"""Release metadata checks that run inside the existing CI test job."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

import factcircuit
import newsverify
from scripts import validate_release


ROOT = Path(__file__).resolve().parents[1]


class ReleaseIntegrityTests(unittest.TestCase):
    def test_project_and_runtime_versions_match(self):
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["name"], "factcircuit")
        self.assertEqual(project["project"]["version"], factcircuit.__version__)
        self.assertEqual(factcircuit.__version__, newsverify.__version__)

    def test_release_manifest_matches_git_checkout(self):
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)
        if probe.returncode:
            self.skipTest("manifest completeness needs a git checkout")
        checked = subprocess.run(
            [sys.executable, "scripts/release_manifest.py", "check"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        self.assertEqual(0, checked.returncode, checked.stdout)

    def test_manifest_contains_staged_runtime_and_current_validation(self):
        manifest = json.loads(
            (ROOT / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}
        required = {
            "experiments/prompt_specs.py",
            "experiments/staged_semantic.py",
            "experiments/target_plan.py",
            "experiments/historical_compare.py",
            "experiments/historical-2023/freeze.json",
            "experiments/historical-2023/gold.json",
            "experiments/historical-2023/inputs.json",
            "experiments/historical-2023/sources.json",
            "tests/test_staged_semantic.py",
            "tests/test_historical_compare.py",
            "docs/HISTORICAL_2023_BENCHMARK.md",
            f"reports/historical-2023-audit-v{factcircuit.__version__}.json",
            f"reports/VALIDATION_V{factcircuit.__version__}.md",
            f"reports/package-smoke-v{factcircuit.__version__}.json",
        }
        self.assertEqual(set(), required - paths)

    def test_historical_release_audit_is_scoped_and_saved(self):
        with tempfile.TemporaryDirectory(prefix="historical-audit-test-") as tmp:
            output = Path(tmp) / "audit.json"
            audit = validate_release.historical_benchmark_audit(output)

            self.assertEqual("passed", audit["status"])
            self.assertEqual(8, audit["case_count"])
            self.assertEqual({"true": 4, "false": 4}, audit["labels"])
            self.assertFalse(audit["corpus_synthetic"])
            self.assertEqual({
                "contract_audit_performed": True,
                "remote_artifacts_independently_authenticated": False,
                "live_model_ab_performed": False,
                "accuracy_measured": False,
            }, audit["release_validation_scope"])
            self.assertEqual(
                audit, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
