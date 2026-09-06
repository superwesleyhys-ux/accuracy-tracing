"""Public-contract regression tests; all evidence is synthetic and offline."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from newsverify.cli import benchmark, run_fixture
from newsverify.core import run_verification
from newsverify.providers import ReplayProvider


ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "examples/demo.json").read_text(encoding="utf-8"))
BENCHMARK = json.loads((ROOT / "examples/benchmark.json").read_text(encoding="utf-8"))


def evidence(identifier, stance="neutral", **overrides):
    """Create an independent, eligible synthetic record unless overridden."""
    item = deepcopy(DEMO["rounds"][0][0])
    item.update(
        id=identifier,
        url=f"https://{identifier}.example/report",
        publisher_group=f"publisher-{identifier}",
        origin_id=f"origin-{identifier}",
        content=f"Synthetic record {identifier}: the supplied annotation is {stance}.",
        stance=stance,
    )
    item["quote"] = item["content"]
    item.update(overrides)
    return item


class HarnessContractTests(unittest.TestCase):
    def setUp(self):
        self.claim = deepcopy(DEMO["claim"])

    def test_all_synthetic_policy_expectations(self):
        for case in BENCHMARK["cases"]:
            with self.subTest(case=case["name"]):
                report = run_fixture(case)
                self.assertEqual(case["expected_status"], report["status"])

    def test_default_checks_another_round_before_supported(self):
        calls = []

        class Provider:
            def search(self, claim, round_number, intent, limit):
                calls.append((round_number, intent))
                return deepcopy(DEMO["rounds"][0]) if round_number == 1 else []

        report = run_verification(self.claim, Provider())
        self.assertEqual("supported", report["status"])
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn("refutation", calls[1][1].lower())

    def test_later_refutation_changes_first_pass(self):
        baseline = run_verification(self.claim, ReplayProvider(DEMO["rounds"]), {"max_rounds": 1})
        loop = run_verification(self.claim, ReplayProvider(DEMO["rounds"]))
        self.assertEqual("supported", baseline["status"])
        self.assertEqual("conflicting", loop["status"])
        self.assertTrue(any(item["stance"] == "contradicts" for item in loop["evidence"]))

    def test_transitive_copies_are_one_source(self):
        records = [
            evidence("a", "supports", publisher_group="owner-one", origin_id="origin-one"),
            evidence("b", "supports", publisher_group="owner-one", origin_id="origin-two"),
            evidence("c", "supports", publisher_group="owner-two", origin_id="origin-two"),
        ]
        report = run_verification(self.claim, ReplayProvider([records[:2], records[2:]]))
        self.assertEqual("unresolved", report["status"])
        self.assertEqual(1, report["independent_source_counts"]["supports"])
        self.assertEqual({"a", "b", "c"}, set(report["source_groups"][0]["evidence_ids"]))

    def test_late_neutral_lineage_can_remove_apparent_independence(self):
        first = [evidence("a", "supports"), evidence("b", "supports")]
        bridge = evidence("bridge", publisher_group=first[0]["publisher_group"], origin_id=first[1]["origin_id"])
        report = run_verification(self.claim, ReplayProvider([first, [bridge]]), {"max_rounds": 2})
        self.assertEqual("unresolved", report["status"])
        self.assertEqual(1, report["independent_source_counts"]["supports"])

    def test_same_source_disagreement_remains_visible(self):
        report = run_verification(self.claim, ReplayProvider([
            [evidence("a", "supports", publisher_group="same-owner")],
            [evidence("b", "contradicts", publisher_group="same-owner")],
        ]))
        self.assertEqual("conflicting", report["status"])
        self.assertEqual(1, report["independent_source_counts"]["conflicting"])

    def test_changed_evidence_reusing_an_id_cannot_leave_claim_supported(self):
        original = evidence("a", "supports")
        correction = evidence("a", "contradicts")
        report = run_verification(self.claim, ReplayProvider([
            [original, evidence("b", "supports")], [correction],
        ]))
        self.assertEqual("unresolved", report["status"])
        self.assertEqual("integrity_error", report["stop_reason"])
        self.assertEqual(original, report["evidence"][0])
        collisions = [record for record in report["rejected"] if "evidence_id_collision" in record["reasons"]]
        self.assertEqual(1, len(collisions))
        self.assertEqual(correction, collisions[0]["evidence"])

    def test_next_round_targets_validation_failures_without_repeating_source_instructions(self):
        intents = []
        article_instruction = "SOURCE_INSTRUCTION_REQUEST_TO_OVERRIDE_THE_REVIEW"
        malformed = evidence("bad", "supports", content=article_instruction, quote="A fabricated quotation.")

        class Provider:
            def search(self, claim, round_number, intent, limit):
                intents.append(intent)
                return [malformed] if round_number == 1 else []

        report = run_verification(self.claim, Provider())
        self.assertEqual("unresolved", report["status"])
        self.assertGreaterEqual(len(intents), 2)
        self.assertIn("quote_not_in_content", intents[1])
        self.assertNotIn(article_instruction, " ".join(intents))

    def test_provider_failure_abstains_and_redacts_exception_message(self):
        secret = "EXAMPLE_PRIVATE_TOKEN_not_a_real_credential"

        class Provider:
            def search(self, claim, round_number, intent, limit):
                if round_number == 1:
                    return deepcopy(DEMO["rounds"][0])
                raise RuntimeError(secret)

        report = run_verification(self.claim, Provider())
        self.assertEqual("unresolved", report["status"])
        self.assertEqual("provider_error", report["stop_reason"])
        self.assertEqual(2, len(report["evidence"]))
        serialized = json.dumps(report, allow_nan=False)
        self.assertNotIn(secret, serialized)
        self.assertIn("RuntimeError", serialized)

    def test_round_budget_stops_provider_with_continuing_new_evidence(self):
        calls = []

        class Provider:
            def search(self, claim, round_number, intent, limit):
                calls.append(round_number)
                return [evidence(f"round-{round_number}")]

        report = run_verification(self.claim, Provider(), {"max_rounds": 3})
        self.assertEqual([1, 2, 3], calls)
        self.assertEqual("unresolved", report["status"])
        self.assertEqual("max_rounds", report["stop_reason"])

    def test_document_budget_bounds_an_unending_iterable(self):
        consumed = []

        class Provider:
            def search(self, claim, round_number, intent, limit):
                number = 0
                while True:
                    number += 1
                    consumed.append((round_number, number))
                    yield evidence(f"r{round_number}-item{number}")

        report = run_verification(self.claim, Provider(), {"max_rounds": 3, "max_documents": 7})
        self.assertEqual(7, len(consumed))
        self.assertEqual(7, report["documents_examined"])
        self.assertLessEqual(len(report["rounds"]), 3)
        self.assertEqual("unresolved", report["status"])

    def test_provider_iterable_is_not_consumed_past_requested_limit(self):
        class Provider:
            def search(self, claim, round_number, intent, limit):
                for number in range(limit):
                    yield evidence(f"r{round_number}-item{number}")
                raise AssertionError("caller consumed beyond the advertised limit")

        report = run_verification(self.claim, Provider(), {"max_rounds": 2, "max_documents": 5})
        self.assertEqual(5, report["documents_examined"])
        self.assertNotEqual("provider_error", report["stop_reason"])

    def test_too_little_budget_for_second_round_stays_unresolved(self):
        report = run_verification(self.claim, ReplayProvider([[evidence("a", "supports")]]), {
            "max_documents": 1, "min_independent_sources": 1,
        })
        self.assertEqual("unresolved", report["status"])
        self.assertEqual("document_budget", report["stop_reason"])

    def test_input_dictionaries_are_not_mutated(self):
        fixture = deepcopy(DEMO)
        fixture["config"] = {"max_rounds": 3}
        snapshot = deepcopy(fixture)

        class Provider:
            def search(self, claim, round_number, intent, limit):
                return fixture["rounds"][round_number - 1][:limit] if round_number <= 2 else []

        run_verification(fixture["claim"], Provider(), fixture["config"])
        self.assertEqual(snapshot, fixture)

    def test_trace_keeps_original_claim_even_if_adapter_changes_its_copy(self):
        original = deepcopy(self.claim)

        class Provider:
            def search(self, claim, round_number, intent, limit):
                claim["text"] = "An adapter attempted to replace the question."
                claim["id"] = "replacement"
                return deepcopy(DEMO["rounds"][round_number - 1]) if round_number <= 2 else []

        report = run_verification(self.claim, Provider())
        self.assertEqual(original, self.claim)
        self.assertEqual(original, report["claim"])
        self.assertEqual("conflicting", report["status"])

    def test_report_is_detached_from_provider_records(self):
        item = evidence("a", "supports", metadata={"tags": ["original"]})

        class Provider:
            def search(self, claim, round_number, intent, limit):
                return [item] if round_number == 1 else []

        report = run_verification(self.claim, Provider())
        item["metadata"]["tags"].append("changed-later")
        self.assertEqual(["original"], report["evidence"][0]["metadata"]["tags"])

    def test_future_evidence_and_fabricated_quote_are_rejected_with_reasons(self):
        records = [
            evidence("future", "supports", published_at="2026-09-06T12:00:00Z", retrieved_at="2026-09-06T13:00:00Z"),
            evidence("bad-quote", "supports", quote="This quotation was never present in the supplied article."),
        ]
        report = run_verification(self.claim, ReplayProvider([records, []]))
        self.assertEqual("unresolved", report["status"])
        self.assertEqual([], report["evidence"])
        reasons = {item["evidence_id"]: item["reasons"] for item in report["rejected"]}
        self.assertIn("future_published_at", reasons["future"])
        self.assertIn("future_retrieved_at", reasons["future"])
        self.assertIn("quote_not_in_content", reasons["bad-quote"])

    def test_malformed_configuration_raises_value_error(self):
        for config in [
            {"max_rounds": True}, {"max_rounds": 0}, {"max_rounds": 1.5},
            {"max_documents": -1}, {"min_independent_sources": 0},
            {"max_age_hours": float("nan")}, {"max_age_hours": -1},
            {"max_age_hours": True}, {"unrecognized_setting": 1}, [],
        ]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_verification(self.claim, ReplayProvider([]), config)

    def test_malformed_claim_raises_value_error(self):
        for claim in [
            None, [], {}, dict(self.claim, id=""), dict(self.claim, text="  "),
            dict(self.claim, as_of="2026-09-05T12:00:00"), dict(self.claim, as_of="not-a-date"),
        ]:
            with self.subTest(claim=claim), self.assertRaises(ValueError):
                run_verification(claim, ReplayProvider([]))

    def test_benchmark_labels_do_not_reach_provider(self):
        captured_claims = []
        captured_rounds = []
        fixture = deepcopy(DEMO)
        fixture["expected_status"] = "LABEL_MUST_NOT_REACH_RETRIEVAL"
        fixture["claim"]["expected_status"] = "NESTED_LABEL_MUST_NOT_REACH_RETRIEVAL"

        class InspectingProvider:
            def __init__(self, rounds):
                captured_rounds.append(deepcopy(rounds))

            def search(self, claim, round_number, intent, limit):
                captured_claims.append(deepcopy(claim))
                return []

        with patch("newsverify.cli.ReplayProvider", InspectingProvider):
            run_fixture(fixture)
        self.assertEqual([fixture["rounds"]], captured_rounds)
        self.assertTrue(captured_claims)
        for claim in captured_claims:
            self.assertEqual({"id", "text", "as_of"}, set(claim))
        self.assertNotIn("LABEL_MUST_NOT_REACH_RETRIEVAL", json.dumps(captured_claims))

    def test_changing_expected_label_changes_score_not_verification(self):
        payload = {"cases": [dict(deepcopy(DEMO), name="label-isolation", expected_status="conflicting")]}
        before = benchmark(payload)
        payload["cases"][0]["expected_status"] = "supported"
        after = benchmark(payload)
        self.assertEqual(before["results"][0]["loop_status"], after["results"][0]["loop_status"])
        self.assertTrue(before["all_policy_expectations_matched"])
        self.assertFalse(after["all_policy_expectations_matched"])


class CommandLineTests(unittest.TestCase):
    def invoke(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "newsverify", *map(str, arguments)],
            cwd=ROOT, text=True, capture_output=True, timeout=10, check=False,
        )

    def test_demo_emits_machine_readable_report(self):
        result = self.invoke("demo")
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("conflicting", report["status"])
        self.assertTrue(report["limitations"])

    def test_invalid_json_and_invalid_schema_fail_cleanly(self):
        for text in ["{this is invalid JSON", '{"claim": {}}']:
            with self.subTest(input=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.json"
                path.write_text(text, encoding="utf-8")
                result = self.invoke("verify", path)
                self.assertEqual(2, result.returncode)
                self.assertIn("newsverify:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_failed_benchmark_returns_nonzero_and_keeps_results(self):
        payload = {"cases": [dict(deepcopy(DEMO), name="deliberately-wrong-label", expected_status="supported")]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = self.invoke("benchmark", path)
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["all_policy_expectations_matched"])
        self.assertEqual("conflicting", report["results"][0]["loop_status"])

    def test_output_cannot_overwrite_input(self):
        original = json.dumps(DEMO)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(original, encoding="utf-8")
            result = self.invoke("verify", path, "--output", path)
            self.assertEqual(2, result.returncode)
            self.assertIn("output must differ from input", result.stderr)
            self.assertEqual(original, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
