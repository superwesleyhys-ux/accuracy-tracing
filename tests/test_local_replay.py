"""Offline execution must not inherit API auth or hide semantic failures."""
from argparse import Namespace
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import local_replay


class LocalReplayTests(unittest.TestCase):
    def args(self, output, gold=True):
        data = ROOT / "experiments/historical-2023-pilot2-v3"
        return Namespace(
            archive=str(ROOT / "reports/historical-2023-pilot2-v3-live-001"),
            inputs=str(data / "inputs.json"), sources=str(data / "sources.json"),
            freeze=str(data / "freeze.json"),
            gold=str(data / "gold.json") if gold else None, output=str(output))

    def test_runs_without_network_or_credentials_and_retains_control_error(self):
        for auth in ({}, {"OPENAI_API_KEY": "invalid-test-value"}):
            with self.subTest(configured=bool(auth)), tempfile.TemporaryDirectory() as tmp:
                with patch.dict(os.environ, auth, clear=True), \
                        patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                        patch.object(local_replay.historical.loop_compare, "BudgetClient",
                                     side_effect=AssertionError("API client forbidden")):
                    report = local_replay.replay(self.args(Path(tmp) / "run"))
                self.assertEqual("completed", report["execution_status"])
                self.assertEqual("has_errors", report["verification_status"])
                self.assertEqual({"required": False, "status": "not_used", "requests": 0}, report["api"])
                self.assertFalse(report["new_model_inference"])
                self.assertFalse(report["new_accuracy_measurement"])
                self.assertEqual(52, report["replayed_call_records"])
                self.assertEqual(6, len(report["results"]))
                failures = [row for row in report["results"]
                            if row["verification_status"] == "error"]
                self.assertEqual(1, len(failures))
                self.assertEqual("staged", failures[0]["arm"])
                self.assertEqual("full_evidence_once", failures[0]["variant"])
                self.assertIn("conclusive probe", failures[0]["errors"][0]["message"])
                scores = report["scores"]["main_cases"]
                self.assertEqual((1, 2), (scores["monolithic"]["correct"], scores["staged"]["correct"]))

    def test_gold_is_optional_and_only_opened_after_all_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = local_replay.historical.validate_all
            output = Path(tmp) / "scored"
            def validate_after_replay(*args):
                report = json.loads((output / "results.json").read_text())
                self.assertEqual(6, len(report["results"]))
                self.assertEqual("completed", report["execution_status"])
                return original(*args)
            with patch.object(local_replay.historical, "validate_all", side_effect=validate_after_replay):
                self.assertIsNotNone(local_replay.replay(self.args(output))["scores"])
            with patch.object(local_replay.historical, "validate_all", side_effect=AssertionError("gold forbidden")):
                report = local_replay.replay(self.args(Path(tmp) / "unscored", gold=False))
                self.assertIsNone(report["scores"])

    def test_rejects_corrupted_call_output_before_replay(self):
        original = local_replay.historical._json
        def corrupted(path):
            data = original(path)
            if str(path).endswith("virgin-galactic-commercial-service-2023-loop-calls.json"):
                data = deepcopy(data)
                data[0]["output"] += " "
            return data
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            with patch.object(local_replay.historical, "_json", side_effect=corrupted):
                with self.assertRaisesRegex(ValueError, "model output"):
                    local_replay.replay(self.args(output))
            self.assertFalse(output.exists())

    def test_request_mismatch_is_execution_failure_without_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(local_replay.historical, "_offline_replay_trace",
                              side_effect=ValueError("logged request mismatch")):
                report = local_replay.replay(self.args(Path(tmp) / "run"))
            self.assertEqual("has_errors", report["execution_status"])
            self.assertEqual("incomplete", report["verification_status"])
            self.assertEqual(6, len(report["results"]))
            self.assertIsNone(report["scores"])
            self.assertEqual(0, report["api"]["requests"])

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "keep.txt"
            marker.write_text("original")
            with self.assertRaises(FileExistsError):
                local_replay.replay(self.args(tmp))
            self.assertEqual("original", marker.read_text())


if __name__ == "__main__":
    unittest.main()
