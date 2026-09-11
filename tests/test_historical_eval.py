"""Offline historical-scoring regressions using temporary, synthetic artifacts only.

No private archive, live model, credentials, or network is used. The synthetic
manifests deliberately emulate successful transport metadata to exercise the
scorer; their outputs are not experimental evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCORER_PATH = ROOT / "experiments/historical-cutoff-20260908/summarize_test.py"
SCORER = runpy.run_path(str(SCORER_PATH))
audit_exposure = SCORER["audit_exposure"]
summarize = SCORER["summarize"]
sha = SCORER["sha"]
CUTOFF = "2023-12-31T23:59:59Z"
QUOTE = "The synthetic article reports seven observations."
SOURCE = {
    "version_id": "synthetic-source",
    "url": "https://example.test/offline-fixture",
    "issuer": "Synthetic test publisher",
    "content": QUOTE + "\n" + "测试 evidence. " * 90 + "End of synthetic source.",
    "published_at": "2020-01-01T00:00:00Z",
    "retrieved_at": "2020-01-02T00:00:00Z",
    "available_at": "2020-01-01T00:00:00Z",
    "availability_basis": "Invented dates for an offline regression fixture.",
}


def catalog_entry(source):
    entry = {key: source[key] for key in (
        "version_id", "url", "issuer", "published_at", "available_at"
    )}
    entry["preview"] = source["content"][:800]
    return entry


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


class SyntheticBatch:
    """A complete paired fixture, never written into an experiment directory."""

    def __init__(self, root):
        self.out = root / "synthetic-results"
        self.gold_path = root / "synthetic-gold.json"
        self.temporal = "OFFLINE TEST: use supplied evidence through " + CUTOFF
        self.cases = []
        labels = []
        for role, claim, expected, future in (
            ("authenticity", "The reported observations were genuinely measured.",
             "unresolved", "contradicted"),
            ("attribution_control", "The article reports seven observations.",
             "supported", "supported"),
        ):
            cid = "synthetic-" + role
            self.cases.append({"target": {"id": cid, "text": claim, "as_of": CUTOFF,
                                         "source_version_id": SOURCE["version_id"]},
                               "materials": [deepcopy(SOURCE)]})
            labels.append({"id": cid, "event_family": "synthetic-family",
                           "role": role, "variant": "original",
                           "cutoff_expected": expected, "future_expected": future})
        self.gold = {"evidence_cutoff": CUTOFF, "event_families": ["synthetic-family"],
                     "cases": labels}
        write(self.out / "corpus.json", {"fixture_kind": "offline synthetic", "cases": self.cases})
        write(self.gold_path, self.gold)
        corpus_hash = sha(self.out / "corpus.json")
        write(self.out / "preflight.json", {"corpus_sha256": corpus_hash})
        self.registration = {
            "corpus_sha256": corpus_hash, "gold_sha256": sha(self.gold_path),
            "scorer_sha256": sha(SCORER_PATH), "helper_sha256": sha(SCORER["HELPER_PATH"]),
            "registered_at": "2026-01-01T00:00:00+00:00",
        }
        frozen = self.out / "frozen-inputs/synthetic-worker.txt"
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_text("Offline fixture; no worker or model was invoked.\n")
        # False is required by the scorer's real-batch gate, not a claim that
        # these test-created receipts came from an actual model invocation.
        self.manifest = {
            "fixture_kind": "offline synthetic regression fixture; no inference",
            "test_stub": False, "gold_loaded": False, "worker_exit_code": 0,
            "frozen_integrity": {"synthetic-worker.txt": True},
            "frozen_code_sha256": {"synthetic-worker.txt": sha(frozen)},
            "corpus_sha256": corpus_hash, "review_sha256": sha(self.out / "preflight.json"),
            "case_count": len(self.cases), "model": "gpt-6-astra",
            "reasoning_effort": "medium", "temporal_instruction": self.temporal,
            "started_at": "2026-01-01T00:00:01+00:00",
        }
        self.runs = [self.make_run(case, label, arm)
                     for case, label in zip(self.cases, labels)
                     for arm in ("direct", "double_loop")]
        self.save_registration()
        self.save_runs()

    def make_run(self, case, label, arm):
        output = {"verdict": label["cutoff_expected"], "basis": [],
                  "rationale": "Synthetic source does not establish data authenticity."}
        if label["role"] == "attribution_control":
            output.update(basis=[{"version_id": SOURCE["version_id"], "quote": QUOTE}],
                          rationale="Synthetic source explicitly reports seven observations.")
        call = {"stage": "direct" if arm == "direct" else "verify",
                "success": True, "status": "completed", "model": "gpt-6-astra",
                "reasoning_effort": "medium", "tunnel": "local", "timeout_seconds": 90,
                "wall_seconds": 1.0, "local_skills_disabled": True,
                "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 0}}
        run = {"id": case["target"]["id"], "condition": arm, "route": "local",
               "fact_status": output["verdict"], "errors": [], "calls": [call],
               "timer_seconds": 1.0, "utc_elapsed_seconds": 1.0}
        if arm == "direct":
            run["raw_response"] = output
        else:
            response = {**output, "gaps": [], "resolutions": []}
            run["report"] = {
                "verification_history": [{**deepcopy(response), "round": 1}],
                "analysis_history": [], "operations": [], "gaps": [],
                "execution": {"model_io": [{"instructions": "Synthetic verification request.",
                    "packet": {"target": case["target"], "materials": case["materials"]},
                    "schema": {"type": "object"}, "response": response}]},
            }
        return run

    def save_registration(self):
        write(self.out / "registration.json", self.registration)
        self.manifest["registration_sha256"] = sha(self.out / "registration.json")
        write(self.out / "manifest.json", self.manifest)

    def folder(self, run):
        return self.out / "stage-artifacts" / run["id"] / run["condition"]

    def save_runs(self):
        write(self.out / "stage-artifacts/predictions.json",
              {"test_stub": False, "gold_loaded": False, "results": self.runs})
        for run in self.runs:
            folder = self.folder(run)
            write(folder / "result.json", run)
            for ordinal, call in enumerate(run["calls"], 1):
                stem = folder / f"{ordinal:02d}-{call['stage']}"
                if run["condition"] == "direct":
                    case = next(case for case in self.cases if case["target"]["id"] == run["id"])
                    item = {"instructions": self.temporal + "\nSynthetic direct request.",
                            "packet": {"target": case["target"], "materials": case["materials"]},
                            "schema": {"type": "object"}}
                    response = run["raw_response"]
                else:
                    audit = run["report"]["execution"]["model_io"][ordinal - 1]
                    item = {key: deepcopy(audit[key]) for key in ("instructions", "packet", "schema")}
                    item["instructions"] = self.temporal + "\n" + item["instructions"]
                    response = audit["response"]
                write(stem.with_suffix(".input.json"), item)
                write(stem.with_suffix(".calls.json"), [call])
                write(stem.with_suffix(".response.json"), response)


class HistoricalEvaluationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="historical-offline-test-")
        self.addCleanup(temporary.cleanup)
        return SyntheticBatch(Path(temporary.name))

    def test_exposure_checks_nested_full_sources_and_exact_800_character_previews(self):
        case = {"materials": [deepcopy(SOURCE)]}
        entry = catalog_entry(SOURCE)
        self.assertEqual(len(entry["preview"]), 800)
        self.assertGreater(len(entry["preview"].encode("utf-8")), 800)
        packet = {"history": [{"materials": [deepcopy(SOURCE)]}], "provider": {"catalog": [entry]}}
        self.assertEqual(audit_exposure(packet, case), {
            "full_material_ids": [SOURCE["version_id"]],
            "catalog_preview_ids": [SOURCE["version_id"]],
            "registered_materials_and_previews_only": True,
        })

    def test_exposure_rejects_changed_sources_previews_metadata_and_foreign_ids(self):
        case = {"materials": [deepcopy(SOURCE)]}
        damaged_full = {**SOURCE, "content": SOURCE["content"][:800] + "Changed hidden remainder."}
        packets = [
            ({"materials": [damaged_full]}, "Unregistered material"),
            ({"materials": [{**SOURCE, "version_id": "foreign"}]}, "Unregistered material"),
            ({"catalog": [{**catalog_entry(SOURCE), "preview": SOURCE["content"][:799]}]}, "preview differs"),
            ({"catalog": [{**catalog_entry(SOURCE), "url": "https://example.test/foreign"}]}, "preview differs"),
            ({"catalog": [{**catalog_entry(SOURCE), "published_at": "2025-01-01T00:00:00Z"}]}, "preview differs"),
            ({"catalog": [{**catalog_entry(SOURCE), "version_id": "foreign"}]}, "Unregistered catalog"),
            ({"catalog": [catalog_entry(SOURCE), catalog_entry(SOURCE)]}, "Duplicate catalog"),
            ({"catalog": {}}, "Malformed source catalog"),
        ]
        for packet, message in packets:
            with self.subTest(packet=packet):
                with self.assertRaisesRegex(ValueError, message):
                    audit_exposure({"nested": [packet]}, case)

    def test_scoring_retains_malformed_and_failed_runs_without_abstention_credit(self):
        malformed = {
            "empty_list": [],
            "nonempty_list": [{"verdict": "unresolved"}],
            "nonempty_string": "unresolved",
        }
        for failure in (None, *malformed, "timeout"):
            with self.subTest(failure=failure):
                batch = self.fixture()
                if failure in malformed:
                    # Truthy non-dicts must not survive an `output or {}`
                    # fallback and crash later rationale/field access.
                    batch.runs[0]["raw_response"] = deepcopy(malformed[failure])
                elif failure == "timeout":
                    batch.runs[0]["errors"] = [{"type": "Timeout", "message": "Synthetic failure"}]
                    batch.runs[0]["calls"][0].update(success=False, status="timeout", usage=None)
                batch.save_runs()
                originals = {path: path.read_bytes() for path in batch.out.rglob("*") if path.is_file()}
                summary = summarize(batch.out, batch.gold_path)
                self.assertEqual((summary["cases"], summary["runs"]), (2, 4))
                self.assertEqual(len(summary["rows"]), 4)
                direct = summary["scores_by_variant"]["original"]["direct"]
                self.assertEqual(direct["cases"], 2)
                self.assertEqual(direct["cutoff_matches"], 2 if failure is None else 1)
                self.assertEqual(direct["authenticity_abstentions"], int(failure is None))
                row = summary["rows"][0]
                self.assertEqual(row["pipeline_success"], failure is None)
                self.assertFalse(row["future_verdict_match"])
                self.assertFalse(row["called_later_false_claim_false"])
                if failure:
                    self.assertFalse(row["cutoff_match"])
                    self.assertFalse(row["abstained"])
                if failure in malformed:
                    self.assertEqual(row["final_output"], {})
                    self.assertIsNone(row["rationale"])
                if failure == "timeout":
                    self.assertIsNone(summary["conditions"]["direct"]["total_tokens"])
                self.assertEqual(summary["scores_by_variant"]["original"]["double_loop"]["cutoff_matches"], 2)
                self.assertTrue((batch.out / "SUMMARY.json").is_file())
                receipts = json.loads((batch.out / "SANITIZED_RECEIPTS.json").read_text())["receipts"]
                self.assertEqual(len(receipts), 4)
                self.assertTrue(all(receipt["response_sha256"] for receipt in receipts))
                self.assertEqual({path: path.read_bytes() for path in originals}, originals)

    def test_incomplete_or_duplicate_pairs_and_gold_denominators_are_rejected(self):
        for mutation, message in (("missing", "Missing or duplicate condition"),
                                  ("duplicate", "Missing or duplicate condition"),
                                  ("case_count", "Case denominator mismatch"),
                                  ("gold_missing", "Gold denominator mismatch")):
            with self.subTest(mutation=mutation):
                batch = self.fixture()
                if mutation == "missing":
                    batch.runs.pop()
                elif mutation == "duplicate":
                    batch.runs[-1] = deepcopy(batch.runs[0])
                elif mutation == "case_count":
                    batch.manifest["case_count"] += 1
                else:
                    batch.gold["cases"].pop()
                    write(batch.gold_path, batch.gold)
                    batch.registration["gold_sha256"] = sha(batch.gold_path)
                batch.save_registration()
                batch.save_runs()
                with self.assertRaisesRegex(ValueError, message):
                    summarize(batch.out, batch.gold_path)

    def test_registered_gold_and_scorer_dependencies_cannot_silently_change(self):
        for mutation, message in (("gold", "Prespecified gold changed after launch"),
                                  ("scorer_sha256", "Scorer changed after registration"),
                                  ("helper_sha256", "Imported scoring helper changed after registration")):
            with self.subTest(mutation=mutation):
                batch = self.fixture()
                if mutation == "gold":
                    batch.gold["cases"][0]["cutoff_expected"] = "supported"
                    write(batch.gold_path, batch.gold)
                else:
                    # Simulate a stale code commitment without editing frozen
                    # code or any shared workspace file.
                    batch.registration[mutation] = "0" * 64
                    batch.save_registration()
                with self.assertRaisesRegex(ValueError, message):
                    summarize(batch.out, batch.gold_path)

    def test_scored_answers_must_match_recorded_model_response_sidecars(self):
        for mutation, message in (("missing", "Successful call is missing its model response"),
                                  ("direct", "Scored direct answer differs from its response receipt"),
                                  ("harness_receipt", "Harness report response differs from its receipt"),
                                  ("harness_final", "Scored harness verdict differs from its final model response")):
            with self.subTest(mutation=mutation):
                batch = self.fixture()
                if mutation in ("missing", "direct"):
                    response_path = batch.folder(batch.runs[0]) / "01-direct.response.json"
                    if mutation == "missing":
                        response_path.unlink()
                    else:
                        write(response_path, {**batch.runs[0]["raw_response"], "rationale": "Changed response."})
                elif mutation == "harness_receipt":
                    write(batch.folder(batch.runs[1]) / "01-verify.response.json", {})
                else:
                    batch.runs[1]["report"]["verification_history"][-1]["rationale"] = "Changed scored rationale."
                    batch.save_runs()
                with self.assertRaisesRegex(ValueError, message):
                    summarize(batch.out, batch.gold_path)


if __name__ == "__main__":
    unittest.main()
