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
from model_io import Budget, BudgetClient, PriorResponseCache, write
from semantic_adapter import Decomposer, Verifier

BUDGET = Budget(calls=24, output_tokens=36000, per_call_output_tokens=2500, seconds=600)


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
    reuse = Path(args.reuse_from) if getattr(args, "reuse_from", None) else None
    if reuse:
        old = json.loads((reuse / "config.json").read_text())
        if (old["input_sha256"] != hashlib.sha256(Path(args.inputs).read_bytes()).hexdigest()
                or old["model"] != args.model or old["budget"] != asdict(BUDGET)):
            raise ValueError("Cached run must have the same frozen inputs, model, and resource caps")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    config = {"model": args.model, "max_rounds": args.max_rounds, "budget": asdict(BUDGET),
        "input_sha256": hashlib.sha256(Path(args.inputs).read_bytes()).hexdigest(),
        "source_sha256": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                          for base in [ROOT / "newsverify", ROOT / "experiments"] for f in sorted(base.glob("*.py"))},
        "comparison": "exact first-round checkpoint versus continued loop; same decision function",
        "control": "one-round all-materials control for flagged cases separates access from repeated reasoning",
        "original_agent_reexecuted": False, "gold_access_during_inference": False,
        "actual_spend_equal": False, "input_tokens_capped": False}
    config["reuse_from"] = str(reuse) if reuse else None
    config["cache_rule"] = "same case/variant, exact system/user/schema/model/output-cap match; historical time/tokens charged"
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
        client = RecordedClient(args.model, BUDGET, transport=cache)
        row = {"id": case["target"]["id"], "variant": "full_evidence_once" if control else "loop",
               "status": "error", "prediction": None, "checkpoints": []}
        try:
            materials = [p.MaterialVersion(**m) for m in case["materials"]]
            provider = SnapshotSearchProvider(materials, [m.version_id for m in materials] if control else case["seed_ids"])
            t = case["target"]
            target = p.Target(**{**t, "evidence_scope": tuple(t["evidence_scope"])})
            report = p.run_provenance(target, provider, Decomposer(client), Verifier(client),
                p.TraceConfig(max_rounds=1 if control else args.max_rounds, max_documents=18, max_decomposition_calls=18))
            write(out / f"{identifier}-trace.json", report)
            write(out / f"{identifier}-retrieval.json", provider.history)
            row["checkpoints"] = round_decisions(report)
            row["prediction"] = present_decision(report)
            row["status"] = "completed" if report["assessment_valid"] else "error"
        except Exception as exc:
            row["error_type"] = type(exc).__name__
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
    write(out / "status.json", {"status": "completed" if all(r["status"] == "completed" for r in results) else "has_errors",
        "actual_model_calls": sum(r["usage"]["model_calls"] for r in results)})
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
        first = r["checkpoints"][0]["decision"] if r["checkpoints"] else None
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
    s = sub.add_parser("score")
    for name in ["gold", "run"]: s.add_argument("--" + name, required=True)
    args = cli.parse_args()
    if args.command == "run" and not 1 <= args.max_rounds <= 10: cli.error("max-rounds must be 1..10")
    return run(args) if args.command == "run" else score(args)


if __name__ == "__main__": raise SystemExit(main())
