"""Build and test the installed first-run workflow in an isolated directory."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import venv

ROOT = Path(__file__).resolve().parents[1]


def smoke_first_run():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    result = {"status": "failed", "version": version, "platform": sys.platform,
              "python": sys.version.split()[0], "model_api_calls": 0,
              "new_model_inference": False}
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)

    def run(command, cwd):
        completed = subprocess.run([str(item) for item in command], cwd=cwd,
                                   env=environment, text=True, encoding="utf-8",
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=180, check=False)
        if completed.returncode:
            raise RuntimeError(completed.stdout[-2000:])
        return completed.stdout

    try:
        with tempfile.TemporaryDirectory(prefix="factcircuit-first-run-") as temporary:
            work = Path(temporary)
            wheelhouse = work / "wheels"
            wheelhouse.mkdir()
            run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
                 "--disable-pip-version-check", "--wheel-dir", wheelhouse], ROOT)
            # The distribution name is independent of the public CLI name.
            distribution = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"].replace("-", "_")
            wheels = list(wheelhouse.glob(f"{distribution}-{version}-*.whl"))
            if len(wheels) != 1:
                raise ValueError(f"expected one {distribution} wheel, found {len(wheels)}")
            wheel = wheels[0]
            virtualenv = work / "venv"
            venv.EnvBuilder(with_pip=True).create(virtualenv)
            binaries = virtualenv / ("Scripts" if sys.platform == "win32" else "bin")
            python = binaries / ("python.exe" if sys.platform == "win32" else "python")
            cli = binaries / ("newsverify.exe" if sys.platform == "win32" else "newsverify")
            run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel], work)
            output = run([cli, "demo"], work)
            if not output.strip():
                raise ValueError("installed newsverify demo returned no output")
            result.update(status="passed", wheel=wheel.name,
                          installed_version=version, outside_checkout=True,
                          installed_default_example="passed", compatibility_cli="passed")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result


if __name__ == "__main__":
    outcome = smoke_first_run()
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["status"] == "passed" else 1)
