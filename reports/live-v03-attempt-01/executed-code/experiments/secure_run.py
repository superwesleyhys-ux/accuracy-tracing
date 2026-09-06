"""Read API authentication without echo; never persist it or print remote errors."""
import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import sys
import loop_compare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if Path(args.output).exists(): raise SystemExit("Output exists; preserve prior attempts")
    if not sys.stdin.isatty(): raise SystemExit("An echo-disabled terminal is required")
    logging.disable(logging.CRITICAL)
    secret = getpass.getpass("API credential (hidden): ")
    os.environ["OPENAI_API_KEY"] = secret
    del secret
    root = Path(__file__).resolve().parent
    try:
        status = loop_compare.run(argparse.Namespace(inputs=str(root / "inputs-v03.json"),
            output=args.output, model="gpt-6-astra", max_rounds=5))
        if (Path(args.output) / "results.json").exists():
            status = max(status, loop_compare.score(argparse.Namespace(gold=str(root / "gold-v03.json"), run=args.output)))
        return status
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "stopped", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1)
