"""Offline contract tests for the frozen 2023 historical comparison."""
from __future__ import annotations

from copy import deepcopy
import argparse
from dataclasses import asdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import historical_compare as historical
import loop_compare
from model_io import BudgetClient


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class HistoricalComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.inputs = root / "inputs.json"
        self.sources = root / "sources.json"
        self.gold = root / "gold.json"
        self.freeze = root / "freeze.json"
        self.claims = ["The mission will launch by the end of 2024.",
                       "The rover will launch by the end of 2024."]
        self.outcomes = ["The mission launched successfully on July 9, 2024.",
                         "The rover project was ended on July 17, 2024."]
        cases = []
        source_cases = []
        gold_cases = []
        for index, decision in enumerate(("true", "false"), start=1):
            identifier = f"case-{index}"
            claim_id, outcome_id = f"claim-{index}", f"outcome-{index}"
            materials = [
                {"version_id": claim_id,
                 "url": f"https://agency.example/{claim_id}",
                 "content": self.claims[index - 1],
                 "retrieved_at": "2026-09-05T00:00:00Z",
                 "published_at": "2023-12-01T12:00:00Z",
                 "available_at": "2023-12-01T12:00:00Z",
                 "availability_basis": "Official dated body capture.",
                 "issuer": "Official Agency"},
                {"version_id": outcome_id,
                 "url": f"https://agency.example/{outcome_id}",
                 "content": self.outcomes[index - 1],
                 "retrieved_at": "2026-09-05T00:00:00Z",
                 "published_at": "2024-07-17T12:00:00Z",
                 "available_at": "2024-07-17T12:00:00Z",
                 "availability_basis": "Official dated body capture.",
                 "issuer": "Official Agency"},
            ]
            cases.append({
                "target": {"id": identifier,
                           "text": self.claims[index - 1],
                           "as_of": historical.BENCHMARK_CUTOFF,
                           "source_version_id": claim_id,
                           "assessment_mode": "evidence",
                           "evidence_scope": [outcome_id]},
                "materials": materials,
                "seed_ids": [claim_id],
                "full_evidence_control": index == 1,
            })
            source_cases.append({
                "id": identifier, "event_id": identifier,
                "domain": "space", "modality": "forecast_resolution",
                "claim_made_at": "2023-12-01T12:00:00Z",
                "resolution_deadline": historical.BENCHMARK_CUTOFF,
                "normalization": "Event occurs no later than the cutoff.",
                "materials": [
                    {"version_id": claim_id, "role": "claim",
                     "source_url": f"https://agency.example/{claim_id}",
                     "content_sha256": _digest(self.claims[index - 1]),
                     "source_format": "html", "official_source": True,
                     "body_only": True,
                     "version_proof": {
                         "kind": "official_repository_record",
                         "locator": f"https://archive.example/{claim_id}",
                         "observed_at": "2023-12-01T12:00:00Z",
                         "identifier": claim_id,
                         "artifact_sha256": _digest(
                             "artifact:" + self.claims[index - 1]),
                         "artifact_bytes": len(
                             self.claims[index - 1].encode("utf-8"))}},
                    {"version_id": outcome_id, "role": "outcome",
                     "source_url": f"https://agency.example/{outcome_id}",
                     "content_sha256": _digest(self.outcomes[index - 1]),
                     "source_format": "html", "official_source": True,
                     "body_only": True,
                     "version_proof": {
                         "kind": "official_repository_record",
                         "locator": f"https://archive.example/{outcome_id}",
                         "observed_at": "2024-07-17T12:00:00Z",
                         "identifier": outcome_id,
                         "artifact_sha256": _digest(
                             "artifact:" + self.outcomes[index - 1]),
                         "artifact_bytes": len(
                             self.outcomes[index - 1].encode("utf-8"))}},
                ],
            })
            gold_cases.append({
                "id": identifier, "event_id": identifier,
                "assessment_mode": "evidence", "decision": decision,
                "adjudication_source_version_ids": [outcome_id],
                "rationale": "The official outcome resolves the forecast.",
                "basis": [{"version_id": outcome_id,
                           "quote": self.outcomes[index - 1]}],
            })
        self.input_data = {"schema_version": 1, "cases": cases}
        self.source_data = {
            "schema_version": 1, "benchmark_id": "historical-2023-v1",
            "task": "Resolve forecasts using only official frozen evidence.",
            "claim_window": historical.CLAIM_WINDOW,
            "evidence_cutoff": historical.BENCHMARK_CUTOFF,
            "capture": {"method": "body-only manual transcription"},
            "cases": source_cases,
        }
        self.gold_data = {
            "schema_version": 1,
            "dataset_kind": "historical_forecast_resolution",
            "cases": gold_cases,
            "limitations": "Small official-source benchmark.",
        }
        self._write_data()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    def _write_data(self):
        self._write(self.inputs, self.input_data)
        self._write(self.sources, self.source_data)
        self._write(self.gold, self.gold_data)
        self._refreeze()

    def _refreeze(self):
        freeze = {
            "schema_version": 1,
            "benchmark_id": self.source_data["benchmark_id"],
            "pre_run_checksum": True,
            "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (self.inputs, self.sources, self.gold)},
            "rule": "Never edit frozen cases or gold after model calls.",
        }
        self._write(self.freeze, freeze)

    def _args(self, **overrides):
        values = dict(inputs=str(self.inputs), sources=str(self.sources),
                      freeze=str(self.freeze), gold=str(self.gold),
                      model="fixture-model", reasoning_effort="high",
                      max_rounds=5, max_repairs=1)
        values.update(overrides)
        return argparse.Namespace(**values)

    def _clean_git(self):
        return {"repository_root": str(ROOT), "commit": "a" * 40,
                "clean": True, "all_inputs_at_commit": True,
                "eligible": True, "files": {}}

    def test_audit_accepts_frozen_2023_cases(self):
        output = self.inputs.parent / "audit.json"
        self.assertEqual(0, historical.audit(self._args(output=str(output))))
        result = json.loads(output.read_text())
        self.assertEqual("passed", result["status"])
        self.assertEqual({"true": 1, "false": 1}, result["labels"])
        checks = " ".join(result["checks"])
        self.assertIn("four-digit years from 2025 onward", checks)
        self.assertIn("does not independently authenticate remote artifacts",
                      checks)
        self.assertIn("not that an output came from the API", checks)

    def test_repository_historical_2023_dataset_audits_after_schema_update(self):
        dataset = ROOT / "experiments" / "historical-2023"
        paths = {name: dataset / f"{name}.json"
                 for name in ("inputs", "sources", "gold", "freeze")}
        self.assertTrue(all(path.is_file() for path in paths.values()),
                        "repository historical dataset must be present")
        sources = json.loads(paths["sources"].read_text())
        gold = json.loads(paths["gold"].read_text())
        freeze = json.loads(paths["freeze"].read_text())
        migrated = (
            freeze.get("pre_run_checksum") is True
            and all("resolution_deadline" in case
                    and all({"source_url", "version_proof"} <= set(material)
                            for material in case.get("materials", ()))
                    for case in sources.get("cases", ()))
            and all({"rationale", "basis"} <= set(case)
                    for case in gold.get("cases", ())))
        self.assertTrue(migrated,
                        "repository historical schema migration must be complete")
        output = self.inputs.parent / "repository-audit.json"
        args = self._args(
            inputs=str(paths["inputs"]), sources=str(paths["sources"]),
            gold=str(paths["gold"]), freeze=str(paths["freeze"]),
            output=str(output))
        self.assertEqual(0, historical.audit(args))
        self.assertEqual("passed", json.loads(output.read_text())["status"])

        # The committed corpus itself passes despite honest 2026 retrieved_at
        # audit metadata.  Even a checksum-consistent 2025 hindsight sentence
        # in model-visible material must fail before inference.
        self.input_data = json.loads(paths["inputs"].read_text())
        self.source_data = sources
        self.gold_data = gold
        material = self.input_data["cases"][0]["materials"][0]
        material["content"] += " Post-cutoff hindsight note added in 2025."
        source_material = next(
            item for item in self.source_data["cases"][0]["materials"]
            if item["version_id"] == material["version_id"])
        source_material["content_sha256"] = historical._content_sha(
            material["content"])
        self._write_data()
        with self.assertRaisesRegex(ValueError,
                                    "Model-visible input.*post-2024 year 2025"):
            historical.validate_inference(
                self.inputs, self.sources, self.freeze)

    def test_rejects_cutoff_and_non_2023_claim_dates(self):
        self.input_data["cases"][0]["target"]["as_of"] = (
            "2025-01-01T00:00:00Z")
        self._write_data()
        with self.assertRaisesRegex(ValueError,
                                    "post-2024 year 2025|target as_of"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self.input_data["cases"][0]["target"]["as_of"] = (
            historical.BENCHMARK_CUTOFF)
        self.source_data["cases"][0]["claim_made_at"] = (
            "2024-01-01T00:00:00Z")
        self._write_data()
        with self.assertRaisesRegex(ValueError, "claim_made_at"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_rejects_post_cutoff_material_and_content_hash_mismatch(self):
        self.input_data["cases"][0]["materials"][1]["available_at"] = (
            "2025-01-01T00:00:00Z")
        self.source_data["cases"][0]["materials"][1]["version_proof"][
            "observed_at"] = "2025-01-01T00:00:00Z"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "cutoff"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self.input_data["cases"][0]["materials"][1]["available_at"] = (
            "2024-07-17T12:00:00Z")
        self.source_data["cases"][0]["materials"][1]["version_proof"][
            "observed_at"] = "2024-07-17T12:00:00Z"
        self.input_data["cases"][0]["materials"][1]["content"] += " changed"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "Content sha256 mismatch"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_rejects_role_and_seed_scope_mismatch(self):
        self.input_data["cases"][0]["seed_ids"] = ["outcome-1"]
        self._write_data()
        with self.assertRaisesRegex(ValueError, "seed_ids"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self.input_data["cases"][0]["seed_ids"] = ["claim-1"]
        self.input_data["cases"][0]["target"]["evidence_scope"] = ["claim-1"]
        self._write_data()
        with self.assertRaisesRegex(ValueError, "evidence_scope"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_source_url_and_version_proof_are_strictly_bound(self):
        meta = self.source_data["cases"][0]["materials"][0]
        original_url = meta["source_url"]
        meta["source_url"] = "https://different.example/claim"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "source_url mismatch"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        meta["source_url"] = original_url
        meta["version_proof"]["observed_at"] = "2023-12-02T12:00:00Z"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "observed_at must equal"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        meta["version_proof"]["observed_at"] = "2023-12-01T12:00:00Z"
        meta["version_proof"]["artifact_sha256"] = "not-a-hash"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "artifact_sha256"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        meta["version_proof"]["artifact_sha256"] = _digest(
            "artifact:" + self.claims[0])
        meta["version_proof"]["artifact_bytes"] = 0
        self._write_data()
        with self.assertRaisesRegex(ValueError, "artifact_bytes"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        meta["version_proof"]["artifact_bytes"] = len(
            self.claims[0].encode("utf-8"))
        meta["version_proof"]["kind"] = "self_reported"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "kind is unsupported"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        meta["version_proof"]["kind"] = "official_repository_record"
        meta["version_proof"]["locator"] = "local-artifact"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "absolute HTTPS"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_resolution_deadline_and_event_order_are_enforced(self):
        source_case = self.source_data["cases"][0]
        source_case["resolution_deadline"] = "2024-07-16T23:59:59Z"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "resolution_deadline"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        source_case["resolution_deadline"] = historical.BENCHMARK_CUTOFF
        self.input_data["cases"][0]["materials"][0]["published_at"] = (
            "2024-01-01T00:00:00Z")
        self._write_data()
        with self.assertRaisesRegex(ValueError, "published in 2023"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self.input_data["cases"][0]["materials"][0]["published_at"] = (
            "2023-12-01T12:00:00Z")
        outcome_publication = self.input_data["cases"][0]["materials"][1][
            "published_at"]
        self.input_data["cases"][0]["materials"][0]["available_at"] = (
            outcome_publication)
        source_case["materials"][0]["version_proof"]["observed_at"] = (
            outcome_publication)
        self._write_data()
        with self.assertRaisesRegex(ValueError, "strictly predate"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self.input_data["cases"][0]["materials"][0]["available_at"] = (
            "2023-12-01T12:00:00Z")
        source_case["materials"][0]["version_proof"]["observed_at"] = (
            "2023-12-01T12:00:00Z")
        source_case["resolution_deadline"] = "2025-01-01T00:00:00Z"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_rejects_freeze_tampering_and_answer_leakage(self):
        self.inputs.write_text(self.inputs.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Frozen sha256 mismatch"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

        self._write_data()
        self.source_data["cases"][0]["normalization"] = {
            "decision": "true"}
        self._write_data()
        with self.assertRaisesRegex(ValueError, "forbidden answer field"):
            historical.validate_inference(self.inputs, self.sources, self.freeze)

    def test_run_does_not_open_gold_and_blocks_with_zero_calls(self):
        self.gold.write_text("not json and deliberately unfrozen", encoding="utf-8")
        seen = []
        original = historical._json

        def tracked(path):
            seen.append(Path(path))
            return original(path)

        output = self.inputs.parent / "blocked"
        with (patch.object(historical, "_json", side_effect=tracked),
              patch.object(historical, "git_state",
                           return_value=self._clean_git()),
              patch.object(historical.loop_compare, "run") as model_runner,
              patch.dict(os.environ, {"OPENAI_API_KEY": "configured"},
                         clear=True)):
            result = historical.run(self._args(output=str(output)))
        self.assertEqual(2, result)
        model_runner.assert_not_called()
        self.assertNotIn(self.gold, seen)
        status = json.loads((output / "status.json").read_text())
        self.assertEqual("blocked_model_calls_not_authorized", status["status"])
        self.assertEqual(0, status["model_calls"])

        missing_auth = self.inputs.parent / "missing-auth"
        with (patch.object(historical, "git_state",
                           return_value=self._clean_git()),
              patch.object(historical.loop_compare, "run") as model_runner,
              patch.dict(os.environ, {
                  "ACCURACY_TRACING_ALLOW_MODEL_CALLS": "1"}, clear=True)):
            self.assertEqual(2, historical.run(
                self._args(output=str(missing_auth))))
        model_runner.assert_not_called()
        status = json.loads((missing_auth / "status.json").read_text())
        self.assertEqual("blocked_missing_auth", status["status"])
        self.assertEqual(0, status["model_calls"])

    def test_audit_checks_gold_freeze_even_though_run_does_not(self):
        self.gold.write_text(self.gold.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Frozen sha256 mismatch"):
            historical.audit(self._args(output=None))

    def test_gold_basis_must_be_exact_outcome_text(self):
        self.gold_data["cases"][0]["basis"][0]["quote"] = "not in outcome"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "occur exactly once"):
            historical.validate_all(
                self.inputs, self.sources, self.gold, self.freeze)

    def test_dirty_or_uncommitted_git_blocks_before_model_calls(self):
        for name, state, expected in (
                ("dirty", {"eligible": False, "clean": False,
                           "all_inputs_at_commit": True},
                 "blocked_dirty_git_worktree"),
                ("uncommitted", {"eligible": False, "clean": True,
                                 "all_inputs_at_commit": False},
                 "blocked_inputs_not_at_git_commit")):
            output = self.inputs.parent / name
            with (self.subTest(name=name),
                  patch.object(historical, "git_state", return_value=state),
                  patch.object(historical.loop_compare, "run") as model_runner,
                  patch.dict(os.environ, {
                      "OPENAI_API_KEY": "configured",
                      "ACCURACY_TRACING_ALLOW_MODEL_CALLS": "1"}, clear=True)):
                self.assertEqual(2, historical.run(
                    self._args(output=str(output))))
            model_runner.assert_not_called()
            status = json.loads((output / "status.json").read_text())
            self.assertEqual(expected, status["status"])
            self.assertEqual(0, status["model_calls"])

    def test_historical_run_rejects_reuse(self):
        with self.assertRaisesRegex(ValueError, "forbids response replay"):
            historical.run(self._args(
                output=str(self.inputs.parent / "reused"),
                reuse_from=str(self.inputs.parent / "old")))

    def _fake_arm(self, calls):
        real_run = loop_compare.run
        response_sequence = itertools.count(1)

        class OracleBudgetClient(BudgetClient):
            """Offline transport whose logged JSON actually builds the trace."""

            def __init__(self, model, budget, transport=None,
                         reasoning_effort=None):
                super().__init__(
                    model, budget, transport=self._oracle_transport,
                    reasoning_effort=reasoning_effort)

            @staticmethod
            def _unresolved_layer(payload):
                stop = ("scope_unavailable" if payload.get("missing_scope")
                        else "no_source_lead")
                return {"probe_results": [{
                    "probe_number": probe["number"],
                    "basis_pool": [],
                    "dimension_results": [{
                        "dimension": dimension,
                        "verdict": "unresolved",
                        "basis_indices": [],
                        "rationale": "The fixture makes no semantic claim.",
                    } for dimension in probe["required_dimensions"]],
                    "gaps": [], "resolutions": [], "stop_reason": stop,
                } for probe in payload["target_plan"]["probes"]]}

            def _oracle_transport(self, **kwargs):
                system = kwargs["messages"][0]["content"]
                payload = json.loads(kwargs["messages"][1]["content"])
                if "Stage: atoms." in system:
                    material = payload["material"]
                    value = {"atoms": [{
                        "statement": material["content"],
                        "quote": material["content"],
                        "qualifier_quotes": [],
                    }], "notes": ""}
                elif "Stage: lineage." in system:
                    value = {"citations": [], "origin": None,
                             "revisit": [], "notes": ""}
                elif "Stage: decomposition critic." in system:
                    value = {"decision": "accept", "stage": "none",
                             "quote": "", "issue": ""}
                elif ("Stage: evidence critic." in system
                      or "Stage: world critic." in system):
                    value = {"decision": "accept", "issue": "",
                             "basis": []}
                elif ("Stage: evidence verification." in system
                      or "Stage: world verification." in system):
                    value = self._unresolved_layer(payload)
                elif "Return TWO distinct assessments" in system:
                    if payload["target"]["id"] == "case-2":
                        # A real transport exception is redacted into the call
                        # log, retained in the trace, and must remain scoreable
                        # as an unverifiable case.
                        raise TimeoutError("fixture transport unavailable")
                    else:
                        value = asdict(loop_compare.p.VerificationResult(
                            verdict="unresolved", rationale="",
                            evidence_verdict="unresolved",
                            world_verdict="unresolved", world_rationale=""))
                else:
                    material = payload["material"]
                    target = payload["target"]
                    span = loop_compare.p.Span(
                        material["version_id"], 0,
                        len(material["content"]), material["content"])
                    value = asdict(loop_compare.p.Analysis(fragments=(
                        loop_compare.p.Fragment(
                            f"{material['version_id']}:fixture",
                            material["content"], span, target["id"]),)))
                output_text = json.dumps(value, ensure_ascii=False)
                return argparse.Namespace(
                    id=f"fixture-response-{next(response_sequence)}",
                    model="fixture-actual",
                    usage=argparse.Namespace(
                        prompt_tokens=1, completion_tokens=1),
                    choices=[argparse.Namespace(
                        finish_reason="stop",
                        message=argparse.Namespace(
                            content=output_text, refusal=None))])

        def fake(args):
            calls.append((args.semantic_mode, args.execution_profile,
                          args.reasoning_effort, args.max_rounds,
                          args.reuse_from))
            with patch.object(loop_compare, "BudgetClient",
                              OracleBudgetClient):
                return real_run(args)
        return fake

    def _produce_fake_run(self, name):
        calls = []
        output = self.inputs.parent / name
        with (patch.object(historical.loop_compare, "run",
                           side_effect=self._fake_arm(calls)),
              patch.object(historical, "git_state",
                           return_value=self._clean_git()),
              patch.dict(os.environ, {
                  "OPENAI_API_KEY": "configured",
                  "ACCURACY_TRACING_ALLOW_MODEL_CALLS": "1",
              }, clear=True)):
            self.assertEqual(1, historical.run(self._args(output=str(output))))
        return output, calls

    def test_completed_rows_are_call_trace_and_payload_bound(self):
        output, _ = self._produce_fake_run("integrity-run")
        call_path = output / "staged" / "case-1-loop-calls.json"
        results_path = output / "staged" / "results.json"
        trace_path = output / "staged" / "case-1-loop-trace.json"
        original_calls = call_path.read_bytes()
        original_results = results_path.read_bytes()
        original_trace = trace_path.read_bytes()

        # A self-consistent zero-usage rewrite must not turn a handwritten
        # prediction into a completed, scored case.
        rows = json.loads(original_results)
        row = next(item for item in rows
                   if item["id"] == "case-1" and item["variant"] == "loop")
        row["usage"] = {"model_calls": 0, "input_tokens": 0,
                        "output_tokens": 0, "seconds": 0}
        row["actual_new_api_usage"] = {
            "model_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._write(results_path, rows)
        self._write(call_path, [])
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "successful model call"):
            historical.score(self._args(run=str(output), output=None))
        results_path.write_bytes(original_results)
        call_path.write_bytes(original_calls)

        # The raw prediction must be the deterministic presentation of the
        # checksummed trace, not merely agree with the top-level summary.
        rows = json.loads(original_results)
        row = next(item for item in rows
                   if item["id"] == "case-1" and item["variant"] == "loop")
        row["prediction"]["decision"] = "false"
        self._write(results_path, rows)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "deterministic trace"):
            historical.score(self._args(run=str(output), output=None))
        results_path.write_bytes(original_results)

        rows = json.loads(original_results)
        row = next(item for item in rows
                   if item["id"] == "case-1" and item["variant"] == "loop")
        row["status"] = "error"
        row["error_type"] = "ForgedBaselineDowngrade"
        self._write(results_path, rows)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "offline replay assessment status"):
            historical.score(self._args(run=str(output), output=None))
        results_path.write_bytes(original_results)

        forged_trace = json.loads(original_trace)
        forged_trace["stop_reason"] = "self_consistent_but_not_from_outputs"
        self._write(trace_path, forged_trace)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "offline replay of model call"):
            historical.score(self._args(run=str(output), output=None))
        trace_path.write_bytes(original_trace)

        # Rehashing a leaked payload cannot hide retrieval-time metadata.
        records = json.loads(original_calls)
        payload = json.loads(records[0]["user"])
        payload["retrieved_at"] = "2026-09-05T00:00:00Z"
        records[0]["user"] = json.dumps(payload, sort_keys=True)
        records[0]["user_payload_sha256"] = _digest(records[0]["user"])
        records[0]["request_digest"] = historical.digest(
            [records[0]["system"], records[0]["user"]])
        self._write(call_path, records)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "forbidden retrieved_at"):
            historical.score(self._args(run=str(output), output=None))
        call_path.write_bytes(original_calls)

        records = json.loads(original_calls)
        records[0]["usage"]["output_tokens"] = (
            records[0]["max_completion_tokens"] + 1)
        self._write(call_path, records)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "requested output-token cap"):
            historical.score(self._args(run=str(output), output=None))
        call_path.write_bytes(original_calls)

        rows = json.loads(original_results)
        row = next(item for item in rows
                   if item["id"] == "case-1" and item["variant"] == "loop")
        row["usage"]["seconds"] = loop_compare.EQUAL_V1_BUDGET.seconds + 1
        self._write(results_path, rows)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "wall-time cap"):
            historical.score(self._args(run=str(output), output=None))

        with self.assertRaisesRegex(ValueError, "exactly one actual model"):
            historical._validate_actual_model_sets({
                "monolithic": set(), "staged": set()})

    def test_transport_failure_with_or_without_trace_is_replayed(self):
        output, _ = self._produce_fake_run("transport-failure-run")
        arm = output / "monolithic"
        rows = json.loads((arm / "results.json").read_text())
        row = next(item for item in rows
                   if item["id"] == "case-2"
                   and item["variant"] == "loop")
        self.assertEqual("error", row["status"])
        self.assertEqual("TimeoutError", row["error_type"])
        records = json.loads((arm / "case-2-loop-calls.json").read_text())
        self.assertEqual("TimeoutError", records[-1]["error_type"])
        trace_path = arm / "case-2-loop-trace.json"
        trace = json.loads(trace_path.read_text())
        self.assertFalse(trace["assessment_valid"])
        self.assertEqual("TimeoutError",
                         trace["execution_failure"]["error_type"])
        self.assertEqual(records[-1]["sequence"],
                         trace["execution_failure"]
                         ["failed_call_sequence"])
        self.assertEqual(0, historical.score(
            self._args(run=str(output), output=None)))

        # Simulate the process failing after the call log was persisted but
        # before its invalid trace was written.  A sidecar alone is not
        # trusted: score accepts it only because replaying these exact calls
        # deterministically reconstructs the same invalid failure.
        trace_path.unlink()
        historical.write(
            arm / "case-2-loop-failure.json",
            loop_compare.missing_trace_failure(row["error_type"], records))
        row["prediction"] = None
        row["checkpoints"] = []
        self._write(arm / "results.json", rows)
        top = historical._normalized_arm(
            "monolithic", arm, self.input_data["cases"], return_code=1)
        results_path = output / "results.json"
        results = json.loads(results_path.read_text())
        results["arms"][0] = top
        self._write(results_path, results)
        historical._write_raw_artifact_manifest(output)
        self.assertEqual(0, historical.score(
            self._args(run=str(output), output=None)))
        scores = json.loads((output / "scores.json").read_text())
        scored = next(item for item in scores["cases"]
                      if item["id"] == "case-2")
        self.assertEqual("unverifiable",
                         scored["monolithic"]["decision"])
        self.assertEqual("TimeoutError",
                         scored["monolithic"]["error_type"])

    def test_call_budget_exhaustion_is_replayed_and_scored(self):
        constrained = loop_compare.Budget(
            calls=8, output_tokens=64000,
            per_call_output_tokens=8000, seconds=1800)
        with patch.object(loop_compare, "EQUAL_V1_BUDGET", constrained):
            output, _ = self._produce_fake_run("budget-failure-run")
            staged_rows = json.loads(
                (output / "staged" / "results.json").read_text())
            exhausted = [row for row in staged_rows
                         if row["status"] == "error"
                         and row.get("error_type") == "StagedSemanticError"]
            self.assertTrue(exhausted)
            row = exhausted[0]
            suffix = ("full" if row["variant"] == "full_evidence_once"
                      else "loop")
            trace = json.loads((
                output / "staged" /
                f"{row['id']}-{suffix}-trace.json").read_text())
            self.assertEqual("StagedSemanticError",
                             trace["execution_failure"]["error_type"])
            self.assertIn("resource budget exhausted",
                          trace["errors"][-1]["message"])
            self.assertIsNone(trace["execution_failure"]
                              ["failed_call_sequence"])
            self.assertEqual(0, historical.score(
                self._args(run=str(output), output=None)))
            scores = json.loads((output / "scores.json").read_text())
            scored = next(item for item in scores["cases"]
                          if item["id"] == row["id"])
            self.assertEqual("unverifiable", scored["staged"]["decision"])
            self.assertEqual("StagedSemanticError",
                             scored["staged"]["error_type"])

    def test_cross_arm_response_reuse_and_call_time_rewrites_are_rejected(self):
        output, _ = self._produce_fake_run("response-integrity-run")
        staged_call_path = (
            output / "staged" / "case-1-loop-calls.json")
        staged_trace_path = (
            output / "staged" / "case-1-loop-trace.json")
        original_calls = staged_call_path.read_bytes()
        original_trace = staged_trace_path.read_bytes()
        staged_rows = json.loads(
            (output / "staged" / "results.json").read_text())
        row = next(item for item in staged_rows
                   if item["id"] == "case-1" and item["variant"] == "loop")

        records = json.loads(original_calls)
        records[0]["seconds"] = row["usage"]["seconds"] + 1
        self._write(staged_call_path, records)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "Cumulative call seconds"):
            historical.score(self._args(run=str(output), output=None))
        staged_call_path.write_bytes(original_calls)

        monolithic_records = json.loads((
            output / "monolithic" / "case-1-loop-calls.json").read_text())
        records = json.loads(original_calls)
        records[0]["response_id"] = monolithic_records[0]["response_id"]
        self._write(staged_call_path, records)
        outer = json.loads((output / "config.json").read_text())
        replayed = historical._offline_replay_trace(
            self.input_data["cases"][0], "loop", "staged",
            outer["trace_config"], outer["max_inner_repairs"]["staged"],
            records, outer["model"], outer["reasoning_effort"],
            outer["budget"])
        historical.write(staged_trace_path, replayed)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "reuse any API response_id"):
            historical.score(self._args(run=str(output), output=None))
        staged_call_path.write_bytes(original_calls)
        staged_trace_path.write_bytes(original_trace)

    def test_runs_equal_profile_sequentially_and_scores_every_error(self):
        calls = []
        output = self.inputs.parent / "run"
        with (patch.object(historical.loop_compare, "run",
                           side_effect=self._fake_arm(calls)),
              patch.object(historical, "git_state",
                           return_value=self._clean_git()),
              patch.dict(os.environ, {
                  "OPENAI_API_KEY": "configured",
                  "ACCURACY_TRACING_ALLOW_MODEL_CALLS": "1",
              }, clear=True)):
            self.assertEqual(1, historical.run(self._args(output=str(output))))
        self.assertEqual([
            ("monolithic", "equal-v1", "high", 5, None),
            ("staged", "equal-v1", "high", 5, None),
        ], calls)
        config = json.loads((output / "config.json").read_text())
        self.assertTrue(config["sequential_arms"])
        self.assertEqual("equal-v1", config["execution_profile"])
        self.assertEqual("high", config["reasoning_effort"])
        self.assertFalse(config["model_retrieved_at_exposed"])
        self.assertFalse(config["reuse_allowed"])

        self.assertEqual(0, historical.score(self._args(run=str(output),
                                                        output=None)))
        scores = json.loads((output / "scores.json").read_text())
        self.assertEqual(0, scores["paired_metrics"]["accuracy"]["monolithic"])
        self.assertEqual(0, scores["paired_metrics"]["accuracy"]["staged"])
        self.assertEqual(0, scores["paired_metrics"]["false_recall"]["monolithic"])
        self.assertEqual(0, scores["paired_metrics"]["false_recall"]["staged"])
        self.assertEqual(1, scores["paired_metrics"]["abstention_rate"]["monolithic"])
        self.assertEqual(1, scores["paired_metrics"]["completion_rate"]["staged"])
        errored = scores["cases"][1]["monolithic"]
        self.assertEqual("unverifiable", errored["decision"])
        self.assertEqual("TimeoutError", errored["error_type"])
        self.assertEqual("fixture-actual",
                         scores["actual_models"]["monolithic"][0])
        limits = " ".join(scores["limits"])
        self.assertIn("recorded dataset declaration", limits)
        self.assertIn("cannot authenticate", limits)
        self.assertIn("actually returned by the model API", limits)
        self.assertGreater(scores["resource_usage_by_arm"]["staged"]
                           ["main_cases"]["actual_new_api"]["model_calls"], 0)
        self.assertGreater(scores["resource_usage_by_arm"]["staged"]
                           ["full_evidence_controls"]["actual_new_api"]
                           ["model_calls"], 0)
        self.assertEqual("semantic_failure_with_full_evidence",
                         scores["full_evidence_control_diagnostics"][0]
                         ["arms"]["staged"]["diagnosis"])

        raw_call = output / "staged" / "case-1-loop-calls.json"
        original_call = raw_call.read_bytes()
        raw_call.write_bytes(original_call + b" ")
        with self.assertRaisesRegex(ValueError, "artifact sha256"):
            historical.score(self._args(run=str(output), output=None))
        raw_call.write_bytes(original_call)

        top_results_path = output / "results.json"
        original_top = top_results_path.read_bytes()
        changed_top = json.loads(original_top)
        changed_top["arms"][1]["cases"][0]["decision"] = "false"
        self._write(top_results_path, changed_top)
        with self.assertRaisesRegex(ValueError, "derived results"):
            historical.score(self._args(run=str(output), output=None))
        top_results_path.write_bytes(original_top)

        calls_value = json.loads(raw_call.read_text())
        calls_value[0]["cached_from"] = "prior"
        self._write(raw_call, calls_value)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "forbids replayed calls"):
            historical.score(self._args(run=str(output), output=None))
        raw_call.write_bytes(original_call)
        historical._write_raw_artifact_manifest(output)

        staged_logs = list((output / "staged").glob("*-calls.json"))
        staged_traces = list((output / "staged").glob("*-trace.json"))
        staged_original = {
            path: path.read_bytes() for path in staged_logs + staged_traces}
        for path in staged_logs:
            value = json.loads(path.read_text())
            for record in value:
                record["actual_model"] = "different-actual-model"
            self._write(path, value)
        outer = json.loads((output / "config.json").read_text())
        staged_rows = json.loads(
            (output / "staged" / "results.json").read_text())
        input_cases = {case["target"]["id"]: case
                       for case in self.input_data["cases"]}
        for row in staged_rows:
            if row["status"] != "completed":
                continue
            suffix = ("full" if row["variant"] == "full_evidence_once"
                      else "loop")
            log_path = (output / "staged" /
                        f"{row['id']}-{suffix}-calls.json")
            trace = historical._offline_replay_trace(
                input_cases[row["id"]], row["variant"], "staged",
                outer["trace_config"], outer["max_inner_repairs"]["staged"],
                json.loads(log_path.read_text()), outer["model"],
                outer["reasoning_effort"], outer["budget"])
            historical.write(
                output / "staged" / f"{row['id']}-{suffix}-trace.json",
                trace)
        historical._write_raw_artifact_manifest(output)
        with self.assertRaisesRegex(ValueError, "same actual model"):
            historical.score(self._args(run=str(output), output=None))
        for path, value in staged_original.items():
            path.write_bytes(value)
        historical._write_raw_artifact_manifest(output)

        # Even a self-consistent post-run rewrite of gold plus freeze cannot be
        # scored, because inference blindly committed to the original manifest.
        self.gold_data["cases"][0]["decision"] = "false"
        self._write_data()
        with self.assertRaisesRegex(ValueError, "frozen benchmark"):
            historical.score(self._args(run=str(output), output=None))

    def test_equal_v1_contract_and_reuse_key_include_reasoning_trace_profile(self):
        mono = loop_compare.execution_contract(
            argparse.Namespace(execution_profile="equal-v1", max_rounds=5),
            "monolithic")
        staged = loop_compare.execution_contract(
            argparse.Namespace(execution_profile="equal-v1", max_rounds=5),
            "staged")
        self.assertEqual(mono, staged)

        first = self.inputs.parent / "first-arm"
        base = argparse.Namespace(
            inputs=str(self.inputs), output=str(first), model="fixture-model",
            reasoning_effort="low", max_rounds=5, reuse_from=None,
            semantic_mode="monolithic", max_repairs=1,
            execution_profile="equal-v1")
        with patch.dict(loop_compare.os.environ, {}, clear=True):
            self.assertEqual(2, loop_compare.run(base))
        config = json.loads((first / "config.json").read_text())
        self.assertEqual("low", config["reasoning_effort"])
        self.assertEqual(mono[2].max_documents,
                         config["trace_config"]["max_documents"])

        for field, value in (("reasoning_effort", "high"),
                             ("max_rounds", 4),
                             ("execution_profile", "legacy-v03")):
            changed = deepcopy(vars(base))
            changed.update(output=str(self.inputs.parent / f"changed-{field}"),
                           reuse_from=str(first), **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "identical inputs"):
                loop_compare.run(argparse.Namespace(**changed))

    def test_loop_runner_passes_reasoning_to_every_budget_client(self):
        seen = []

        class FakeClient:
            def __init__(self, model, budget, transport=None,
                         reasoning_effort=None):
                seen.append(reasoning_effort)
                self.model, self.budget = model, budget
                self.reasoning_effort = reasoning_effort
                self.records, self.calls = [], 0
                self.start = 0

            def usage(self):
                return {"model_calls": 0, "input_tokens": 0,
                        "output_tokens": 0, "seconds": 0}

        output = self.inputs.parent / "reasoning-arm"
        args = argparse.Namespace(
            inputs=str(self.inputs), output=str(output), model="fixture-model",
            reasoning_effort="high", max_rounds=5, reuse_from=None,
            semantic_mode="monolithic", max_repairs=1,
            execution_profile="equal-v1")
        report = {"assessment_valid": True}
        with (patch.object(loop_compare, "BudgetClient", FakeClient),
              patch.object(loop_compare.p, "run_provenance", return_value=report),
              patch.object(loop_compare, "round_decisions", return_value=[]),
              patch.object(loop_compare, "present_decision", return_value={
                  "decision": "unverifiable", "assessment_mode": "evidence"}),
              patch.dict(loop_compare.os.environ,
                         {"OPENAI_API_KEY": "configured"}, clear=True)):
            self.assertEqual(0, loop_compare.run(args))
        self.assertEqual(["high", "high", "high"], sorted(seen))

    def test_completed_invalid_prediction_becomes_error_and_unverifiable(self):
        arm = self.inputs.parent / "invalid-prediction-arm"
        arm.mkdir()
        rows = []
        for index, case in enumerate(self.input_data["cases"]):
            rows.append({
                "id": case["target"]["id"], "variant": "loop",
                "status": "completed", "checkpoints": [],
                "prediction": (None if index == 0 else {
                    "decision": "true", "assessment_mode": "world"}),
                "usage": {"model_calls": 0, "input_tokens": 0,
                          "output_tokens": 0, "seconds": 0},
                "actual_new_api_usage": {"model_calls": 0,
                                         "input_tokens": 0,
                                         "output_tokens": 0},
            })
        historical.write(arm / "results.json", rows)
        historical.write(arm / "status.json", {"status": "has_errors"})
        normalized = historical._normalized_arm(
            "monolithic", arm, self.input_data["cases"], return_code=1)
        for row in normalized["cases"]:
            self.assertEqual("error", row["status"])
            self.assertEqual("unverifiable", row["decision"])
            self.assertEqual("InvalidPrediction", row["error_type"])

    def test_nonfinite_usage_and_json_numbers_are_rejected(self):
        base = {"model_calls": 1, "input_tokens": 1, "output_tokens": 1}
        for seconds in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(
                    ValueError, "seconds must be nonnegative"):
                historical._validated_usage(
                    {**base, "seconds": seconds}, "fixture usage")
        value = self.inputs.parent / "nonfinite.json"
        value.write_text('{"seconds": NaN}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Non-finite JSON number"):
            historical._json(value)


if __name__ == "__main__":
    unittest.main()
