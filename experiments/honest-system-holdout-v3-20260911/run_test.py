#!/usr/bin/env python3
"""Run the frozen system-comparison arms without loading outcome labels."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from newsverify.tunnels import LocalTunnel  # noqa: E402
from policies import POLICIES, RESULT_SCHEMA  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def validate_setup(corpus: dict, registration: dict) -> None:
    expected = registration.get("frozen_sha256")
    if not isinstance(expected, dict):
        raise SystemExit("registration has no frozen hashes")
    paths = {
        "corpus.json": HERE / "corpus.json",
        "policies.py": HERE / "policies.py",
        "run_test.py": HERE / "run_test.py",
        "summarize_test.py": HERE / "summarize_test.py",
        "PROTOCOL.md": HERE / "PROTOCOL.md",
        "SOURCE_AUDIT.json": HERE / "SOURCE_AUDIT.json",
    }
    observed = {name: sha256(path) for name, path in paths.items()}
    if observed != expected:
        raise SystemExit("registered files changed after preregistration")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or [case.get("id") for case in cases] != registration.get("case_order"):
        raise SystemExit("corpus case order does not match registration")
    for case in cases:
        for arm, expected_ids in (
            ("direct", ["p001", "p002", "p003", "p004"]),
            ("harness", ["p001", "p002", "p003", "p004", "p005", "p006"]),
        ):
            packet = case.get(f"{arm}_packet")
            if not isinstance(packet, dict) or packet.get("case_id") != case.get("id"):
                raise SystemExit(f"case has an invalid {arm} packet")
            if set(packet) != {"case_id", "question", "cutoff", "paper_profile", "evidence_passages"}:
                raise SystemExit(f"{arm} packet fields are not fixed")
            passage_ids = [item.get("id") for item in packet["evidence_passages"]]
            if passage_ids != expected_ids:
                raise SystemExit(f"{arm} packet passage IDs are not fixed")
        if case["harness_packet"]["evidence_passages"][:4] != case["direct_packet"]["evidence_passages"]:
            raise SystemExit("harness packet does not preserve the direct packet")


def validate_response(value: object, packet: dict) -> None:
    fields = set(RESULT_SCHEMA["properties"])
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("response fields do not match the frozen schema")
    if value["risk"] not in {"elevated", "ordinary"}:
        raise ValueError("invalid risk label")
    if value["confidence"] not in {"low", "medium", "high"}:
        raise ValueError("invalid confidence label")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise ValueError("missing rationale")
    valid_ids = {item["id"] for item in packet["evidence_passages"]}
    evidence = value["evidence_passage_ids"]
    signals = value["signals"]
    if not isinstance(evidence, list) or not evidence or len(evidence) > 5:
        raise ValueError("response must cite one to five evidence passages")
    if len(evidence) != len(set(evidence)) or any(item not in valid_ids for item in evidence):
        raise ValueError("response cites an invalid or repeated passage")
    if not isinstance(signals, list) or len(signals) > 5 or any(not isinstance(item, str) for item in signals):
        raise ValueError("invalid signals list")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output already exists; registered attempts are immutable")
    corpus = read(HERE / "corpus.json")
    registration = read(HERE / "REGISTRATION.json")
    validate_setup(corpus, registration)
    output.mkdir(parents=True)

    model = registration["model"]
    effort = registration["reasoning_effort"]
    schedule = registration["schedule"]
    cases = {case["id"]: case for case in corpus["cases"]}
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "registration_sha256": sha256(HERE / "REGISTRATION.json"),
        "gold_sha256_committed_before_inference": registration["sealed_gold_sha256"],
        "source_audit_sha256": sha256(HERE / "SOURCE_AUDIT.json"),
        "model": model,
        "reasoning_effort": effort,
        "tunnel": "local",
        "api_credentials_removed": True,
        "web_tools_plugins_skills_disabled": True,
        "fallback": False,
        "retries": 0,
        "calls_expected": len(schedule),
    }
    dump(output / "manifest.json", manifest)
    results = []
    started = time.perf_counter()
    for step in schedule:
        case_id, arm = step["case_id"], step["arm"]
        packet = cases[case_id][f"{arm}_packet"]
        transport = LocalTunnel(model=model, reasoning_effort=effort, timeout=args.timeout)
        row = {"case_id": case_id, "arm": arm, "status": "running", "result": None, "calls": []}
        try:
            value = transport.generate(
                stage=f"honest_system_holdout_v3_{arm}",
                instructions=POLICIES[arm],
                packet=packet,
                schema=RESULT_SCHEMA,
            )
            validate_response(value, packet)
        except Exception as exc:
            row.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                calls=transport.calls,
            )
        else:
            row.update(status="completed", result=value, calls=transport.calls)
        results.append(row)
        dump(output / "predictions.json", {
            "gold_loaded": False,
            "completed_steps": len(results),
            "expected_steps": len(schedule),
            "results": results,
        })
        print(json.dumps({"case_id": case_id, "arm": arm, "status": row["status"]}), flush=True)

    manifest.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": time.perf_counter() - started,
        "steps_completed": sum(row["status"] == "completed" for row in results),
        "calls_attempted": sum(len(row["calls"]) for row in results),
    })
    dump(output / "manifest.json", manifest)


if __name__ == "__main__":
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("CODEX_API_KEY", None)
    main()
