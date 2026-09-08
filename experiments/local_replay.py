"""Re-execute archived verification locally without API authentication or calls.

This is deterministic response replay, not new local-model inference. API
availability, replay execution, and semantic verification have separate states.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historical_compare as historical
from model_io import write
from newsverify.decisions import present_decision


def replay(args):
    archive = Path(args.archive).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("Output already exists; choose a new run directory")
    validated = historical.validate_inference(
        args.inputs, args.sources, args.freeze)
    config = historical._json(archive / "config.json")
    for key in ("input_sha256", "sources_sha256", "freeze_sha256"):
        if config.get(key) != validated[key]:
            raise ValueError("Archive and frozen inputs differ: " + key)
    cases = validated["inputs"]["cases"]
    prepared = []
    # Validate both arms before replay. Archived token use belongs to the old
    # run and is never added to this run's API usage.
    for arm, mode in historical.ARM_ORDER:
        rows = historical._json(archive / arm / "results.json")
        historical._validate_raw_rows(rows, cases)
        historical._validate_call_logs(
            archive / arm, rows, config["model"],
            config["reasoning_effort"], config["budget"])
        for case in cases:
            identifier = case["target"]["id"]
            if Path(identifier).name != identifier or identifier in {".", ".."}:
                raise ValueError("Case id is not a safe artifact name")
            variants = [("loop", "loop")]
            if case["full_evidence_control"]:
                variants.append(("full_evidence_once", "full"))
            for variant, suffix in variants:
                path = archive / arm / f"{identifier}-{suffix}-calls.json"
                prepared.append((arm, mode, case, variant, suffix,
                                 historical._json(path)))

    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "schema_version": 1,
        "execution_mode": "local_replay",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_status": "running",
        "verification_status": "not_checked",
        "api": {"required": False, "status": "not_used", "requests": 0},
        "new_model_inference": False,
        "new_accuracy_measurement": False,
        "gold_access_during_replay": False,
        "input_sha256": validated["input_sha256"],
        "archive_config_sha256": historical._sha(archive / "config.json"),
        "executed_source_sha256": historical.loop_compare.source_hashes(),
        "archived_model": config["model"],
        "results": [],
        "replayed_call_records": 0,
        "scores": None,
    }
    write(output / "results.json", report)
    for arm, mode, case, variant, suffix, records in prepared:
        identifier = case["target"]["id"]
        row = {"arm": arm, "id": identifier, "variant": variant}
        try:
            trace = historical._offline_replay_trace(
                case, variant, mode, config["trace_config"],
                config["max_inner_repairs"][arm], records,
                config["model"], config["reasoning_effort"], config["budget"])
            filename = f"{arm}-{identifier}-{suffix}-trace.json"
            write(output / filename, trace)
            prediction = present_decision(trace)
            row.update(
                execution_status="completed",
                verification_status=("completed" if prediction["assessment_valid"]
                                     else "error"),
                prediction=prediction, errors=trace["errors"],
                replayed_call_records=len(records), trace=filename)
            report["replayed_call_records"] += len(records)
        except (ValueError, RuntimeError) as exc:
            # A request/log mismatch is a replay error, never a new decision.
            row.update(execution_status="error", verification_status="not_checked",
                       prediction=None, error_type=type(exc).__name__,
                       error=str(exc))
        report["results"].append(row)
        write(output / "results.json", report)

    replay_failed = any(row["execution_status"] != "completed"
                        for row in report["results"])
    report["execution_status"] = "has_errors" if replay_failed else "completed"
    report["verification_status"] = (
        "has_errors" if any(row["verification_status"] == "error"
                            for row in report["results"])
        else "incomplete" if replay_failed else "completed")
    write(output / "results.json", report)

    # Gold is opened only after every replay has finished. Refuse a score if
    # a request could not be replayed; semantic failures remain in the results.
    if args.gold and not replay_failed:
        try:
            gold = historical.validate_all(
                args.inputs, args.sources, args.gold, args.freeze)["gold"]
            labels = {case["id"]: case["decision"] for case in gold["cases"]}
            scores = {"kind": "archived_response_replay", "main_cases": {}}
            for arm, _ in historical.ARM_ORDER:
                rows = [row for row in report["results"]
                        if row["arm"] == arm and row["variant"] == "loop"]
                correct = sum(row["prediction"]["assessment_valid"]
                              and row["prediction"]["decision"] == labels[row["id"]]
                              for row in rows)
                scores["main_cases"][arm] = {
                    "correct": correct, "total": len(rows),
                    "accuracy": correct / len(rows) if rows else None,
                }
            report["scores"] = scores
        except ValueError as exc:
            report["execution_status"] = "has_errors"
            report["scoring_error"] = str(exc)
    report["local_seconds"] = round(time.monotonic() - started, 6)
    write(output / "results.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "inputs", "sources", "freeze", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--gold", help="Optional frozen labels; opened after replay")
    args = parser.parse_args()
    try:
        report = replay(args)
    except (ValueError, OSError) as exc:
        print(f"Local replay blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print("API: not used (0 requests)")
    print("Local replay:", report["execution_status"])
    print("Verification:", report["verification_status"])
    print("Archived calls replayed:", report["replayed_call_records"])
    if report["scores"]:
        for arm, score in report["scores"]["main_cases"].items():
            print(f"{arm}: {score['correct']}/{score['total']} (saved-output replay)")
    print("New model inference: no")
    print("Results:", Path(args.output).resolve() / "results.json")
    return int(report["execution_status"] != "completed"
               or report["verification_status"] != "completed")


if __name__ == "__main__":
    raise SystemExit(main())
