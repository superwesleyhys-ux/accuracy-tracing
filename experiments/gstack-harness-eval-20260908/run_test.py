"""Fresh, frozen comparison using the existing recorded local/API transports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(ROOT))
OLD_RUNNER = ROOT / "experiments/double-loop-pilot/run_test.py"
shared = runpy.run_path(str(OLD_RUNNER))
dump, run_one = shared["dump"], shared["run_one"]
DIRECT_PROMPT = (
    shared["DIRECT_PROMPT"] + " Each quote must be nonempty and occur exactly once "
    "in its cited material. Give a nonempty rationale; a verdict other than "
    "unresolved requires at least one relevant basis entry."
)
# Reuse the established recording path with a neutral, equally strict citation
# contract. This changes only this process, never the historical runner file.
run_one.__globals__["DIRECT_PROMPT"] = DIRECT_PROMPT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    parser.add_argument("--tunnel", choices=("local", "api"), default="local")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    corpus = json.loads((DATA / "corpus.json").read_text())
    cases = corpus["cases"]
    assert len(cases) == 6 and len({c["target"]["id"] for c in cases}) == 6
    from newsverify.provenance import MaterialVersion, _material_eligibility, _time
    for case in cases:
        cutoff = _time(case["target"]["as_of"], "cutoff")
        assert all(not _material_eligibility(MaterialVersion(**m), cutoff)
                   for m in case["materials"]), "Both arms must have the same eligible pool"
        assert len(case["initial_version_ids"]) == 1
        assert case["initial_version_ids"][0] in {m["version_id"] for m in case["materials"]}
    review = json.loads((HERE / "PRE_RUN_REVIEW.json").read_text())
    assert review["passed"] and review["corpus_sha256"] == sha(DATA / "corpus.json")
    assert review["gold_sha256"] == sha(DATA / "gold.json")
    isolation = json.loads((HERE / "ISOLATION_REVIEW.json").read_text())
    assert isolation["passed"], "Local prompt isolation has not been verified"
    files = [OLD_RUNNER, ROOT / "experiments/double-loop-pilot/summarize_test.py"]
    files += sorted(HERE.glob("*.py"))
    files += sorted(ROOT.glob("newsverify/*.py")) + sorted(ROOT.glob("tests/test_*.py"))
    files += sorted(p for p in DATA.rglob("*") if p.is_file())
    files += sorted(HERE.glob("*.md")) + sorted(HERE.glob("*.json"))
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    manifest = {
        "started_at": now(), "model": "gpt-6-astra", "reasoning_effort": "medium",
        "tunnel": args.tunnel, "workers": 1, "case_count": len(cases), "event_family_count": 3,
        "timeout_seconds_per_call": 90, "max_model_calls_per_harness_case": 10,
        "max_total_logical_calls": 66, "orchestration_retries": 0,
        "internal_cli_transport_retries": "not controlled or counted separately",
        "cross_route_fallback": False,
        "direct_prompt": DIRECT_PROMPT, "frozen_sha256": hashes,
        "corpus_path": str((DATA / "corpus.json").relative_to(ROOT)),
        "gold_path": str((DATA / "gold.json").relative_to(ROOT)),
        "local_connection_profile": "explicit ephemeral Codex-login HTTP" if args.tunnel == "local" else None,
        "local_profile_options": shared["PROFILE"] if args.tunnel == "local" else None,
        "dataset_kind": "six constructed cases from three fresh event families",
        "held_out": False, "equal_token_budget": False,
        "baseline_evidence_access": "entire eligible frozen pool immediately",
        "harness_evidence_access": "initial source followed by model-selected eligible sources",
        "gstack_role": "development review and evaluation workflow; no skill prompt treatment",
    }
    if args.dry_run:
        print(json.dumps({k: v for k, v in manifest.items() if k != "frozen_sha256"}, indent=2))
        return
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    for name, expected in hashes.items():
        destination = folder / "frozen-inputs" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        assert sha(destination) == expected
    dump(folder / "manifest.json", manifest)
    if args.tunnel == "local":
        shared["tunnels"].subprocess = shared["LocalHTTPProcess"]()
    awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
    started = time.perf_counter()
    results = []
    try:
        for index, case in enumerate(cases):
            order = ("direct", "double_loop") if index % 2 == 0 else ("double_loop", "direct")
            for condition in order:
                results.append(run_one(case, condition, folder, manifest))
                dump(folder / "progress.json", {"completed": len(results), "expected": 12})
    finally:
        awake.terminate()
        awake.wait(timeout=10)
    manifest.update(finished_at=now(), timer_seconds=time.perf_counter() - started)
    manifest["utc_elapsed_seconds"] = (datetime.fromisoformat(manifest["finished_at"]) - datetime.fromisoformat(manifest["started_at"])).total_seconds()
    manifest["integrity_checks"] = {name: sha(ROOT / name) == expected for name, expected in hashes.items()}
    # Gold is parsed only after inference and never passed to either condition.
    gold = json.loads((DATA / "gold.json").read_text())
    dump(folder / "manifest.json", manifest)
    dump(folder / "all-results.json", {"manifest": manifest, "gold": gold, "results": results})
    assert all(manifest["integrity_checks"].values()), "Frozen inputs changed during inference"


if __name__ == "__main__":
    main()
