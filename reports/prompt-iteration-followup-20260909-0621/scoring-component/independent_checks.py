"""Independent fictional regression checks for scoring boundaries only."""
from copy import deepcopy
import unittest

from scoring import score


def fixture():
    plan = {"schema_version": 1, "case_ids": ["item_a7", "item_b9"],
            "conditions": ["direct", "news_tracing"], "arm_order": "alternating"}
    labels = {"schema_version": 1, "cases": [
        {"case_id": "item_a7", "assertion_scope": "real_world",
         "cutoff_expected": "unresolved", "future_expected": "contradicted",
         "independently_adjudicated": True},
        {"case_id": "item_b9", "assertion_scope": "real_world",
         "cutoff_expected": "supported", "future_expected": "supported",
         "independently_adjudicated": True},
    ]}
    rows = []
    for cid, arm, verdict in [
        ("item_a7", "direct", "unresolved"),
        ("item_a7", "news_tracing", "contradicted"),
        ("item_b9", "news_tracing", "contradicted"),
        ("item_b9", "direct", "supported"),
    ]:
        rows.append({"case_id": cid, "condition": arm, "execution_status": "completed",
                     "audit_passed": True, "pipeline_valid": True, "formal_valid": True,
                     "observed_verdict": verdict, "formal_verdict": verdict})
    return plan, labels, rows


class IndependentChecks(unittest.TestCase):
    def test_more_false_answers_do_not_look_like_an_accuracy_win(self):
        plan, labels, rows = fixture()
        before = deepcopy((plan, labels, rows))
        result = score(plan, rows, labels, batch_status="completed")
        direct, harness = (result["conditions"][arm] for arm in ("direct", "news_tracing"))
        self.assertEqual(direct["primary"]["cutoff_matches"], 2)
        self.assertEqual(harness["primary"]["cutoff_matches"], 0)
        self.assertEqual(direct["primary"]["future_matches"], 1)
        self.assertEqual(harness["primary"]["future_matches"], 1)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["called_false"], 1)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["cutoff_grounded_false_calls"], 0)
        self.assertEqual(harness["truth_strata"]["real_world_true"]["metrics"]["false_accusations"], 1)
        self.assertFalse(result["scope"]["superiority_established"])
        self.assertEqual((plan, labels, rows), before)

    def test_future_falsehood_is_not_inherited_from_authenticity_scope(self):
        plan, labels, rows = fixture()
        labels["cases"][0]["future_expected"] = "supported"
        result = score(plan, rows, labels, batch_status="completed")
        harness = result["conditions"]["news_tracing"]
        self.assertEqual(harness["truth_strata"]["real_world_false"]["cases"], 0)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["called_false"], 0)
        self.assertEqual(harness["truth_strata"]["real_world_true"]["cases"], 2)
        self.assertEqual(harness["truth_strata"]["real_world_true"]["metrics"]["false_accusations"], 2)
        self.assertFalse(result["rows"][1]["row_called_later_false_claim_false"])

    def test_attribution_is_never_a_real_world_false_detection(self):
        plan, labels, rows = fixture()
        labels["cases"][0]["assertion_scope"] = "attribution"
        result = score(plan, rows, labels, batch_status="completed")
        harness = result["conditions"]["news_tracing"]
        self.assertEqual(harness["truth_strata"]["attribution"]["metrics"]["contradicted"], 1)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["cases"], 0)
        self.assertFalse(result["rows"][1]["row_called_later_false_claim_false"])

    def test_failed_research_cannot_receive_formal_success_credit(self):
        plan, labels, rows = fixture()
        labels["cases"][0]["cutoff_expected"] = "contradicted"
        rows[1]["pipeline_valid"] = False
        rows[1]["execution_status"] = "failed"
        result = score(plan, rows, labels, batch_status="completed")
        harness = result["conditions"]["news_tracing"]
        self.assertEqual(harness["primary"]["denominator"], 2)
        self.assertEqual(harness["primary"]["cutoff_matches"], 0)
        self.assertEqual(harness["formal_diagnostic"]["cutoff_matches"], 1)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["called_false"], 0)
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["failed_or_invalid"], 1)

    def test_fatal_batch_keeps_plan_but_suppresses_comparison(self):
        plan, labels, rows = fixture()
        rows[3].update(execution_status="unexecuted", pipeline_valid=False,
                       formal_valid=False, observed_verdict=None, formal_verdict=None)
        result = score(plan, rows, labels, batch_status="fatal_worker_failure")
        self.assertEqual(result["planned_rows"], 4)
        self.assertEqual(len(result["rows"]), 4)
        self.assertFalse(result["primary_comparison_available"])
        for arm in result["conditions"].values():
            self.assertEqual(arm["primary"]["denominator"], 2)
            self.assertIsNone(arm["primary"]["cutoff_matches"])
            self.assertIsNone(arm["primary"]["future_match_rate"])
            for stratum in arm["truth_strata"].values():
                self.assertTrue(all(value is None for value in stratum["metrics"].values()))

    def test_deleting_bad_or_unfinished_rows_fails(self):
        for status in ("completed", "fatal_worker_failure"):
            plan, labels, rows = fixture()
            with self.subTest(status=status), self.assertRaises(ValueError):
                score(plan, rows[:3], labels, batch_status=status)

    def test_all_settled_and_uncertain_outputs_keep_stratum_denominators(self):
        for verdict in ("supported", "contradicted", "unresolved", "conflicting"):
            plan, labels, rows = fixture()
            for row in rows:
                row.update(observed_verdict=verdict, formal_verdict=verdict)
            result = score(plan, rows, labels, batch_status="completed")
            for arm in result["conditions"].values():
                with self.subTest(verdict=verdict):
                    self.assertEqual(arm["primary"]["denominator"], 2)
                    self.assertEqual(sum(arm["recorded_outcome_diagnostics"].values()), 2)
                    self.assertEqual(arm["recorded_outcome_diagnostics"][verdict], 2)
                    self.assertEqual(arm["truth_strata"]["real_world_false"]["cases"], 1)
                    self.assertEqual(arm["truth_strata"]["real_world_true"]["cases"], 1)
                    if verdict in {"unresolved", "conflicting"}:
                        self.assertEqual(arm["truth_strata"]["real_world_false"]["metrics"]["called_false"], 0)
                        self.assertEqual(arm["primary"]["future_matches"], 0)

    def test_unknown_usage_cannot_be_silently_recast_as_measured_zero(self):
        plan, labels, rows = fixture()
        rows[0]["usage"] = None
        with self.assertRaises(ValueError):
            score(plan, rows, labels, batch_status="completed")


if __name__ == "__main__":
    unittest.main()
