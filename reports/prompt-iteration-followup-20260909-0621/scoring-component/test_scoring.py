"""Fictional declaration fixtures only; no real sources, labels or inference."""
from copy import deepcopy
import unittest

from scoring import score, validate_plan


def fixture():
    plan = {"schema_version": 1, "case_ids": ["fictional_a", "fictional_b"],
            "conditions": ["direct", "news_tracing"], "arm_order": "alternating"}
    labels = {"schema_version": 1, "cases": [
        {"case_id": "fictional_a", "assertion_scope": "real_world",
         "cutoff_expected": "contradicted", "future_expected": "contradicted",
         "independently_adjudicated": True},
        {"case_id": "fictional_b", "assertion_scope": "real_world",
         "cutoff_expected": "supported", "future_expected": "supported",
         "independently_adjudicated": True}]}
    outcomes = []
    for cid, arm in validate_plan(plan):
        verdict = "contradicted" if cid == "fictional_a" else "supported"
        outcomes.append({"case_id": cid, "condition": arm, "execution_status": "completed",
                         "audit_passed": True, "pipeline_valid": True, "formal_valid": True,
                         "observed_verdict": verdict, "formal_verdict": verdict})
    return plan, outcomes, labels


def set_verdict(row, value):
    row.update(observed_verdict=value, formal_verdict=value)


