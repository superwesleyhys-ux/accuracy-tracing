"""Run fresh claim verification with local GGUF weights and zero cloud model calls."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop_compare as loop
from local_model import LocalTransport
from model_io import Budget, BudgetClient, write


def run(args):
    cases = loop.load_inputs(args.inputs)["cases"]
    if args.case:
        cases = [case for case in cases if case["target"]["id"] == args.case]
        if not cases:
            raise ValueError("Requested case does not exist")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    config = {
        "execution_mode": "local_model_inference", "new_model_inference": True,
        "cloud_api": {"required": False, "requests": 0, "fallback": False},
        "semantic_mode": args.semantic_mode, "max_rounds": args.max_rounds,
        "input_sha256": hashlib.sha256(Path(args.inputs).read_bytes()).hexdigest(),
        "source_sha256": loop.source_hashes(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "gold_access_during_inference": False,
    }
    write(out / "config.json", config)
    budget = Budget(calls=args.max_calls, output_tokens=128000,
                    per_call_output_tokens=8000, seconds=args.case_seconds)
    results = []
    try:
        with LocalTransport(args.config) as transport:
            config.update(local_model=transport.config, model=transport.model_id,
                          budget=asdict(budget), network_disabled_in_worker=True)
            write(out / "config.json", config)
            jobs = [(case, False) for case in cases]
            if args.include_controls:
                jobs += [(case, True) for case in cases if case["full_evidence_control"]]
            for case, full in jobs:
                identifier = case["target"]["id"] + ("-full" if full else "-loop")
                if Path(identifier).name != identifier:
                    raise ValueError("Unsafe case id")
                class RecordedClient(BudgetClient):
                    def call(self, *values, **options):
                        try:
                            return super().call(*values, **options)
                        finally:
                            write(out / f"{identifier}-calls.json", self.records)
                            write(out / "local-runtime-calls.json", transport.records)
                            print(json.dumps({"case": identifier, "local_calls": self.calls,
                                              "cloud_calls": 0}), flush=True)
                client = RecordedClient(transport.model_id, budget, transport=transport)
                materials = [loop.p.MaterialVersion(**item) for item in case["materials"]]
                seeds = [item.version_id for item in materials] if full else case["seed_ids"]
                provider = loop.SnapshotSearchProvider(materials, seeds)
                target = loop.p.Target(**{**case["target"], "evidence_scope": tuple(case["target"]["evidence_scope"])})
                if args.semantic_mode == "staged":
                    decomposer = loop.StagedDecomposer(client, max_repairs=1)
                    verifier = loop.StagedVerifier(client, max_repairs=1)
                else:
                    decomposer = loop.MonolithicDecomposer(client)
                    verifier = loop.MonolithicVerifier(client)
                trace = loop.p.run_provenance(
                    target, provider, decomposer, verifier,
                    loop.p.TraceConfig(max_rounds=1 if full else args.max_rounds,
                                       max_documents=18, max_decomposition_calls=18))
                write(out / f"{identifier}-trace.json", trace)
                write(out / f"{identifier}-retrieval.json", provider.history)
                if args.semantic_mode == "staged":
                    write(out / f"{identifier}-stages.json", {
                        "decomposition": decomposer.history, "verification": verifier.history})
                row = {"id": case["target"]["id"], "variant": "full_evidence_once" if full else "loop",
                       "status": "completed" if trace["assessment_valid"] else "error",
                       "prediction": loop.present_decision(trace), "errors": trace["errors"],
                       "local_usage": client.usage(), "cloud_api_calls": 0}
                results.append(row)
                write(out / "results.json", results)
                print(json.dumps({"case": identifier, "status": row["status"],
                                  "decision": row["prediction"]["decision"]}), flush=True)
        status = {"status": "completed" if all(row["status"] == "completed" for row in results) else "has_errors",
                  "new_model_inference": True, "local_model_calls": sum(row["local_usage"]["model_calls"] for row in results),
                  "cloud_api_calls": 0, "results": len(results)}
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        status = {"status": "local_runtime_error", "error_type": type(exc).__name__,
                  "error": str(exc), "cloud_api_calls": 0, "fallback": False}
    write(out / "status.json", status)
    print(json.dumps(status), flush=True)
    return int(status["status"] != "completed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=".local/model.json")
    parser.add_argument("--inputs", default="experiments/historical-2023-pilot2-v3/inputs.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--case")
    parser.add_argument("--semantic-mode", choices=["staged", "monolithic"], default="staged")
    parser.add_argument("--max-rounds", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--case-seconds", type=int, default=900)
    parser.add_argument("--include-controls", action="store_true")
    args = parser.parse_args()
    if args.max_calls < 1 or args.case_seconds < 1:
        parser.error("max-calls and case-seconds must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
