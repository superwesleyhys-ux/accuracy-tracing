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
            wheel, = wheelhouse.glob(f"factcircuit-{version}-*.whl")
            virtualenv = work / "venv"
            venv.EnvBuilder(with_pip=True).create(virtualenv)
            binaries = virtualenv / ("Scripts" if sys.platform == "win32" else "bin")
            python = binaries / ("python.exe" if sys.platform == "win32" else "python")
            cli = binaries / ("factcircuit.exe" if sys.platform == "win32" else "factcircuit")
            run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel], work)
            actual_version = run([python, "-I", "-m", "factcircuit", "--version"], work).strip()
            if actual_version != f"factcircuit {version}":
                raise ValueError("installed version does not match the built release")
            run([cli, "quickstart", "--output", work / "first-run"], work)
            trace = json.loads((work / "first-run" / "trace.json").read_text())
            if (trace["fact_status"] != "contradicted" or trace["stop_reason"] != "complete"
                    or trace["usage"]["rounds"] != 3 or trace["usage"]["unique_versions"] != 4
                    or not trace["assessment_valid"] or trace["errors"]):
                raise ValueError("installed default example did not meet documented expectations")
            if trace["model_api_calls"] != 0 or trace["new_model_inference"]:
                raise ValueError("offline example must not report model inference")
            config = work / "limited.json"
            config.write_text('{"max_rounds": 1}', encoding="utf-8")
            run([python, "-I", "-m", "factcircuit", "quickstart", "--config", config,
                 "--output", work / "limited-run"], work)
            limited = json.loads((work / "limited-run" / "trace.json").read_text())
            if limited["fact_status"] != "unresolved" or limited["usage"]["rounds"] != 1:
                raise ValueError("installed limited-budget example ignored the supplied config")
            run([python, "-I", "-m", "newsverify", "demo"], work)
            result.update(status="passed", wheel=wheel.name,
                          installed_version=actual_version,
                          outside_checkout=True, installed_default_example="passed",
                          installed_configured_example="passed", compatibility_cli="passed")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    return result


if __name__ == "__main__":
    outcome = smoke_first_run()
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["status"] == "passed" else 1)
