"""Independently score saved historical outputs with Inspect; never run a model.

Optional tooling, separate from the project's runtime dependencies::

    python -m venv /tmp/historical-inspect-venv
    /tmp/historical-inspect-venv/bin/pip install \
      'inspect_ai @ git+https://github.com/UKGovernmentBEIS/inspect_ai.git@ec3bf0995fb6435f452f158f85ca423803aa0f98'
    /tmp/historical-inspect-venv/bin/python inspect_replay.py \
      --results /path/to/completed/results --gold /path/to/registered/gold.json

Inputs remain private. Public checkouts without the archived batch can run
``python inspect_replay.py --self-test`` using only the standard library.
This is a post hoc replay of prior responses, not fresh model inference, a
new held-out benchmark, or a new semantic adjudication of the gold labels.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
INSPECT_COMMIT = "ec3bf0995fb6435f452f158f85ca423803aa0f98"
ARMS = ("direct", "double_loop")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
FLAGS = ("pipeline_success", "valid", "cutoff_match", "future_verdict_match",
         "abstained", "accepted_later_false_claim", "called_later_false_claim_false",
         "unwarranted_settled_cutoff_verdict")


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    def reject(value):
        raise ValueError("Nonfinite JSON in input artifact")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timestamp(value):
    require(isinstance(value, str), "Missing source timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None, "Timestamp lacks timezone")
    return parsed


def eligible(source, cutoff):
    try:
        if not all(isinstance(source.get(k), str) and source[k].strip()
                   for k in ("version_id", "url", "issuer", "content", "availability_basis")):
            return False
        retrieved = timestamp(source["retrieved_at"])
        available = timestamp(source["available_at"])
        published = timestamp(source["published_at"]) if source.get("published_at") else None
        return (available <= cutoff and available <= retrieved
                and (published is None or published <= cutoff and published <= retrieved))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def final_output(run):
    if run["condition"] == "direct":
        return run.get("raw_response")
    report = run.get("report")
    history = report.get("verification_history") if isinstance(report, dict) else None
    return history[-1] if isinstance(history, list) and history else None


def shaped(output, arm):
    fields = {"verdict", "basis", "rationale"}
    if arm == "double_loop":
        fields |= {"round", "gaps", "resolutions"}
    if not isinstance(output, dict) or set(output) != fields:
        return False
    if not isinstance(output["verdict"], str) or output["verdict"] not in VERDICTS:
        return False
    if not isinstance(output["basis"], list) or not isinstance(output["rationale"], str):
        return False
    if arm == "double_loop" and not (
        type(output["round"]) is int and output["round"] >= 0
        and isinstance(output["gaps"], list) and isinstance(output["resolutions"], list)
    ):
        return False
    return all(isinstance(span, dict) and {"version_id", "quote"} <= set(span)
               <= {"version_id", "quote", "start", "end"}
               and isinstance(span["version_id"], str) and isinstance(span["quote"], str)
               for span in output["basis"])


def citations(output, case, visible):
    if not isinstance(output, dict) or not isinstance(output.get("basis"), list):
        return False
    if not isinstance(output.get("rationale"), str) or not output["rationale"].strip():
        return False
    if not output["basis"]:
        return visible == output.get("verdict") == "unresolved"
    pool = {m["version_id"]: m for m in case["materials"]}
    for span in output["basis"]:
        if not isinstance(span, dict) or not isinstance(span.get("version_id"), str):
            return False
        source, quote = pool.get(span["version_id"]), span.get("quote")
        if source is None or not isinstance(quote, str) or not quote:
            return False
        start = source["content"].find(quote)
        if start < 0 or source["content"].find(quote, start + 1) >= 0:
            return False  # The second search also detects overlapping duplicates.
        if not eligible(source, timestamp(case["target"]["as_of"])):
            return False
        if "start" in span or "end" in span:
            if not (type(span.get("start")) is int and type(span.get("end")) is int
                    and span["start"] == start and span["end"] == start + len(quote)):
                return False
    return True


def derive(run, case, label):
    """Compute outcomes from raw output and receipts, without project helpers."""
    output, observed = final_output(run), run.get("fact_status")
    calls = run.get("calls")
    success = (shaped(output, run["condition"]) and isinstance(calls, list) and bool(calls)
               and run.get("errors") == [] and isinstance(observed, str) and observed in VERDICTS
               and all(isinstance(c, dict) and c.get("success") is True for c in calls))
    if run["condition"] == "direct" and isinstance(output, dict):
        success = success and output.get("verdict") == observed
    citation_ok = citations(output, case, observed)
    valid = bool(success and citation_ok)
    authenticity = label["role"] == "authenticity"
    return {
        "id": run["id"], "condition": run["condition"], "variant": label["variant"],
        "role": label["role"], "event_family": label["event_family"], "observed": observed,
        "raw_verdict": output.get("verdict") if isinstance(output, dict) else None,
        "cutoff_expected": label["cutoff_expected"], "future_expected": label["future_expected"],
        "pipeline_success": bool(success), "citation_integrity": citation_ok, "valid": valid,
        "cutoff_match": valid and observed == label["cutoff_expected"],
        "future_verdict_match": valid and observed == label["future_expected"],
        "abstained": valid and observed == "unresolved",
        "accepted_later_false_claim": valid and authenticity and observed == "supported",
        "called_later_false_claim_false": valid and authenticity and observed == "contradicted",
        "unwarranted_settled_cutoff_verdict": valid and label["cutoff_expected"] == "unresolved" and observed != "unresolved",
        "logical_calls": len(calls) if isinstance(calls, list) else 0,
        "failed_calls": sum(c.get("success") is not True for c in calls) if isinstance(calls, list) else 0,
    }


def exposure(value, pool):
    """Bind full material objects and source previews to the registered corpus."""
    if isinstance(value, list):
        for child in value:
            exposure(child, pool)
    elif isinstance(value, dict):
        if {"version_id", "content", "available_at"} <= set(value):
            require(value.get("version_id") in pool and value == pool[value["version_id"]], "Altered full source")
        if "catalog" in value:
            require(isinstance(value["catalog"], list), "Invalid catalog")
            seen = set()
            for entry in value["catalog"]:
                require(isinstance(entry, dict) and entry.get("version_id") in pool, "Foreign catalog source")
                source = pool[entry["version_id"]]
                expected = {k: source[k] for k in ("version_id", "url", "issuer", "published_at", "available_at")}
                expected["preview"] = source["content"][:800]
                require(entry == expected and entry["version_id"] not in seen, "Altered or duplicate preview")
                seen.add(entry["version_id"])
        for child in value.values():
            exposure(child, pool)


def load_batch(results, gold_path):
    manifest = read(results / "manifest.json")
    require(manifest.get("worker_exit_code") == 0 and manifest.get("finished_at"), "Wait for the completed batch")
    require(manifest.get("test_stub") is False and manifest.get("gold_loaded") is False, "Real isolated batch required")
    require(manifest.get("frozen_integrity") and all(v is True for v in manifest["frozen_integrity"].values()), "Frozen integrity failed")
    artifacts = {name: results / filename for name, filename in (
        ("manifest", "manifest.json"), ("corpus", "corpus.json"), ("preflight", "preflight.json"),
        ("registration", "registration.json"), ("predictions", "stage-artifacts/predictions.json"))}
    artifacts["gold"] = gold_path
    hashes = {name: sha(path) for name, path in artifacts.items()}
    registration, corpus, gold = read(artifacts["registration"]), read(artifacts["corpus"]), read(gold_path)
    require(hashes["corpus"] == manifest["corpus_sha256"] == registration["corpus_sha256"]
            == read(artifacts["preflight"])["corpus_sha256"], "Corpus commitment differs")
    require(hashes["gold"] == registration["gold_sha256"], "Registered gold changed")
    require(hashes["registration"] == manifest["registration_sha256"] and hashes["preflight"] == manifest["review_sha256"], "Review or registration changed")
    require(timestamp(registration["registered_at"]) <= timestamp(manifest["started_at"]), "Registration was late")
    for name, expected in manifest["frozen_code_sha256"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe frozen path")
        require(sha(results / "frozen-inputs" / name) == expected, "Frozen inference source changed")
    cases = {c["target"]["id"]: c for c in corpus["cases"]}
    labels = {g["id"]: g for g in gold["cases"]}
    require(len(cases) == len(corpus["cases"]) == manifest["case_count"], "Case denominator differs")
    require(len(labels) == len(gold["cases"]) and set(labels) == set(cases), "Gold denominator differs")
    predictions = read(artifacts["predictions"])
    require(predictions.get("test_stub") is False and predictions.get("gold_loaded") is False, "Prediction provenance differs")
    runs = predictions["results"]
    pairs = [(r["id"], r["condition"]) for r in runs]
    require(len(pairs) == len(set(pairs)) == 2 * len(cases)
            and set(pairs) == {(cid, arm) for cid in cases for arm in ARMS}, "Missing or duplicate paired run")
    receipt_hashes = {}
    for run in runs:
        cid, arm = run["id"], run["condition"]
        require(re.fullmatch(r"[A-Za-z0-9_-]+", cid), "Unsafe case ID")
        folder = results / "stage-artifacts" / cid / arm
        require(read(folder / "result.json") == run, "Result sidecar differs")
        pool = {m["version_id"]: m for m in cases[cid]["materials"]}
        require(len(pool) == len(cases[cid]["materials"]), "Duplicate source version")
        require(all(eligible(m, timestamp(cases[cid]["target"]["as_of"])) for m in pool.values()), "Ineligible source")
        report = run.get("report") or {}
        audit_io = report.get("execution", {}).get("model_io", [])
        if report:
            require(len(audit_io) == len(run["calls"]), "Harness call count differs")
        verified = None
        for n, call in enumerate(run["calls"], 1):
            require(call["stage"] in {"direct", "select", "decompose", "verify"}, "Unknown stage")
            stem = folder / f"{n:02d}-{call['stage']}"
            require(read(stem.with_suffix(".calls.json")) == [call], "Call receipt differs")
            require(call.get("test_stub") is not True and call["tunnel"] == "local", "Unexpected call transport")
            item = read(stem.with_suffix(".input.json"))
            require(item["instructions"].startswith(manifest["temporal_instruction"]), "Missing temporal contract")
            exposure(item["packet"], pool)
            serialized = json.dumps(item["packet"])
            require("cutoff_expected" not in serialized and "future_expected" not in serialized, "Gold field exposed")
            response_path = stem.with_suffix(".response.json")
            require(not call["success"] or response_path.is_file(), "Missing successful response")
            response = read(response_path) if response_path.is_file() else None
            if arm == "direct" and response_path.is_file():
                require(response == run.get("raw_response"), "Direct response binding differs")
            if arm == "double_loop" and audit_io:
                audit = audit_io[n - 1]
                require(audit["packet"] == item["packet"] and audit["schema"] == item["schema"], "Harness input binding differs")
                require(item["instructions"] == manifest["temporal_instruction"] + "\n" + audit["instructions"], "Harness instructions differ")
                require(not response_path.is_file() or audit.get("response") == response, "Harness response binding differs")
            if call["stage"] == "verify" and call["success"]:
                verified = response
            for suffix in (".input.json", ".response.json", ".calls.json"):
                path = stem.with_suffix(suffix)
                if path.is_file():
                    receipt_hashes[str(path.relative_to(results))] = sha(path)
        row = derive(run, cases[cid], labels[cid])
        if arm == "double_loop" and row["valid"]:
            final = final_output(run)
            require(isinstance(verified, dict) and final["verdict"] == verified["verdict"]
                    and final["rationale"] == verified["rationale"], "Final verifier binding differs")
            require([{k: b[k] for k in ("version_id", "quote")} for b in final["basis"]] == verified["basis"], "Final citation binding differs")
    receipt_digest = hashlib.sha256(json.dumps(receipt_hashes, sort_keys=True).encode()).hexdigest()
    hashes["recorded_sidecars_index"] = receipt_digest
    return runs, cases, labels, hashes, receipt_hashes


def aggregate(rows):
    result = {}
    for variant in ("original", "blinded"):
        result[variant] = {}
        for arm in ARMS:
            selected = [r for r in rows if r["variant"] == variant and r["condition"] == arm]
            authentic = [r for r in selected if r["role"] == "authenticity"]
            controls = [r for r in selected if r["role"] == "attribution_control"]
            result[variant][arm] = {
                "cases": len(selected), "completed": sum(r["pipeline_success"] for r in selected),
                "evidence_valid": sum(r["valid"] for r in selected),
                "cutoff_matches": sum(r["cutoff_match"] for r in selected),
                "authenticity_cases": len(authentic),
                "accepted_later_false_claims": sum(r["accepted_later_false_claim"] for r in authentic),
                "called_later_false_claims_false": sum(r["called_later_false_claim_false"] for r in authentic),
                "authenticity_abstentions": sum(r["abstained"] for r in authentic),
                "unwarranted_settled_cutoff_verdicts": sum(r["unwarranted_settled_cutoff_verdict"] for r in authentic),
                "controls": len(controls), "control_matches": sum(r["cutoff_match"] for r in controls),
            }
    return result


def run_inspect(results, gold_path, out, reference=None):
    try:
        from inspect_ai import Task, eval as inspect_eval
        from inspect_ai.dataset import Sample
        from inspect_ai.model import Model, ModelOutput
        from inspect_ai.scorer import Score, mean, scorer
        from inspect_ai.solver import solver
    except ImportError as exc:
        raise SystemExit("Install the optional pinned Inspect dependency as documented in this script.") from exc
    distribution = metadata.distribution("inspect_ai")
    installation = json.loads(distribution.read_text("direct_url.json") or "{}")
    require(installation.get("vcs_info", {}).get("commit_id") == INSPECT_COMMIT, "Inspect must be installed from the documented pinned commit")
    runs, cases, labels, hashes, receipt_hashes = load_batch(results, gold_path)
    records = {(r["id"], r["condition"]): r for r in runs}
    rows = []
    generation_attempts = 0

    async def forbidden_generate(*args, **kwargs):
        nonlocal generation_attempts
        generation_attempts += 1
        raise RuntimeError("Model generation is forbidden during offline replay")

    @solver
    def replay_saved_response():
        async def solve(state, generate):
            run = records[state.sample_id, state.metadata["condition"]]
            state.output = ModelOutput.from_content("recorded-output", json.dumps(run, ensure_ascii=False))
            state.completed = True
            return state
        return solve

    @scorer(metrics={flag: [mean()] for flag in FLAGS})
    def independent_receipt_scores():
        async def score(state, target):
            run = json.loads(state.output.completion)
            row = derive(run, cases[state.sample_id], labels[state.sample_id])
            rows.append(row)
            # Every saved run receives numeric scores, including model failures.
            return Score(value={flag: int(row[flag]) for flag in FLAGS},
                         answer=row["observed"], metadata={"audit_row": row})
        return score

    tasks = []
    for variant in ("original", "blinded"):
        for arm in ARMS:
            samples = [Sample(id=r["id"], input=cases[r["id"]]["target"]["text"],
                              metadata={"condition": arm, "replay_only": True})
                       for r in runs if r["condition"] == arm and labels[r["id"]]["variant"] == variant]
            if samples:
                tasks.append(Task(name=f"historical_replay_{variant}_{arm}", dataset=samples,
                    solver=replay_saved_response(), scorer=independent_receipt_scores(),
                    metadata={"variant": variant, "condition": arm, "replay_only": True},
                    fail_on_error=True))
    out.mkdir(parents=True, exist_ok=True)
    with patch.object(Model, "generate", forbidden_generate):
        logs = inspect_eval(tasks, model="none", log_dir=str(out / "logs"), log_format="json",
                            display="none", max_tasks=1, max_samples=1, epochs=1,
                            retry_on_error=0, log_shared=False, score_display=False)
    require(generation_attempts == 0 and len(logs) == len(tasks), "Unexpected generation or missing task")
    inspect_metrics, model_events, log_hashes = {}, 0, {}
    for log in logs:
        require(log.status == "success" and log.results is not None, "Inspect replay task failed")
        require(log.samples and len(log.samples) == log.results.total_samples, "Inspect omitted samples")
        require(not log.stats.model_usage, "Unexpected model usage in offline replay")
        for sample in log.samples:
            require(sample.error is None and sample.scores, "Inspect dropped a replay score")
            model_events += sum(getattr(event, "event", None) == "model" for event in sample.events)
        scores = {s.name: {name: metric.value for name, metric in s.metrics.items()} for s in log.results.scores}
        inspect_metrics[log.eval.task] = {"samples": log.results.total_samples, "metrics": scores}
        log_hashes[Path(log.location).name] = sha(log.location)
    require(model_events == 0 and len(rows) == len(runs), "Unexpected model event or missing score")
    rows.sort(key=lambda row: (row["id"], row["condition"]))
    scores_by_variant = aggregate(rows)
    agreement = None
    if reference is not None:
        # The original summary is opened only after independent scores exist.
        prior = read(reference)
        prior_rows = {(r["id"], r["condition"]): r for r in prior["rows"]}
        fields = FLAGS + ("observed", "raw_verdict", "citation_integrity")
        differences = [{"id": row["id"], "condition": row["condition"], "field": key}
                       for row in rows for key in fields
                       if prior_rows.get((row["id"], row["condition"]), {}).get(key) != row[key]]
        agreement = {"row_outcomes_match": not differences,
                     "aggregate_outcomes_match": prior["scores_by_variant"] == scores_by_variant,
                     "rows_compared": len(rows), "fields_per_row": len(fields), "differences": differences,
                     "reference_summary_sha256": sha(reference)}
    result = {
        "schema_version": 1, "kind": "offline_replay_of_saved_real_batch",
        "new_model_test": False, "no_model_calls": True, "generation_attempts": generation_attempts,
        "inspect_model_events": model_events, "inspect_model": "none",
        "inspect_version": distribution.version, "inspect_commit": INSPECT_COMMIT,
        "script_sha256": sha(Path(__file__)), "source_artifact_sha256": hashes,
        "event_family_count": len({label["event_family"] for label in labels.values()}),
        "case_count": len(cases), "saved_run_count": len(runs), "replayed_run_count": len(rows),
        "saved_logical_calls": sum(row["logical_calls"] for row in rows),
        "saved_failed_calls": sum(row["failed_calls"] for row in rows),
        "failure_denominator": "all_saved_runs_explicit_zero_on_failure",
        "scores_by_variant": scores_by_variant, "rows": rows,
        "inspect_task_metrics": inspect_metrics, "inspect_log_sha256": log_hashes,
        "original_scorer_agreement": agreement,
        "scope": {"independent_score_implementation": True, "independent_inference": False,
                  "new_gold_adjudication": False, "independent_event_families_added": 0,
                  "pretrained_future_knowledge_excluded": False, "semantic_entailment_rejudged": False,
                  "image_forensics_tested": False},
    }
    write(out / "RESULTS.json", result)
    write(out / "SIDECAR_HASHES.json", receipt_hashes)
    write(out / "INSTALLATION.json", {"version": distribution.version, "direct_url": installation})
    return result


def self_test():
    source = {"version_id": "s", "url": "https://example.test", "issuer": "Test",
              "content": "The source reports seven.", "retrieved_at": "2020-01-01T00:00:00Z",
              "published_at": "2020-01-01T00:00:00Z", "available_at": "2020-01-01T00:00:00Z",
              "availability_basis": "Synthetic fixture only."}
    case = {"target": {"as_of": "2023-12-31T00:00:00Z"}, "materials": [source]}
    label = {"role": "authenticity", "variant": "original", "event_family": "synthetic",
             "cutoff_expected": "unresolved", "future_expected": "contradicted"}
    run = {"id": "synthetic", "condition": "direct", "fact_status": "unresolved", "errors": [],
           "calls": [{"success": True}], "raw_response": {"verdict": "unresolved", "basis": [], "rationale": "Unknown."}}
    require(derive(run, case, label)["cutoff_match"], "Synthetic abstention failed")
    for malformed in ([], [{"verdict": "unresolved"}], "unresolved", None):
        broken = {**run, "raw_response": malformed}
        require(not derive(broken, case, label)["abstained"], "Malformed output earned credit")
    failed = deepcopy(run)
    failed["calls"][0]["success"] = False
    require(not derive(failed, case, label)["cutoff_match"], "Failed call earned credit")
    settled = {"verdict": "supported", "basis": [{"version_id": "s", "quote": source["content"]}], "rationale": "The source reports it."}
    require(citations(settled, case, "supported"), "Exact quote rejected")
    repeated = deepcopy(case)
    repeated["materials"][0]["content"] *= 2
    require(not citations(settled, repeated, "supported"), "Duplicate quote accepted")
    print("Offline synthetic replay checks passed; no optional dependencies or model calls.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--gold", type=Path, default=HERE / "private/gold.json")
    parser.add_argument("--out", type=Path, default=HERE / "private/inspect-audit")
    parser.add_argument("--reference-summary", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        summary = run_inspect(args.results.resolve(), args.gold.resolve(), args.out.resolve(), args.reference_summary)
        print(json.dumps({key: summary[key] for key in ("no_model_calls", "inspect_version", "saved_run_count", "scores_by_variant", "original_scorer_agreement")}, indent=2))
