"""One-command CPU setup for Linux, macOS and Windows; no model API credentials."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv

from setup_local_model import setup

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", default=".venv-local")
    parser.add_argument("--model-dir", default=".models")
    parser.add_argument("--config", default=".local/model.json")
    args = parser.parse_args()
    environment = (ROOT / args.venv).resolve()
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([
        str(python), "-m", "pip", "install", "--disable-pip-version-check",
        "-r", str(ROOT / "requirements-local.txt"),
    ], cwd=ROOT, check=True)
    config_path = (ROOT / args.config).resolve()
    setup(ROOT / args.model_dir, config_path)
    print("Local inference is configured. Run:")
    print(f'"{python}" "{ROOT / "experiments/local_inference.py"}" '
          f'--config "{config_path}" --output reports/my-local-inference')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
