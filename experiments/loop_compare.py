"""Fixed-contract single-round checkpoints versus continued loops, with full-evidence control.

Inference never reads gold. Each first-round result is the literal shared prefix
of its continued run, not a separately sampled baseline or the old agent score.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from newsverify import provenance as p
from newsverify.decisions import present_decision, round_decisions
from newsverify.retrieval import SnapshotSearchProvider
from model_io import (Budget, BudgetClient, PriorResponseCache,
                      ResourceBudgetError, digest, write)
from semantic_adapter import Decomposer as MonolithicDecomposer, Verifier as MonolithicVerifier
from staged_semantic import StagedDecomposer, StagedVerifier
from prompt_specs import prompt_manifest

MONOLITHIC_BUDGET = Budget(calls=24, output_tokens=36000,
                           per_call_output_tokens=2500, seconds=600)
STAGED_BUDGET = Budget(calls=128, output_tokens=480000,
                       per_call_output_tokens=8000, seconds=1800)
# A causal prompt-architecture comparison must not silently grant one arm a
# larger model or trace allowance.  The legacy v0.3 settings above remain the
# default for the original experiment, while historical_compare explicitly
# selects this shared profile for both arms.
EQUAL_V1_BUDGET = Budget(calls=128, output_tokens=480000,
                         per_call_output_tokens=8000, seconds=1800)
EQUAL_V1_TRACE_CAPS = {"max_documents": 18,
                       "max_decomposition_calls": 18}
# Backwards-compatible import for external experiment helpers.
BUDGET = MONOLITHIC_BUDGET


def model_call_lineage(records):
    """Canonical trace commitment to the exact requests and API responses."""
    return {
        "schema_version": 1,
        "call_artifact_sha256": digest(records),
        "responses": [
            {"sequence": record["sequence"],
             "response_id": record["response_id"],
             "output_sha256": record["output_sha256"]}
            for record in records
            if all(key in record for key in (
                "response_id", "output_sha256", "usage"))
            and "error_type" not in record
        ],
    }


def execution_failure_binding(report, records):
    """Bind an invalid trace to its deterministic error and exact call log.

    Provider/model failures are normally converted into an invalid provenance
    report by the engine.  Keeping the underlying failed call (when one
    exists) next to the trace error prevents a scorer from treating a
    successful replay as a generic, unverified ``error`` row.
    """
    if report.get("assessment_valid") is True:
        return None
    trace_errors = report.get("errors")
    if not isinstance(trace_errors, list) or not trace_errors:
        raise ValueError("Invalid assessment is missing its trace error")
    trace_error = trace_errors[-1]
    if (not isinstance(trace_error, dict)
            or not isinstance(trace_error.get("stage"), str)
            or not isinstance(trace_error.get("type"), str)):
        raise ValueError("Invalid assessment has a malformed trace error")
    failed = next((record for record in reversed(records)
                   if isinstance(record, dict)
                   and isinstance(record.get("error_type"), str)), None)
    return {
        "schema_version": 1,
        "error_type": (failed["error_type"] if failed
                       else trace_error["type"]),
        "trace_stage": trace_error["stage"],
        "trace_error_type": trace_error["type"],
        "call_artifact_sha256": digest(records),
        "failed_call_sequence": (failed.get("sequence") if failed else None),
        "failed_call_error_type": (failed["error_type"] if failed else None),
    }


def missing_trace_failure(error_type, records):
    """Create a checksummed fallback when a case fails before trace write."""
    failed = next((record for record in reversed(records)
                   if isinstance(record, dict)
                   and isinstance(record.get("error_type"), str)), None)
    effective = failed["error_type"] if failed else error_type
    return {
        "schema_version": 1,
        "status": "error",
        "error_type": effective,
        "call_artifact_sha256": digest(records),
        "failed_call_sequence": (failed.get("sequence") if failed else None),
        "failed_call_error_type": (failed["error_type"] if failed else None),
    }


def source_hashes():
    """Hash the exact Python implementation admitted to a comparison run."""
    return {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
            for base in [ROOT / "newsverify", ROOT / "experiments"]
            for f in sorted(base.glob("*.py"))}


def execution_contract(args, semantic_mode):
    """Resolve immutable per-arm resource caps for a named profile."""
    profile = getattr(args, "execution_profile", "legacy-v03")
    if profile == "equal-v1":
        budget = EQUAL_V1_BUDGET
        trace = p.TraceConfig(max_rounds=args.max_rounds,
                              **EQUAL_V1_TRACE_CAPS)
    elif profile == "legacy-v03":
        budget = (STAGED_BUDGET if semantic_mode == "staged"
                  else MONOLITHIC_BUDGET)
        trace = p.TraceConfig(
            max_rounds=args.max_rounds,
            max_documents=8 if semantic_mode == "staged" else 18,
            max_decomposition_calls=8 if semantic_mode == "staged" else 18,
        )
    else:
        raise ValueError("execution_profile must be legacy-v03 or equal-v1")
    return profile, budget, trace


def load_inputs(path):
    data = json.loads(Path(path).read_text())
    if set(data) != {"schema_version", "cases"} or data["schema_version"] != 1:
        raise ValueError("Inference input only accepts schema_version and cases")
    seen = set()
    for case in data["cases"]:
        if set(case) != {"target", "materials", "seed_ids", "full_evidence_control"}:
            raise ValueError("Unexpected case field; gold must be separate")
        t = case["target"]
        if set(t) != {"id", "text", "as_of", "source_version_id", "assessment_mode", "evidence_scope"}:
            raise ValueError("Unexpected target contract field")
        if t["id"] in seen: raise ValueError("Duplicate case")
        seen.add(t["id"])
        for raw in case["materials"]:
            p.MaterialVersion(**raw)
    return data


def run(args):
    data = load_inputs(args.inputs)
    # Programmatic callers created before staged mode keep legacy semantics;
    # the current CLI explicitly supplies its staged default.
    semantic_mode = getattr(args, "semantic_mode", "monolithic")
    if semantic_mode not in {"monolithic", "staged"}:
        raise ValueError("semantic_mode must be monolithic or staged")
    requested_repairs = getattr(args, "max_repairs", 1)
    if type(requested_repairs) is not int or requested_repairs not in (0, 1):
        raise ValueError("max_repairs must be 0 or 1")
    max_repairs = requested_repairs if semantic_mode == "staged" else 0
    profile, budget, trace_config = execution_contract(args, semantic_mode)
    reasoning_effort = getattr(args, "reasoning_effort", None)
    if reasoning_effort is not None and (type(reasoning_effort) is not str
                                         or not reasoning_effort.strip()):
        raise ValueError("reasoning_effort must be a nonempty string or null")
    source_manifest_sha256 = getattr(args, "source_manifest_sha256", None)
    if source_manifest_sha256 is not None and (
            type(source_manifest_sha256) is not str
            or len(source_manifest_sha256) != 64
            or any(ch not in "0123456789abcdef"
                   for ch in source_manifest_sha256)):
        raise ValueError("source_manifest_sha256 must be lowercase sha256 or null")
    git_commit = getattr(args, "git_commit", None)
    if git_commit is not None and (type(git_commit) is not str
                                   or not git_commit.strip()):
        raise ValueError("git_commit must be a nonempty string or null")
    reuse = Path(args.reuse_from) if getattr(args, "reuse_from", None) else None
    if reuse:
        old = json.loads((reuse / "config.json").read_text())
        if (old["input_sha256"] != hashlib.sha256(Path(args.inputs).read_bytes()).hexdigest()
                or old["model"] != args.model or old["budget"] != asdict(budget)
                or old.get("reasoning_effort") != reasoning_effort
                or old.get("execution_profile") != profile
                or old.get("trace_config") != asdict(trace_config)
                or old.get("source_manifest_sha256") != source_manifest_sha256
                or old.get("git_commit") != git_commit
                or old.get("semantic_mode", "monolithic") != semantic_mode
                or old.get("max_inner_repairs", 0) != max_repairs
                or (semantic_mode == "staged"
                    and old.get("prompt_manifest") != prompt_manifest())):
            raise ValueError("Cached run must have identical inputs, model, reasoning, execution profile, trace caps, prompt mode, repairs, and resource caps")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    config = {"model": args.model, "reasoning_effort": reasoning_effort,
        "execution_profile": profile, "max_rounds": args.max_rounds,
        "trace_config": asdict(trace_config), "budget": asdict(budget),
        "model_retrieved_at_exposed": False,
        "source_manifest_sha256": source_manifest_sha256,
        "git_commit": git_commit,
        "semantic_mode": semantic_mode, "max_inner_repairs": max_repairs,
        "input_sha256": hashlib.sha256(Path(args.inputs).read_bytes()).hexdigest(),
        "source_sha256": source_hashes(),
        "comparison": "exact first-round checkpoint versus continued loop; same decision function",
        "control": "one-round all-materials control for flagged cases separates access from repeated reasoning",
        "original_agent_reexecuted": False, "gold_access_during_inference": False,
        "actual_spend_equal": False, "input_tokens_capped": False}
    config["prompt_manifest"] = prompt_manifest() if semantic_mode == "staged" else None
    config["reuse_from"] = str(reuse) if reuse else None
    config["cache_rule"] = ("same case/variant and run-level execution-profile/trace-config; "
                            "exact requested-model/reasoning/system/user/schema/"
                            "response-mode/output-cap match; one-shot replay; "
                            "historical time/tokens charged")
    write(out / "config.json", config)
    if not os.environ.get("OPENAI_API_KEY"):
        write(out / "status.json", {"status": "blocked_missing_auth", "model_calls": 0})
        return 2

    def one(case, control=False):
        identifier = case["target"]["id"] + ("-full" if control else "-loop")
        cache = None
        if reuse and (reuse / f"{identifier}-calls.json").exists():
            from openai import OpenAI
            cache = PriorResponseCache(json.loads((reuse / f"{identifier}-calls.json").read_text()), args.model,
                OpenAI(max_retries=0, base_url="https://api.openai.com/v1").chat.completions.create)
        class RecordedClient(BudgetClient):
            def call(self, *a, **kw):
                try: return super().call(*a, **kw)
                finally:
                    if self.records:
                        record = self.records[-1]
                        prior = cache.by_id.get(record.get("response_id")) if cache else None
                        if prior and not record.get("cache_accounted"):
                            self.start -= max(0, prior["seconds"] - record.get("seconds", 0))
                            record.update(cached_from=str(reuse), cache_accounted=True, seconds=prior["seconds"])
                    write(out / f"{identifier}-calls.json", self.records)
                    print(json.dumps({"case": identifier, "calls": self.calls}), flush=True)
                    if self.usage()["seconds"] > self.budget.seconds:
                        raise RuntimeError("Historical plus new wall-time budget exceeded")
        client = RecordedClient(args.model, budget, transport=cache,
                                reasoning_effort=reasoning_effort)
        row = {"id": case["target"]["id"], "variant": "full_evidence_once" if control else "loop",
               "status": "error", "prediction": None, "checkpoints": []}
        report = None
        trace_written = False
        try:
            materials = [p.MaterialVersion(**m) for m in case["materials"]]
            provider = SnapshotSearchProvider(materials, [m.version_id for m in materials] if control else case["seed_ids"])
            t = case["target"]
            target = p.Target(**{**t, "evidence_scope": tuple(t["evidence_scope"])})
            if semantic_mode == "staged":
                decomposer = StagedDecomposer(client, max_repairs=max_repairs)
                verifier = StagedVerifier(client, max_repairs=max_repairs)
            else:
                decomposer = MonolithicDecomposer(client)
                verifier = MonolithicVerifier(client)
            case_trace_config = (p.TraceConfig(
                max_rounds=1,
                max_documents=trace_config.max_documents,
                max_decomposition_calls=trace_config.max_decomposition_calls,
            ) if control else trace_config)
            report = p.run_provenance(target, provider, decomposer, verifier,
                                      case_trace_config)
            report["model_call_lineage"] = model_call_lineage(client.records)
            if not report["assessment_valid"]:
                report["execution_failure"] = execution_failure_binding(
                    report, client.records)
            write(out / f"{identifier}-trace.json", report)
            trace_written = True
            write(out / f"{identifier}-retrieval.json", provider.history)
            if semantic_mode == "staged":
                write(out / f"{identifier}-semantic-stages.json", {
                    "prompt_manifest": prompt_manifest(),
                    "target_plans": {**decomposer.plans, **verifier.plans},
                    "decomposition": decomposer.history,
                    "verification": verifier.history,
                })
            row["checkpoints"] = round_decisions(report)
            row["prediction"] = present_decision(report)
            row["status"] = "completed" if report["assessment_valid"] else "error"
            if not report["assessment_valid"]:
                row["error_type"] = report["execution_failure"]["error_type"]
        except Exception as exc:
            failure = missing_trace_failure(type(exc).__name__, client.records)
            row["error_type"] = failure["error_type"]
            if not trace_written:
                # This sidecar is not accepted on trust: historical_compare
                # requires an offline replay of the bound calls to reproduce
                # an invalid assessment before it retains the row.
                write(out / f"{identifier}-failure.json", failure)
        finally:
            row["usage"] = client.usage()
            new_records = [r for r in client.records if not r.get("cached_from")]
            row["actual_new_api_usage"] = {"model_calls": len(new_records), **{k:sum(r.get("usage", {}).get(k, 0)
                                          for r in new_records) for k in ["input_tokens", "output_tokens"]}}
            write(out / f"{identifier}-calls.json", client.records)
            write(out / f"{identifier}-result.json", row)
        return row

    jobs = [(case, False) for case in data["cases"]]
    jobs += [(case, True) for case in data["cases"] if case["full_evidence_control"]]
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one, c, full) for c, full in jobs]):
            row = future.result()
            results.append(row)
            write(out / "results.json", results)
            print(json.dumps({"case": row["id"], "variant": row["variant"], "status": row["status"]}), flush=True)
    logical_calls = sum(r["usage"]["model_calls"] for r in results)
    actual_calls = sum(r["actual_new_api_usage"]["model_calls"] for r in results)
    write(out / "status.json", {
        "status": "completed" if all(r["status"] == "completed" for r in results) else "has_errors",
        "actual_model_calls": actual_calls,
        "logical_model_calls": logical_calls,
        "replayed_model_calls": logical_calls - actual_calls,
    })
    return 0 if all(r["status"] == "completed" for r in results) else 1


def score(args):
    gold = json.loads(Path(args.gold).read_text())
    rows = json.loads((Path(args.run) / "results.json").read_text())
    expected = {g["id"]: g for g in gold["cases"]}
    loops = [r for r in rows if r["variant"] == "loop"]
    if len(loops) != len(expected) or {r["id"] for r in loops} != expected.keys():
        raise ValueError("All frozen cases must be present exactly once")
    comparisons = []
    for r in loops:
        label = expected[r["id"]]["decision"]
        mode = expected[r["id"]]["assessment_mode"]
        if (r["prediction"] and r["prediction"]["assessment_mode"] != mode) or any(
                c["assessment_mode"] != mode for c in r["checkpoints"]):
            raise ValueError("Gold and predictions must use the same assessment_mode")
        first = r["checkpoints"][0]["decision"] if r["checkpoints"] else ("unverifiable" if r["status"] == "completed" else None)
        final = r["prediction"]["decision"] if r["status"] == "completed" else None
        comparisons.append({"id": r["id"], "gold": label, "first_round": first, "last_round": final,
                            "rounds_verified": len(r["checkpoints"]), "first_correct": first == label,
                            "last_correct": final == label, "status": r["status"]})
    controls = [{"id": r["id"], "decision": r["prediction"]["decision"] if r["prediction"] else None,
                 "status": r["status"]} for r in rows if r["variant"] == "full_evidence_once"]
    all_ok = all(r["status"] == "completed" for r in rows)
    write(Path(args.run) / "scores.json", {"status": "scored" if all_ok else "incomplete_no_overall_accuracy_claim",
        "dataset_kind": "synthetic_contract_examples", "cases": comparisons, "controls": controls,
        "overall": {"n": len(comparisons), "first_correct": sum(r["first_correct"] for r in comparisons),
                    "last_correct": sum(r["last_correct"] for r in comparisons)} if all_ok else None,
        "limits": ["Not independently reviewed or held out; not real-news accuracy.",
                   "First-round baseline reuses the exact live prefix; no stochastic independent baseline run.",
                   "Additional retrieval can change evidence access; consult the full-evidence control.",
                   "No synthetic confidence probabilities or aggregate NVScore were invented."]})
    return 0 if all_ok else 1


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    for name in ["inputs", "output", "model"]: r.add_argument("--" + name, required=True)
    r.add_argument("--max-rounds", type=int, default=5)
    r.add_argument("--reuse-from")
    r.add_argument("--semantic-mode", choices=["staged", "monolithic"], default="staged")
    r.add_argument("--max-repairs", type=int, choices=[0, 1], default=1)
    r.add_argument("--execution-profile", choices=["legacy-v03", "equal-v1"],
                   default="legacy-v03")
    r.add_argument("--reasoning-effort")
    s = sub.add_parser("score")
    for name in ["gold", "run"]: s.add_argument("--" + name, required=True)
    args = cli.parse_args()
    if args.command == "run" and not 1 <= args.max_rounds <= 10: cli.error("max-rounds must be 1..10")
    return run(args) if args.command == "run" else score(args)


if __name__ == "__main__": raise SystemExit(main())