class MixedScoringTests(unittest.TestCase):
    def result(self, values=None, status="completed"):
        return score(*(values or fixture()), batch_status=status)

    def test_valid_pair_has_all_four_rows_and_distinct_truth_strata(self):
        result = self.result()
        self.assertTrue(result["primary_comparison_available"])
        self.assertEqual(result["planned_rows"], 4)
        for arm in result["conditions"].values():
            self.assertEqual(arm["primary"], {"available": True, "denominator": 2,
                "cutoff_matches": 2, "future_matches": 2,
                "cutoff_match_rate": 1.0, "future_match_rate": 1.0})
            strata = arm["truth_strata"]
            self.assertEqual(strata["real_world_false"]["metrics"]["called_false"], 1)
            self.assertEqual(strata["real_world_true"]["metrics"]["true_acceptances"], 1)
            self.assertEqual(strata["attribution"]["cases"], 0)
            self.assertIsNone(strata["attribution"]["primary"]["cutoff_match_rate"])

    def test_true_claim_called_false_is_false_accusation_not_detection(self):
        values = fixture()
        set_verdict(values[1][2], "contradicted")
        result = self.result(values)
        harness = result["conditions"]["news_tracing"]
        self.assertEqual(harness["primary"]["cutoff_matches"], 1)
        self.assertEqual(harness["truth_strata"]["real_world_true"]["metrics"]["false_accusations"], 1)
        row = result["rows"][2]
        self.assertTrue(row["row_true_control_false_accusation"])
        self.assertFalse(row["row_called_later_false_claim_false"])
        self.assertFalse(row["row_false_acceptance"])

    def test_false_claim_accepted_is_false_acceptance(self):
        values = fixture()
        set_verdict(values[1][0], "supported")
        result = self.result(values)
        metrics = result["conditions"]["direct"]["truth_strata"]["real_world_false"]["metrics"]
        self.assertEqual(metrics["false_acceptances"], 1)
        self.assertEqual(metrics["called_false"], 0)

    def test_failed_research_preserves_correct_formal_diagnostic_only(self):
        values = fixture()
        values[1][1].update(execution_status="failed", pipeline_valid=False)
        result = self.result(values)
        harness = result["conditions"]["news_tracing"]
        self.assertEqual(harness["primary"]["denominator"], 2)
        self.assertEqual(harness["primary"]["cutoff_matches"], 1)
        self.assertEqual(harness["primary"]["cutoff_match_rate"], 0.5)
        self.assertEqual(harness["formal_diagnostic"]["cutoff_matches"], 2)
        self.assertFalse(result["rows"][1]["row_called_later_false_claim_false"])
        self.assertEqual(harness["truth_strata"]["real_world_false"]["metrics"]["failed_or_invalid"], 1)

    def test_correct_future_false_call_can_be_unsupported_at_cutoff(self):
        values = fixture()
        values[2]["cases"][0]["cutoff_expected"] = "unresolved"
        result = self.result(values)
        row = result["rows"][0]
        self.assertTrue(row["row_future_match"])
        self.assertFalse(row["row_cutoff_match"])
        self.assertTrue(row["row_called_later_false_claim_false"])
        self.assertFalse(row["row_cutoff_grounded_false_call"])
        primary = result["conditions"]["direct"]["primary"]
        self.assertEqual((primary["cutoff_matches"], primary["future_matches"]), (1, 2))

    def test_unresolved_future_false_claim_is_abstention_never_detection(self):
        values = fixture()
        values[2]["cases"][0]["cutoff_expected"] = "unresolved"
        set_verdict(values[1][0], "unresolved")
        result = self.result(values)
        self.assertTrue(result["rows"][0]["row_cutoff_match"])
        self.assertFalse(result["rows"][0]["row_future_match"])
        metrics = result["conditions"]["direct"]["truth_strata"]["real_world_false"]["metrics"]
        self.assertEqual((metrics["abstentions"], metrics["called_false"]), (1, 0))

    def test_conflict_is_neither_detection_acceptance_nor_abstention(self):
        values = fixture()
        set_verdict(values[1][0], "conflicting")
        result = self.result(values)
        metrics = result["conditions"]["direct"]["truth_strata"]["real_world_false"]["metrics"]
        self.assertEqual((metrics["conflicts"], metrics["called_false"], metrics["false_acceptances"], metrics["abstentions"]), (1, 0, 0, 0))

    def test_attribution_falsehood_is_never_real_world_detection(self):
        values = fixture()
        values[2]["cases"][0]["assertion_scope"] = "attribution"
        result = self.result(values)
        self.assertFalse(result["rows"][0]["row_called_later_false_claim_false"])
        strata = result["conditions"]["direct"]["truth_strata"]
        self.assertEqual(strata["attribution"]["metrics"]["contradicted"], 1)
        self.assertEqual(strata["real_world_false"]["cases"], 0)

    def test_attribution_acceptance_is_not_accepting_false_reality(self):
        values = fixture()
        values[2]["cases"][0]["assertion_scope"] = "attribution"
        set_verdict(values[1][0], "supported")
        result = self.result(values)
        self.assertFalse(result["rows"][0]["row_false_acceptance"])
        self.assertEqual(result["conditions"]["direct"]["truth_strata"]["attribution"]["metrics"]["supported"], 1)

    def test_invalid_formal_result_never_earns_credit(self):
        values = fixture()
        values[1][0].update(pipeline_valid=False, formal_valid=False)
        row = self.result(values)["rows"][0]
        self.assertFalse(row["row_cutoff_match"])
        self.assertFalse(row["formal_cutoff_match"])
        self.assertEqual(row["classification"], "failed_or_invalid")

    def test_recorded_failure_without_verdict_retains_denominator(self):
        values = fixture()
        values[1][0].update(execution_status="failed", pipeline_valid=False, formal_valid=False,
                            observed_verdict=None, formal_verdict=None)
        result = self.result(values)
        self.assertTrue(result["primary_comparison_available"])
        self.assertEqual(result["conditions"]["direct"]["primary"]["denominator"], 2)
        self.assertEqual(result["conditions"]["direct"]["primary"]["cutoff_matches"], 1)

    def test_fatal_batch_retains_rows_but_suppresses_all_primary_metrics(self):
        values = fixture()
        for row in values[1][2:]:
            row.update(execution_status="unexecuted", pipeline_valid=False, formal_valid=False,
                       observed_verdict=None, formal_verdict=None)
        result = self.result(values, "fatal_worker_failure")
        self.assertFalse(result["primary_comparison_available"])
        self.assertEqual(len(result["rows"]), 4)
        self.assertTrue(result["rows"][0]["row_cutoff_match"])
        for arm in result["conditions"].values():
            self.assertEqual(arm["primary"]["denominator"], 2)
            self.assertFalse(arm["primary"]["available"])
            for key in ("cutoff_matches", "future_matches", "cutoff_match_rate", "future_match_rate"):
                self.assertIsNone(arm["primary"][key])
            self.assertEqual(arm["formal_diagnostic"]["cutoff_matches"], 1)
            self.assertEqual(arm["execution_status_counts"]["unexecuted"], 1)
            for stratum in arm["truth_strata"].values():
                self.assertFalse(stratum["metrics_available"])
                self.assertTrue(all(v is None for v in stratum["metrics"].values()))

    def test_fatal_status_suppresses_primary_even_if_all_rows_recorded(self):
        result = self.result(status="fatal_worker_failure")
        self.assertFalse(result["primary_comparison_available"])
        self.assertIsNone(result["conditions"]["direct"]["primary"]["cutoff_matches"])

    def test_unexecuted_rows_rejected_in_completed_batch(self):
        values = fixture()
        values[1][0].update(execution_status="unexecuted", pipeline_valid=False, formal_valid=False,
                            observed_verdict=None, formal_verdict=None)
        with self.assertRaises(ValueError):
            self.result(values)

    def test_unexecuted_rows_cannot_contain_results(self):
        values = fixture()
        values[1][0].update(execution_status="unexecuted", pipeline_valid=False, formal_valid=False)
        with self.assertRaises(ValueError):
            self.result(values, "fatal_worker_failure")

    def test_missing_duplicate_and_reordered_rows_reject(self):
        for change in (lambda rows: rows.pop(), lambda rows: rows.__setitem__(1, deepcopy(rows[0])),
                       lambda rows: rows.reverse()):
            with self.subTest(change=change):
                values = fixture()
                change(values[1])
                for status in ("completed", "fatal_worker_failure"):
                    with self.assertRaises(ValueError):
                        self.result(values, status)

    def test_unknown_case_and_arm_reject(self):
        for key, value in (("case_id", "fictional_unknown"), ("condition", "api")):
            values = fixture()
            values[1][0][key] = value
            with self.assertRaises(ValueError):
                self.result(values)

    def test_bool_integer_and_nonbool_audit_flags_reject(self):
        for key in ("pipeline_valid", "formal_valid", "audit_passed"):
            for value in (1, 0, "true", None):
                values = fixture()
                values[1][0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.result(values)
        values = fixture()
        values[1][0]["audit_passed"] = False
        with self.assertRaises(ValueError):
            self.result(values)

    def test_contradictory_validity_states_reject(self):
        for patch in ({"formal_valid": False}, {"execution_status": "failed"},
                      {"observed_verdict": None}, {"formal_verdict": None}):
            values = fixture()
            values[1][0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.result(values)

    def test_formal_observed_mismatch_rejects_even_when_primary_invalid(self):
        for pipeline_valid in (True, False):
            values = fixture()
            values[1][0].update(pipeline_valid=pipeline_valid, formal_verdict="supported")
            with self.assertRaises(ValueError):
                self.result(values)

    def test_unknown_or_nonstring_verdicts_reject(self):
        for value in ("false", "execution_failed", True, 1, [], {}):
            values = fixture()
            set_verdict(values[1][0], value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.result(values)

    def test_label_scope_membership_and_extra_fields_reject(self):
        mutations = [lambda x: x.update(assertion_scope="authenticity_control"),
                     lambda x: x.update(cutoff_expected="unknown"),
                     lambda x: x.update(future_expected="unresolved"),
                     lambda x: x.update(case_id="outside_plan"),
                     lambda x: x.update(quote="Not admitted here"),
                     lambda x: x.update(independently_adjudicated=False),
                     lambda x: x.update(independently_adjudicated=1)]
        for mutate in mutations:
            values = fixture()
            mutate(values[2]["cases"][0])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.result(values)

    def test_missing_duplicate_reordered_and_bool_schema_labels_reject(self):
        for mutation in (lambda x: x["cases"].pop(), lambda x: x["cases"].reverse(),
                         lambda x: x["cases"].__setitem__(1, deepcopy(x["cases"][0])),
                         lambda x: x.update(schema_version=True)):
            values = fixture()
            mutation(values[2])
            with self.assertRaises(ValueError):
                self.result(values)

    def test_plan_cannot_change_scope_or_smuggle_labels(self):
        for patch in ({"schema_version": True}, {"case_ids": ["fictional_a", "fictional_a"]},
                      {"case_ids": ["fictional_a"]}, {"case_ids": [True, "fictional_a"]},
                      {"conditions": ["news_tracing", "direct"]}, {"arm_order": "random"},
                      {"gold": "forbidden"}):
            values = fixture()
            values[0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.result(values)

    def test_batch_status_required_and_validated(self):
        with self.assertRaises(TypeError):
            score(*fixture())
        for value in ("partial", True, None, []):
            with self.assertRaises(ValueError):
                self.result(status=value)

    def test_arm_order_requires_exact_string_type(self):
        class DerivedString(str):
            pass
        values = fixture()
        values[0]["arm_order"] = DerivedString("alternating")
        with self.assertRaises(ValueError):
            self.result(values)

    def test_settled_cutoff_mismatch_visible_in_both_truth_strata(self):
        values = fixture()
        for label in values[2]["cases"]:
            label["cutoff_expected"] = "unresolved"
        result = self.result(values)
        direct = result["conditions"]["direct"]
        self.assertEqual(direct["recorded_settled_cutoff_mismatches"], 2)
        for name in ("real_world_false", "real_world_true"):
            self.assertEqual(direct["truth_strata"][name]["recorded_settled_cutoff_mismatches"], 1)
        self.assertTrue(all(row["row_settled_cutoff_mismatch"] for row in result["rows"]))
        self.assertEqual(direct["primary"]["cutoff_matches"], 0)
        self.assertEqual(direct["primary"]["future_matches"], 2)

    def test_conflicting_and_failed_predictions_are_not_settled_mismatches(self):
        values = fixture()
        set_verdict(values[1][0], "conflicting")
        values[1][3].update(execution_status="failed", pipeline_valid=False)
        set_verdict(values[1][3], "contradicted")
        result = self.result(values)
        self.assertEqual(result["conditions"]["direct"]["recorded_settled_cutoff_mismatches"], 0)
        self.assertFalse(result["rows"][0]["row_settled_cutoff_mismatch"])
        self.assertFalse(result["rows"][3]["row_settled_cutoff_mismatch"])

    def test_tokens_and_other_unvalidated_fields_cannot_enter_module(self):
        for key, value in (("usage", None), ("total_tokens", 0), ("rationale", "fictional")):
            values = fixture()
            values[1][0][key] = value
            with self.assertRaises(ValueError):
                self.result(values)
        result = self.result()
        self.assertFalse(result["scope"]["token_accounting_included"])
        self.assertFalse(result["scope"]["admission_or_request_audit_proved"])
        self.assertFalse(result["scope"]["superiority_established"])

    def test_inputs_are_not_mutated_and_output_counts_reconcile(self):
        values = fixture()
        saved = deepcopy(values)
        result = self.result(values)
        self.assertEqual(values, saved)
        for arm in result["conditions"].values():
            self.assertEqual(sum(arm["recorded_outcome_diagnostics"].values()), arm["planned_rows"])
            self.assertEqual(sum(s["cases"] for s in arm["truth_strata"].values()), arm["planned_rows"])
        result["rows"][0]["observed_verdict"] = "unresolved"
        self.assertEqual(values, saved)


if __name__ == "__main__":
    unittest.main()
