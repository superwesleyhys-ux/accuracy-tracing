from copy import deepcopy
import json
from pathlib import Path
import unittest

from newsverify.comparison import compare


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        self.gold = json.loads((examples / "evaluation_gold.json").read_text())
        self.a = json.loads((examples / "evaluation_predictions.json").read_text())
        self.a["run"] = {"name": "handwritten-baseline", "model_id": "no-model-fixture",
                         "corpus_id": "synthetic-v1", "per_target_budget": {
                             "retrieval_calls": 3, "model_tokens": 1000, "wall_seconds": 60}}
        for case in self.a["cases"]:
            case["usage"] = {"retrieval_calls": 0, "model_tokens": 0, "wall_seconds": 0}
        self.b = deepcopy(self.a)
        self.b["run"]["name"] = "handwritten-candidate"

    def test_identical_predictions_have_zero_paired_change(self):
        result = compare(self.gold, self.a, self.b, bootstrap_samples=20)
        row = result["differences"]["classification_accuracy"]
        self.assertEqual(row["delta"], 0)
        self.assertEqual(row["event_bootstrap95"], [0, 0])
        self.assertEqual(result["conclusion"], "synthetic_no_realworld_claim")

    def test_budget_mismatch_rejected(self):
        self.b["run"]["per_target_budget"]["model_tokens"] = 2000
        with self.assertRaisesRegex(ValueError, "matching per_target_budget"):
            compare(self.gold, self.a, self.b, bootstrap_samples=20)

    def test_different_model_or_corpus_rejected(self):
        for key in ("model_id", "corpus_id"):
            with self.subTest(key=key):
                changed = deepcopy(self.b)
                changed["run"][key] = "different"
                with self.assertRaisesRegex(ValueError, f"matching {key}"):
                    compare(self.gold, self.a, changed, bootstrap_samples=20)

    def test_missing_usage_and_overrun_rejected(self):
        for usage in ({}, {"retrieval_calls": 4, "model_tokens": 0, "wall_seconds": 0}):
            self.b["cases"][0]["usage"] = usage
            with self.assertRaises(ValueError):
                compare(self.gold, self.a, self.b, bootstrap_samples=20)

    def test_one_event_does_not_produce_false_precision(self):
        for case in self.gold["cases"]:
            case["event_id"] = "one-event"
        result = compare(self.gold, self.a, self.b, bootstrap_samples=20)
        self.assertIsNone(result["differences"]["classification_accuracy"]["event_bootstrap95"])

    def test_seed_is_reproducible(self):
        self.b["cases"][3]["decision"] = "false"
        first = compare(self.gold, self.a, self.b, bootstrap_samples=20, seed=12)
        self.assertEqual(first, compare(self.gold, self.a, self.b, bootstrap_samples=20, seed=12))


if __name__ == "__main__":
    unittest.main()
