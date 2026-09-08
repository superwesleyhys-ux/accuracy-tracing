"""Local entry point contracts, including execution with networking blocked."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from newsverify.cli import main
from newsverify.local import run_local


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/local_trace.json"


class LocalTraceTests(unittest.TestCase):
    def test_cli_runs_without_network_and_preserves_materials(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with patch("socket.socket", side_effect=AssertionError("network forbidden")), redirect_stdout(StringIO()):
                self.assertEqual(main(["trace", str(EXAMPLE), "--output", str(output)]), 0)
            report = json.loads(output.read_text())
        payload = json.loads(EXAMPLE.read_text())
        self.assertEqual(report["execution_mode"], "local_snapshot_replay")
        self.assertEqual(report["target"], payload["target"])
        self.assertEqual(report["materials"][0]["content"], payload["rounds"][0][0]["content"])
        self.assertEqual(report["fact_status"], "not_checked")
        self.assertNotEqual(report["provenance_status"], "original_material_located")
        self.assertEqual(report["errors"], [])

    def test_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            original = EXAMPLE.read_text()
            source.write_text(original)
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["trace", str(source), "--output", str(source)]), 2)
            self.assertEqual(source.read_text(), original)

    def test_invalid_input_is_rejected(self):
        for payload in (None, {}, {"target": {}, "rounds": [1]},
                        {"target": {}, "rounds": [[1]]},
                        {"target": {}, "rounds": [], "config": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_local(payload)
