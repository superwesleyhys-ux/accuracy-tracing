from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import loop_compare
from model_io import Budget, BudgetClient, PriorResponseCache, digest, schema
from semantic_adapter import (Decomposer, Verifier, compact_context,
                              suppress_active_gap_restatements)
from loop_compare import load_inputs, score
from newsverify import provenance as p
from newsverify.decisions import present_decision
from newsverify.retrieval import SnapshotSearchProvider


def cache_record(system="s", user="u", output="{}", *, model="m",
                 actual_model=None, response_mode="text", output_schema=None,
                 max_completion_tokens=2500, reasoning_effort=None):
    return {
        "requested_model": model,
        "actual_model": actual_model or model,
        "response_id": "recorded-response",
        "system": system,
        "user": user,
        "request_digest": digest([system, user]),
        "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
        "user_payload_sha256": hashlib.sha256(user.encode()).hexdigest(),
        "response_mode": response_mode,
        "output_schema_sha256": (digest(output_schema)
                                  if output_schema is not None else None),
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": reasoning_effort,
        "output": output,
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "usage": {"input_tokens": 10, "output_tokens": 7},
        "seconds": 3,
    }


class AdapterTests(unittest.TestCase):
    def test_monolithic_verifier_cannot_mutate_an_active_gap_by_restatement(self):
        active = {
            "id": "scope-gap", "question": "Find the frozen outcome.",
            "stage": "verification", "dimension": "evidence",
            "blocking": True, "target_id": "case", "basis": [],
            "decision_impact": "The outcome can change the decision.",
            "action": "search", "locator": "frozen outcome", "probe_id": None,
        }
        raw = asdict(p.VerificationResult(
            verdict="unresolved", rationale="Outcome is not visible.",
            evidence_verdict="unresolved", world_verdict="unresolved",
            gaps=(p.Gap(
                "scope-gap", "Fetch it instead.", stage="verification",
                dimension="evidence", blocking=False, target_id="case",
                decision_impact="Changed wording.", action="fetch",
                locator="outcome-version"),)))
        normalized = suppress_active_gap_restatements(raw, {"gaps": [active]})
        self.assertEqual([], normalized["gaps"])
        self.assertEqual("search", active["action"])
        self.assertTrue(active["blocking"])

    def test_monolithic_verifier_keeps_new_tasks_and_rejects_reopen_close(self):
        active = {
            "id": "scope-gap", "question": "Find the frozen outcome.",
            "stage": "verification", "dimension": "evidence",
            "blocking": False, "target_id": "case", "basis": [],
            "decision_impact": "The outcome can change the decision.",
            "action": "search", "locator": "frozen outcome", "probe_id": None,
        }
        fresh = asdict(p.Gap(
            "new-gap", "Find another source.", stage="verification",
            dimension="world", blocking=False, target_id="case",
            decision_impact="It could establish the world claim.",
            action="search", locator="another source"))
        raw = asdict(p.VerificationResult(
            verdict="unresolved", rationale="Outcome is not visible.",
            evidence_verdict="unresolved", world_verdict="unresolved",
            gaps=(p.Gap(**active), p.Gap(**fresh))))
        normalized = suppress_active_gap_restatements(raw, {"gaps": [active]})
        self.assertEqual(["new-gap"], [item["id"] for item in normalized["gaps"]])

        raw["resolutions"] = [{
            "gap_id": "scope-gap", "basis": [], "rationale": "Closed.",
        }]
        with self.assertRaisesRegex(ValueError, "restate and resolve"):
            suppress_active_gap_restatements(raw, {"gaps": [active]})

    def test_scoring_rejects_mixed_question_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "gold.json").write_text(json.dumps({"cases": [{"id": "x", "decision": "true", "assessment_mode": "evidence"}]}))
            (root / "results.json").write_text(json.dumps([{"id": "x", "variant": "loop", "status": "completed",
                "prediction": {"decision": "true", "assessment_mode": "world"}, "checkpoints": []}]))
            with self.assertRaises(ValueError): score(NS(gold=str(root / "gold.json"), run=str(root)))

    def test_no_evidence_unknown_does_not_create_a_false_loop_gain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "gold.json").write_text(json.dumps({"cases": [{"id": "x", "decision": "unverifiable", "assessment_mode": "world"}]}))
            (root / "results.json").write_text(json.dumps([{"id": "x", "variant": "loop", "status": "completed",
                "prediction": {"decision": "unverifiable", "assessment_mode": "world"}, "checkpoints": []}]))
            self.assertEqual(0, score(NS(gold=str(root / "gold.json"), run=str(root))))
            result = json.loads((root / "scores.json").read_text())
            self.assertEqual(result["overall"]["first_correct"], result["overall"]["last_correct"])

    def test_cache_reuses_exact_request_and_preserves_original_usage(self):
        record = cache_record()
        live = []
        cache = PriorResponseCache([record], "m", lambda **kw: live.append(kw) or "live")
        kwargs = {"model": "m", "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"}],
            "max_completion_tokens": 2500}
        result = cache(**kwargs)
        self.assertEqual("recorded-response", result.id)
        self.assertEqual(7, result.usage.completion_tokens)
        self.assertEqual([], live)
        self.assertEqual("live", cache(**kwargs))
        self.assertEqual(1, len(live))
        kwargs["messages"] = [{"role": "system", "content": "s"},
                              {"role": "user", "content": "changed"}]
        self.assertEqual("live", cache(**kwargs))
        self.assertEqual(2, len(live))

    def test_cache_matches_requested_model_not_server_alias(self):
        record = cache_record(actual_model="m-2026-09-05")
        cache = PriorResponseCache([record], "m", lambda **kw: "live")
        result = cache(model="m", messages=[
                           {"role": "system", "content": "s"},
                           {"role": "user", "content": "u"}],
                       max_completion_tokens=2500)
        self.assertEqual("recorded-response", result.id)
        self.assertEqual("m-2026-09-05", result.model)

    def test_cache_does_not_cross_plain_and_json_object_modes(self):
        record = cache_record()
        cache = PriorResponseCache([record], "m", lambda **kw: "live")
        result = cache(
            model="m", messages=[{"role": "system", "content": "s"},
                                 {"role": "user", "content": "u"}],
            max_completion_tokens=2500,
            response_format={"type": "json_object"})
        self.assertEqual("live", result)

    def test_cache_rejects_tampered_output_before_replay(self):
        record = cache_record()
        record["output"] = '{"tampered":true}'
        with self.assertRaisesRegex(ValueError, "output.*integrity"):
            PriorResponseCache([record], "m", lambda **kw: "live")

    def test_cache_rejects_internally_inconsistent_request_record(self):
        record = cache_record()
        record["user"] = "different payload"
        with self.assertRaisesRegex(ValueError, "request digest.*integrity"):
            PriorResponseCache([record], "m", lambda **kw: "live")

    def test_cache_revalidates_integrity_immediately_before_replay(self):
        cache = PriorResponseCache([cache_record()], "m", lambda **kw: "live")
        queued = next(iter(cache.by_key.values()))
        queued[0]["output"] = '{"tampered":true}'
        with self.assertRaisesRegex(ValueError, "output.*integrity"):
            cache(model="m", messages=[
                      {"role": "system", "content": "s"},
                      {"role": "user", "content": "u"}],
                  max_completion_tokens=2500)

    def test_cache_key_matches_schema_reasoning_and_cap_exactly(self):
        output_schema = {"type": "object", "properties": {}}
        cache = PriorResponseCache([cache_record(
            response_mode="json_schema", output_schema=output_schema,
            max_completion_tokens=1200, reasoning_effort="high")],
            "m", lambda **kw: "live")
        base = {"model": "m", "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "u"}],
                "max_completion_tokens": 1200,
                "reasoning_effort": "high",
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "result", "strict": True, "schema": output_schema}}}
        self.assertEqual("live", cache(**{**base, "reasoning_effort": "low"}))
        self.assertEqual("live", cache(**{**base, "max_completion_tokens": 1199}))
        changed_schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        self.assertEqual("live", cache(**{**base, "response_format": {
            "type": "json_schema", "json_schema": {
                "name": "result", "strict": True, "schema": changed_schema}}}))
        self.assertEqual("recorded-response", cache(**base).id)

    def test_cache_does_not_reuse_failed_response(self):
        cache = PriorResponseCache([{"actual_model": "m", "error_type": "RuntimeError"}], "m", lambda **kw: "live")
        self.assertEqual("live", cache(model="m", messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"}], max_completion_tokens=2500))

    def test_transport_audit_records_stage_and_prompt_hashes(self):
        response = NS(id="r", model="m", usage=NS(prompt_tokens=2, completion_tokens=1),
                      choices=[NS(finish_reason="stop", message=NS(content="ok", refusal=None))])
        client = BudgetClient("m", Budget(), transport=lambda **_: response)
        self.assertEqual("ok", client.call("system", "payload", stage="atoms",
                                            prompt_version="staged-v1"))
        record, = client.records
        self.assertEqual("atoms", record["stage"])
        self.assertEqual("staged-v1", record["prompt_version"])
        self.assertEqual(64, len(record["system_prompt_sha256"]))
        self.assertEqual(64, len(record["user_payload_sha256"]))

    def test_new_gap_and_verdict_values_are_constrained_before_live_call(self):
        gap = schema(p.Gap)["properties"]
        self.assertEqual(["fetch", "search", "reanalyse"], gap["action"]["enum"])
        self.assertNotIn("auto", gap["dimension"]["enum"])
        verification = schema(p.VerificationResult)["properties"]
        self.assertEqual("string", verification["world_verdict"]["type"])
        self.assertEqual(["evidence", "world"], verification["gaps"]["items"]["properties"]["dimension"]["enum"])

    def test_actual_semantic_adapter_engine_and_final_mapping_with_explicit_fake(self):
        value = p.MaterialVersion("m", "https://example.org/m", "The bridge remains closed.",
            "2026-09-04T20:00:00Z", "2026-09-04T10:00:00Z", "2026-09-04T10:00:00Z", "Fixture")
        target = p.Target("c", "The bridge is open.", "2026-09-04T20:00:00Z", assessment_mode="evidence", evidence_scope=("m",))
        basis = p.Span("m", 0, len(value.content), value.content)
        calls = []
        def fake(**kwargs):
            calls.append(kwargs)
            verification = "Return TWO distinct assessments" in kwargs["messages"][0]["content"]
            output = (p.VerificationResult("contradicted", (basis,), "Negation", evidence_verdict="contradicted", world_verdict="unresolved")
                      if verification else p.Analysis(fragments=(p.Fragment("f", "Closed", basis, target.id),)))
            return NS(id="fake", model="fake", usage=NS(prompt_tokens=1, completion_tokens=1),
                choices=[NS(finish_reason="stop", message=NS(content=json.dumps(asdict(output)), refusal=None))])
        client = BudgetClient("fake", Budget(), transport=fake)
        trace = p.run_provenance(target, SnapshotSearchProvider([value], ["m"]), Decomposer(client), Verifier(client))
        self.assertEqual([], trace["errors"])
        self.assertEqual("false", present_decision(trace)["decision"])
        self.assertEqual("unresolved", trace["fact_status"])
        self.assertEqual(2, len(calls))
        self.assertTrue(all("earlier_report" not in c["messages"][1]["content"] for c in calls))
        self.assertTrue(all('"retrieved_at"' not in c["messages"][1]["content"]
                            for c in calls))

    def test_frozen_inputs_have_no_gold_labels(self):
        path = Path(__file__).resolve().parents[1] / "experiments/inputs-v03.json"
        self.assertEqual(5, len(load_inputs(path)["cases"]))

    def test_compact_context_does_not_duplicate_full_analysis_history(self):
        fragment = {"id": "f", "span": {"version_id": "m", "start": 0, "end": 1, "quote": "x"},
                    "qualifier_spans": []}
        relation = {"id": "r", "basis": [{"version_id": "m", "quote": "x"}], "rationale": "visible"}
        full = {"materials": [], "fragments": [fragment], "relations": [relation], "origins": [], "gaps": [], "usage": {"rounds": 1},
                "analyses": {"sensitive-to-cost": "long output"}, "verification_history": ["long history"]}
        result = compact_context(full)
        self.assertNotIn("analyses", result)
        self.assertNotIn("verification_history", result)
        self.assertEqual([{"parent_id": None, "span": fragment["span"],
                           "qualifier_spans": []}], result["fragments"])
        self.assertNotIn("id", result["relations"][0])
        self.assertNotIn("rationale", result["relations"][0])

    def test_loop_runner_writes_staged_contract_before_missing_auth_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            inputs = Path(__file__).resolve().parents[1] / "experiments" / "inputs-v03.json"
            args = NS(inputs=str(inputs), output=str(output), model="fixture-model",
                      max_rounds=2, reuse_from=None, semantic_mode="staged", max_repairs=1)
            with patch.dict(loop_compare.os.environ, {}, clear=True):
                self.assertEqual(2, loop_compare.run(args))
            config = json.loads((output / "config.json").read_text())
            self.assertEqual("staged", config["semantic_mode"])
            self.assertEqual(1, config["max_inner_repairs"])
            self.assertEqual("staged-validation-v6", config["prompt_manifest"]["version"])
            self.assertEqual("blocked_missing_auth",
                             json.loads((output / "status.json").read_text())["status"])


if __name__ == "__main__": unittest.main()
