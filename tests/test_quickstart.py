"""Exercise first-run artifacts, budget changes, and existing-file preservation."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from newsverify.quickstart import run_quickstart


class QuickstartTests(unittest.TestCase):
    def test_complete_loop_and_saved_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            trace = run_quickstart(out)
            self.assertEqual("contradicted", trace["fact_status"])
            self.assertEqual("complete", trace["stop_reason"])
            self.assertEqual(3, trace["usage"]["rounds"])
            self.assertEqual(4, trace["usage"]["unique_versions"])
            self.assertTrue(trace["assessment_valid"])
            self.assertEqual([], trace["errors"])
            self.assertEqual(json.loads(json.dumps(trace)), json.loads((out / "trace.json").read_text()))
            inputs = json.loads((out / "inputs.json").read_text())
            self.assertEqual(json.loads(json.dumps(trace["target"])), inputs["target"])
            self.assertEqual(4, sum(len(items) for items in inputs["rounds"]))
            self.assertFalse(trace["new_model_inference"])
            self.assertIn("hand-authored", (out / "SUMMARY.md").read_text())

    def test_smaller_budget_stops_before_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            trace = run_quickstart(out, {"max_rounds": 1})
            self.assertEqual(1, trace["usage"]["rounds"])
            self.assertEqual("unresolved", trace["fact_status"])
            self.assertNotEqual("complete", trace["stop_reason"])
            self.assertEqual(1, json.loads((out / "config.json").read_text())["max_rounds"])

    def test_invalid_config_and_existing_directory_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            for config in [{"max_rounds": True}, {"max_rounds": 0}, {"api_key": "unused"}, []]:
                with self.subTest(config=config), self.assertRaises(ValueError):
                    run_quickstart(out, config)
                self.assertFalse(out.exists())
            out.mkdir()
            marker = out / "SUMMARY.md"
            marker.write_text("existing user result")
            with self.assertRaises(ValueError):
                run_quickstart(out)
            self.assertEqual("existing user result", marker.read_text())

    def test_cli_reads_config_and_reports_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"max_rounds": 1}')
            out = Path(directory) / "run"
            command = [sys.executable, "-m", "factcircuit", "quickstart",
                       "--config", str(config), "--output", str(out)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("0 model calls", result.stdout)
            repeated = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(2, repeated.returncode)
            self.assertIn("already exists", repeated.stderr)


if __name__ == "__main__":
    unittest.main()
