#!/usr/bin/env python3
"""Run the single-pass candidate without loading later-outcome labels."""

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

from newsverify.early_risk import run_early_risk  # noqa: E402
from newsverify.tunnels import LocalTunnel  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    corpus_path = args.corpus.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output already exists; prior attempts are immutable")
    output.mkdir(parents=True)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise SystemExit("the registered eight-case corpus is required")
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "tunnel": "local",
        "api_credentials_removed": True,
        "fallback": False,
        "model_calls_per_case": 1,
        "case_ids": [case["target"]["id"] for case in cases],
        "corpus_sha256": sha(corpus_path),
        "code_sha256": {
            "early_risk.py": sha(ROOT / "newsverify/early_risk.py"),
            "tunnels.py": sha(ROOT / "newsverify/tunnels.py"),
            "run_test.py": sha(__file__),
            "protocol.md": sha(HERE / "PROTOCOL.md"),
        },
    }
    dump(output / "manifest.json", manifest)
    dump(output / "corpus.json", corpus)
    results = []
    started = time.perf_counter()
    for case in cases:
        case_id = case["target"]["id"]
        transport = LocalTunnel(args.model, args.reasoning_effort, args.timeout)
        row = {"id": case_id, "status": "running", "result": None, "calls": []}
        try:
            result = run_early_risk(case, transport=transport)
        except Exception as exc:
            row.update(status="failed", error=f"{type(exc).__name__}: {exc}", calls=transport.calls)
        else:
            row.update(status="completed", result=result, calls=transport.calls)
        results.append(row)
        dump(output / "predictions.json", {
            "gold_loaded": False, "results": results,
            "completed": len(results), "expected": len(cases),
        })
        print(json.dumps({"id": case_id, "status": row["status"],
                          "calls": len(row["calls"])}), flush=True)
    manifest.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": time.perf_counter() - started,
        "completed_cases": sum(row["status"] == "completed" for row in results),
        "attempted_calls": sum(len(row["calls"]) for row in results),
    })
    dump(output / "manifest.json", manifest)


if __name__ == "__main__":
    # Ensure an accidental API key cannot alter the selected local-only route.
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("CODEX_API_KEY", None)
    main()
