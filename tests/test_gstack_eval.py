"""Scoring and artifact-integrity regressions; no inference or network calls."""
from copy import deepcopy
import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCORER = runpy.run_path(str(ROOT / "experiments/gstack-harness-eval-20260908/summarize_test.py"))
score_run = SCORER["score_run"]
token_stats = SCORER["token_stats"]
mechanisms = SCORER["mechanisms"]
load_batch = SCORER["load_batch"]
summarize = SCORER["summarize"]

TEXT = "The measured count was seven. Follow-up was planned."
CASE = {"target": {"id": "case-a", "text": "The measured count was seven.", "as_of": "2026-02-01T00:00:00Z", "source_version_id": "s1"},
        "materials": [{"version_id": "s1", "url": "https://example.test/source", "content": TEXT,
                       "retrieved_at": "2026-01-01T00:00:00Z", "available_at": "2026-01-01T00:00:00Z",
                       "availability_basis": "Captured source bytes at the stated time."}]}
GOLD = {"id": "case-a", "expected_fact_status": "supported", "reason": "The source states seven."}
OUTPUT = {"verdict": "supported", "basis": [{"version_id": "s1", "quote": "The measured count was seven."}], "rationale": "The source states the target count."}


def call(stage="direct", usage=None):
    return {"stage": stage, "success": True, "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 50} if usage is None else usage}


def run(condition="direct", output=None):
    result = {"id": "case-a", "condition": condition, "route": "local", "fact_status": "supported", "errors": [],
              "calls": [call("direct" if condition == "direct" else "verify")],
              "timer_seconds": 1.0, "utc_elapsed_seconds": 1.0}
    response = deepcopy(OUTPUT if output is None else output)
    if condition == "direct":
        result["raw_response"] = response
    else:
        response.update(round=1, gaps=[], resolutions=[])
        result["report"] = {"verification_history": [response], "analysis_history": [], "operations": [], "gaps": []}
    return result


class ScoringTests(unittest.TestCase):
    def test_malformed_direct_output_fails_without_crashing_or_matching(self):
        invalid = [None, [], "supported", {}, {"verdict": []},
                   {**OUTPUT, "basis": "invented"}, {**OUTPUT, "verdict": ["supported"]},
                   {**OUTPUT, "basis": [{"version_id": ["s1"], "quote": "seven"}]},
                   {**OUTPUT, "extra": "unexpected"}]
        for value in invalid:
            with self.subTest(output=value):
                result = run()
                result["raw_response"] = value
                row = score_run(result, CASE, GOLD)
                self.assertFalse(row["pipeline_success"])
                self.assertFalse(row["completed_label_match"])
                self.assertFalse(row["evidence_valid_label_match"])

    def test_label_matches_are_distinct_from_citation_valid_matches_for_both_conditions(self):
        for condition in ("direct", "double_loop"):
            valid = score_run(run(condition), CASE, GOLD)
            self.assertTrue(valid["completed_label_match"])
            self.assertTrue(valid["evidence_valid_label_match"])
            for response in ({**OUTPUT, "basis": [{"version_id": "missing", "quote": "seven"}]},
                             {**OUTPUT, "rationale": " "}, {**OUTPUT, "basis": []},
                             {**OUTPUT, "basis": [{**OUTPUT["basis"][0], "start": True, "end": 29}]}):
                with self.subTest(condition=condition, response=response):
                    row = score_run(run(condition, response), CASE, GOLD)
                    self.assertTrue(row["completed_label_match"])
                    self.assertFalse(row["evidence_valid_label_match"])

    def test_duplicate_or_future_quotes_fail_evidence_validation(self):
        duplicate, future = deepcopy(CASE), deepcopy(CASE)
        duplicate["materials"][0]["content"] += " The measured count was seven."
        future["materials"][0]["retrieved_at"] = "2026-03-01T00:00:00Z"
        future["materials"][0]["available_at"] = "2026-03-01T00:00:00Z"
        for case in (duplicate, future):
            for condition in ("direct", "double_loop"):
                with self.subTest(case=case, condition=condition):
                    row = score_run(run(condition), case, GOLD)
                    self.assertTrue(row["completed_label_match"])
                    self.assertFalse(row["evidence_valid_label_match"])

    def test_execution_errors_never_receive_abstention_credit(self):
        output = {"verdict": "unresolved", "basis": [], "rationale": "Evidence is insufficient."}
        gold = {**GOLD, "expected_fact_status": "unresolved"}
        for condition in ("direct", "double_loop"):
            result = run(condition, output)
            result["fact_status"] = "unresolved"
            self.assertTrue(score_run(result, CASE, gold)["evidence_valid_label_match"])
            for mutation in ("errors", "calls", "failed_call"):
                damaged = deepcopy(result)
                if mutation == "errors":
                    damaged["errors"] = [{"type": "Timeout"}]
                elif mutation == "calls":
                    damaged["calls"] = []
                else:
                    damaged["calls"][0]["success"] = False
                row = score_run(damaged, CASE, gold)
                self.assertFalse(row["pipeline_success"])
                self.assertFalse(row["completed_label_match"])

    def test_harness_visible_downgrade_is_separate_from_raw_verdict(self):
        result = run("double_loop")
        result["fact_status"] = "unresolved"
        result["report"]["gaps"] = [{"id": "open", "stage": "verification"}]
        row = score_run(result, CASE, {**GOLD, "expected_fact_status": "unresolved"})
        self.assertEqual(row["raw_verdict"], "supported")
        self.assertEqual(row["observed"], "unresolved")
        self.assertTrue(row["completed_label_match"])
        direct = run()
        direct["fact_status"] = "unresolved"
        self.assertFalse(score_run(direct, CASE, {**GOLD, "expected_fact_status": "unresolved"})["pipeline_success"])

    def test_unknown_invalid_usage_is_not_zero_and_cached_tokens_are_not_added_twice(self):
        complete = token_stats([call(), call()])
        self.assertEqual(complete["total_tokens"], 240)
        self.assertEqual(complete["cached_input_tokens"], 100)
        for bad in ({}, {"input_tokens": True, "output_tokens": 20}, {"input_tokens": 100, "output_tokens": -1},
                    {"input_tokens": 100, "output_tokens": 20, "total_tokens": 130},
                    {"input_tokens": 100, "output_tokens": 20, "total_tokens": False}):
            with self.subTest(bad=bad):
                stats = token_stats([call(), call(usage=bad)])
                self.assertIsNone(stats["total_tokens"])
                self.assertEqual(stats["known_total_tokens"], 120)
                self.assertEqual(stats["known_usage_calls"], 1)
        self.assertIsNone(token_stats([])["total_tokens"])
        bad_cache = token_stats([call(usage={"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": -5})])
        self.assertEqual(bad_cache["total_tokens"], 120)
        self.assertIsNone(bad_cache["cached_input_tokens"])

    def test_feedback_requires_new_saved_source_before_decomposition_and_verification(self):
        report = mechanism_report()
        proof = mechanisms(report)
        self.assertTrue(proof["both_loops_executed"])
        self.assertEqual(proof["feedback"][0]["historically_resolved_gap_ids"], ["g"])
        self.assertEqual(proof["feedback"][0]["finally_resolved_gap_ids"], [])
        self.assertEqual(proof["feedback"][0]["still_open_gap_ids"], ["g"])
        report["gaps"] = []
        self.assertEqual(mechanisms(report)["feedback"][0]["finally_resolved_gap_ids"], ["g"])
        wrong_order = deepcopy(report)
        wrong_order["operations"][2]["sequence"] = 6
        self.assertFalse(mechanisms(wrong_order)["verification_feedback_executed"])
        no_new_evidence = deepcopy(report)
        no_new_evidence["analysis_history"].pop(1)
        self.assertFalse(mechanisms(no_new_evidence)["reanalysis_executed"])
        unsaved = deepcopy(report)
        unsaved["operations"].pop(1)
        self.assertFalse(mechanisms(unsaved)["verification_feedback_executed"])


def mechanism_report():
    return {"analysis_history": [
        {"version_id": "s1", "revision": 1, "round": 1, "accepted": True, "revisit": False, "analysis": {"notes": "old", "resolutions": []}},
        {"version_id": "s2", "revision": 2, "round": 2, "accepted": True, "revisit": False, "analysis": {"resolutions": [{"gap_id": "g"}]}},
        {"version_id": "s1", "revision": 3, "round": 2, "accepted": True, "revisit": True, "analysis": {"notes": "new", "resolutions": []}}],
        "verification_history": [{"round": 1, "gaps": [{"id": "g", "stage": "verification"}], "resolutions": []},
                                 {"round": 2, "gaps": [], "resolutions": [{"gap_id": "g"}]},
                                 {"round": 3, "gaps": [{"id": "g", "stage": "verification"}], "resolutions": []}],
        "gaps": [{"id": "g", "stage": "verification"}], "eligible_version_ids": ["s1", "s2"],
        "execution": {"provider_requests": [{"round": 2, "selected_version_id": "s2", "tasks": [{"id": "g", "stage": "verification"}]}]},
        "operations": [{"round": 1, "sequence": 1, "action": "snapshot_saved", "version_id": "s1", "eligible": True},
                       {"round": 2, "sequence": 2, "action": "snapshot_saved", "version_id": "s2", "eligible": True},
                       {"round": 2, "sequence": 3, "action": "decompose_completed", "version_id": "s2"},
                       {"round": 2, "sequence": 4, "action": "verification_completed"}]}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "results"
        self.out.mkdir()
        self.write(self.root / "corpus.json", {"cases": [CASE]})
        self.write(self.root / "gold.json", {"cases": [GOLD]})
        self.manifest = {"case_count": 1, "event_family_count": 1, "corpus_path": "corpus.json", "gold_path": "gold.json",
                         "model": "gpt-6-astra", "reasoning_effort": "medium", "tunnel": "local",
                         "frozen_sha256": {name: SCORER["sha"](self.root / name) for name in ("corpus.json", "gold.json")}}
        self.batch = {"manifest": self.manifest, "gold": {"cases": [GOLD]}, "results": [run(), run("double_loop")]}
        self.save()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def save(self):
        self.write(self.out / "manifest.json", self.manifest)
        self.write(self.out / "all-results.json", self.batch)
        for result in self.batch["results"]:
            folder = self.out / result["id"] / result["condition"]
            self.write(folder / "result.json", result)
            for index, receipt in enumerate(result["calls"], 1):
                self.write(folder / f"{index:02d}-{receipt['stage']}.calls.json", [receipt])

    def test_complete_batch_reports_matches_without_mutating_inference_artifacts(self):
        before = (self.out / "all-results.json").read_bytes()
        summary = summarize(self.out, self.root)
        self.assertEqual(summary["conditions"]["direct"]["evidence_valid_label_matches"], 1)
        self.assertEqual(summary["conditions"]["double_loop"]["total_tokens"], 120)
        self.assertTrue((self.out / "REPORT.md").is_file())
        self.assertEqual((self.out / "all-results.json").read_bytes(), before)

    def test_duplicate_or_missing_condition_is_rejected(self):
        self.batch["results"][1] = deepcopy(self.batch["results"][0])
        self.save()
        with self.assertRaisesRegex(ValueError, "Duplicate or missing"):
            load_batch(self.out, self.root)
        self.batch["results"].pop()
        self.save()
        with self.assertRaisesRegex(ValueError, "Missing or extra"):
            load_batch(self.out, self.root)

    def test_changed_receipt_and_result_sidecar_are_rejected(self):
        self.write(self.out / "case-a/direct/01-direct.calls.json", [])
        with self.assertRaisesRegex(ValueError, "Transport receipt"):
            load_batch(self.out, self.root)
        self.save()
        self.write(self.out / "case-a/direct/result.json", {})
        with self.assertRaisesRegex(ValueError, "Result sidecar"):
            load_batch(self.out, self.root)

    def test_frozen_snapshots_recover_changed_working_files_but_labels_cannot_change(self):
        for name in ("corpus.json", "gold.json"):
            self.write(self.out / "frozen-inputs" / name, SCORER["read"](self.root / name))
            self.write(self.root / name, {})
        load_batch(self.out, self.root)
        self.batch["gold"] = {"cases": []}
        self.save()
        with self.assertRaisesRegex(ValueError, "Aggregate labels"):
            load_batch(self.out, self.root)
        (self.out / "frozen-inputs/corpus.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Frozen artifact"):
            load_batch(self.out, self.root)


if __name__ == "__main__":
    unittest.main()
