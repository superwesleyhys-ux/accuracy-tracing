"""Write or verify hashes for every repository file in the release checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from newsverify import __version__

MANIFEST = ROOT / "RELEASE_MANIFEST.json"
SELF = "RELEASE_MANIFEST.json"


def repository_paths(include_untracked=False):
    command = ["git", "ls-files", "-z"]
    if include_untracked:
        command = [
            "git", "ls-files", "-z", "--cached", "--others",
            "--exclude-standard",
        ]
    completed = subprocess.run(
        command, cwd=ROOT, stdout=subprocess.PIPE, check=True)
    paths = sorted({
        value.decode("utf-8")
        for value in completed.stdout.split(b"\0") if value
    })
    return [path for path in paths if path != SELF]


def record(path):
    payload = (ROOT / path).read_bytes()
    return {
        "path": path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def expected(include_untracked=False):
    return {
        "project": "accuracy tracing",
        "version": __version__,
        "scope": "all git-tracked release checkout files except this self-referential manifest",
        "files": [record(path) for path in repository_paths(include_untracked)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "check"))
    args = parser.parse_args()
    if args.mode == "write":
        MANIFEST.write_text(
            json.dumps(expected(include_untracked=True), indent=2) + "\n",
            encoding="utf-8")
        print(f"wrote {MANIFEST}")
        return 0
    actual = json.loads(MANIFEST.read_text(encoding="utf-8"))
    wanted = expected(include_untracked=False)
    if actual != wanted:
        print("RELEASE_MANIFEST.json is stale or incomplete", file=sys.stderr)
        return 1
    print(f"verified {len(wanted['files'])} release files for {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
