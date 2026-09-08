"""Run trace loops, evidence replays, and fixed-target evaluation."""
import argparse
import json
from importlib.resources import files
from pathlib import Path
import sys

from .core import run_verification
from .providers import ReplayProvider
from .evaluation import evaluate
from .comparison import compare

STATUSES = {"supported", "contradicted", "conflicting", "unresolved"}


def run_fixture(payload):
    if not isinstance(payload, dict) or "claim" not in payload or "rounds" not in payload:
        raise ValueError("input requires claim and rounds")
    return run_verification(payload["claim"], ReplayProvider(payload["rounds"]), payload.get("config"))


def benchmark(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list) or not payload["cases"]:
        raise ValueError("benchmark requires a nonempty cases list")
    results = []
    names = set()
    for case in payload["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("name"), str) or not case["name"].strip():
            raise ValueError("every case requires a nonempty name")
        if case["name"] in names:
            raise ValueError("benchmark case names must be unique")
        names.add(case["name"])
        expected = case.get("expected_status")
        if expected not in STATUSES:
            raise ValueError("every case requires a valid expected_status")
        loop = run_fixture(case)
        first = dict(case)
        first["config"] = dict(case.get("config") or {}, max_rounds=1)
        baseline = run_fixture(first)
        results.append({
            "name": case["name"], "expected_status": expected,
            "loop_status": loop["status"], "single_pass_status": baseline["status"],
            "policy_expectation_matched": loop["status"] == expected,
            "rounds": len(loop["rounds"]),
            "documents_examined": loop["documents_examined"],
            "stop_reason": loop["stop_reason"],
            "independent_source_counts": loop["independent_source_counts"],
        })
    matched = sum(r["policy_expectation_matched"] for r in results)
    return {
        "benchmark_type": "synthetic_annotated_policy_cases",
        "limitations": [
            "Checks expected policy behavior, not real-world news accuracy or semantic verification.",
            "The one-round baseline receives less evidence; this is not an equal-budget accuracy comparison.",
            "Stance, timestamps, and provenance are supplied annotations, not independently authenticated facts.",
        ],
        "case_count": len(results), "policy_expectations_matched": matched,
        "all_policy_expectations_matched": matched == len(results),
        "results": results,
    }


def main(argv=None, *, prog="newsverify"):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    from . import __version__
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    quickstart_parser = sub.add_parser("quickstart", help="run the offline annotated example and save a readable walkthrough")
    quickstart_parser.add_argument("--output", type=Path, required=True, help="new directory for inputs, config, trace and summary")
    quickstart_parser.add_argument("--config", type=Path, help="optional JSON resource budgets; no credentials")
    for command in ("demo", "trace-demo", "verify", "benchmark"):
        child = sub.add_parser(command)
        if command not in ("demo", "trace-demo"):
            child.add_argument("input", type=Path)
        child.add_argument("--output", type=Path)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("gold", type=Path)
    score_parser.add_argument("predictions", type=Path)
    score_parser.add_argument("--output", type=Path)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("gold", type=Path)
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    compare_parser.add_argument("--bootstrap-samples", type=int, default=500)
    compare_parser.add_argument("--seed", type=int, default=0)
    compare_parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "quickstart":
            from .quickstart import run_quickstart
            config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
            if args.config and config is None:
                raise ValueError("quickstart config must be a JSON object")
            result = run_quickstart(args.output, config)
            print(f"Offline annotated example: {result['fact_status']}; "
                  f"{result['usage']['rounds']} rounds; 0 model calls.")
            print(f"Read {args.output / 'SUMMARY.md'}")
            return 0 if result["assessment_valid"] else 1
        elif args.command == "trace-demo":
            from .trace_demo import run_demo
            result = run_demo()
        elif args.command == "compare":
            inputs = (args.gold, args.baseline, args.candidate)
            if args.output and args.output.resolve() in {p.resolve() for p in inputs}:
                raise ValueError("output must differ from all inputs")
            result = compare(*(json.loads(p.read_text(encoding="utf-8")) for p in inputs),
                             bootstrap_samples=args.bootstrap_samples, seed=args.seed)
        elif args.command == "score":
            if args.output and args.output.resolve() in {args.gold.resolve(), args.predictions.resolve()}:
                raise ValueError("output must differ from gold and predictions")
            result = evaluate(json.loads(args.gold.read_text(encoding="utf-8")),
                              json.loads(args.predictions.read_text(encoding="utf-8")))
        elif args.command == "demo":
            raw = files("newsverify").joinpath("data/demo.json").read_text(encoding="utf-8")
        else:
            if args.output and args.output.resolve() == args.input.resolve():
                raise ValueError("output must differ from input")
            raw = args.input.read_text(encoding="utf-8")
        if args.command not in ("score", "trace-demo", "compare"):
            payload = json.loads(raw)
            result = benchmark(payload) if args.command == "benchmark" else run_fixture(payload)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            print(rendered, end="")
        return 1 if args.command == "benchmark" and not result["all_policy_expectations_matched"] else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
