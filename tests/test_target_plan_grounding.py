"""Focused deterministic grounding regressions; no model API use."""
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from target_plan import dimension_evidence_is_grounded


CORE_DIMENSIONS = ("actor_subject", "predicate_object", "scope_location")
VIRGIN_TARGET = (
    "Virgin Galactic will commence commercial service during the second "
    "quarter of 2023."
)
VIRGIN_HEADING = (
    "Virgin Galactic 2023 Form 10-K | SEC filing dated February 27, 2024"
)
VIRGIN_BODY = (
    "In June 2023, we completed our first commercial spaceflight, 'Galactic "
    "01,' which marked the start of our commercial service."
)
BOEING_TARGET = (
    "Boeing will complete the Starliner crewed flight test by December 31, "
    "2023."
)
BOEING_CONTEXT = (
    "Boeing Q3 2024 Form 10-Q | SEC filing dated October 23, 2024\n"
    "National Aeronautics and Space Administration has contracted us to "
    "design and build the CST-100 Starliner spacecraft to transport crews "
    "to the International Space Station (ISS). During 2023, we increased "
    "the reach-forward loss by $288 primarily as a result of delaying the "
    "Crewed Flight Test (CFT) following notification by a parachute supplier "
    "of an issue identified through testing.\nThe CFT launched on June 5, "
    "2024, and docked with the ISS."
)


class TargetPlanGroundingTests(unittest.TestCase):
    def core_results(self, probe, basis):
        return {dimension: dimension_evidence_is_grounded(
            dimension, probe, basis, "supported")
            for dimension in CORE_DIMENSIONS}

    def assert_not_fully_grounded(self, probe, basis):
        results = self.core_results(probe, basis)
        self.assertFalse(all(results.values()), (probe, basis, results))

    def test_contiguous_virgin_excerpt_grounds_all_dimensions(self):
        basis = VIRGIN_HEADING + "\n" + VIRGIN_BODY

        for dimension in (*CORE_DIMENSIONS, "time"):
            with self.subTest(dimension=dimension):
                self.assertTrue(dimension_evidence_is_grounded(
                    dimension, VIRGIN_TARGET, basis, "supported"))

    def test_split_virgin_heading_and_body_do_not_ground_core(self):
        # Neither partial quote may become conclusive alone. The verifier may
        # combine them only when they are truly adjacent and persist the full
        # synthesized span in its audit basis.
        self.assertEqual({dimension: False for dimension in CORE_DIMENSIONS},
                         self.core_results(VIRGIN_TARGET, VIRGIN_HEADING))
        self.assertEqual({dimension: False for dimension in CORE_DIMENSIONS},
                         self.core_results(VIRGIN_TARGET, VIRGIN_BODY))

    def test_september_does_not_ground_second_quarter(self):
        basis = VIRGIN_HEADING + "\n" + (
            "In September 2023, we completed our first commercial spaceflight, "
            "'Galactic 01,' which marked the start of our commercial service."
        )

        self.assertTrue(dimension_evidence_is_grounded(
            "predicate_object", VIRGIN_TARGET, basis, "supported"))
        self.assertFalse(dimension_evidence_is_grounded(
            "time", VIRGIN_TARGET, basis, "supported"))

    def test_end_is_not_equivalent_to_commence(self):
        basis = VIRGIN_HEADING + "\n" + (
            "In June 2023, we completed our first commercial spaceflight, "
            "'Galactic 01,' which marked the end of our commercial service."
        )
        results = self.core_results(VIRGIN_TARGET, basis)
        self.assertEqual({dimension: False for dimension in CORE_DIMENSIONS},
                         results)

    def test_closed_start_equivalence_includes_morphology(self):
        forms = (
            "commence", "commenced", "commences", "commencing",
            "begin", "began", "begun", "begins", "beginning",
            "start", "started", "starts", "starting",
        )
        for form in forms:
            with self.subTest(form=form):
                self.assertTrue(dimension_evidence_is_grounded(
                    "actor_subject",
                    f"Virgin Galactic {form} commercial service.",
                    "Virgin Galactic started commercial service.",
                    "supported",
                ))

    def test_wrong_actor_object_and_predicate_remain_rejected(self):
        for probe, basis in (
            ("Officials denied the report.", "Officials confirmed the report."),
            ("Alice bought Widget.", "Bob bought Widget."),
            ("Alice bought Widget.", "Alice bought Gadget."),
            ("Alice will buy Widget.", "Alice sold Widget."),
            ("Alice produced Widget.",
             "Alice produced Gadget, Bob delivered Widget."),
            ("Alice produced Widget.",
             "Alice produced 12,000, Bob delivered Widget."),
            ("Alice produced Widget.",
             "Alice produced Gadget. Bob delivered Widget."),
            ("Alice produced Widget.",
             "Alice produced Gadget Bob delivered Widget."),
            ("Alice produced Widget.",
             "Alice produced Gadget — Bob delivered Widget."),
            ("Alice produced Widget.",
             "Alice produced Gadget — Widget appeared later."),
            ("Alice produced Widget.",
             "Alice produced Gadget -- Widget appeared later."),
            ("Alice produced Widget.",
             "Alice produced Gadget because Widget failed."),
        ):
            self.assert_not_fully_grounded(probe, basis)

    def test_quoted_brand_does_not_supply_header_actor(self):
        basis = (
            "Acme 2023 results | SEC exhibit\n"
            "Beta's 'Acme One' flight marked the start of commercial service "
            "in June 2023."
        )
        self.assert_not_fully_grounded(
            "Acme will commence commercial service during 2023.", basis)

    def test_company_alias_must_be_the_independent_header_subject(self):
        target = "Lucid will manufacture 8,428 vehicles during 2023."
        for subject in (
                "Beta Company", "Rival Company", "The Other Company",
                "Bob's company"):
            with self.subTest(subject=subject):
                basis = (
                    "Lucid results | SEC exhibit\n"
                    f"{subject} produced 8,428 vehicles during 2023."
                )
                self.assert_not_fully_grounded(target, basis)
        valid = (
            "Lucid results | SEC exhibit\n"
            "On a full-year basis, the Company produced 8,428 vehicles."
        )
        self.assertTrue(all(self.core_results(target, valid).values()))

    def test_report_header_must_name_issuer_at_the_start(self):
        target = "Acme will commence commercial service during 2023."
        body = (
            "In June 2023, we completed our first commercial spaceflight, "
            "'Beta One,' which marked the start of our commercial service."
        )
        headings = (
            "Beta's report on Acme 2023 results | SEC exhibit",
            "Results for Beta versus Acme | SEC filing",
            "Acme results by Beta | SEC exhibit",
        )
        for heading in headings:
            with self.subTest(heading=heading):
                self.assert_not_fully_grounded(
                    target, heading + "\n" + body)

    def test_irregular_passive_does_not_reverse_actor_roles(self):
        for basis in (
                "Alice was brought by Bob after Friday.",
                "Alice was brought over by Bob after Friday.",
                "Alice was brought back by Bob after Friday.",
                "Alice was brought to school by Bob after Friday."):
            with self.subTest(basis=basis):
                self.assert_not_fully_grounded(
                    "Alice brought Bob before Friday.", basis)

        for target, basis in (
                ("Alice brought Bob.", "Alice was brought home to Bob."),
                ("Acme sold Beta.", "Acme was sold to Beta."),
                ("Acme built Beta.", "Acme was built for Beta."),
                ("Acme bought Beta.", "Acme was bought from Beta.")):
            with self.subTest(target=target, basis=basis):
                self.assert_not_fully_grounded(target, basis)

    def test_irregular_active_event_cannot_be_stitched_across_sentences(self):
        self.assert_not_fully_grounded(
            "Alice hit Widget.",
            "Alice filed a notice. Bob hit Widget.")
        self.assertTrue(all(self.core_results(
            "Alice hit Widget.", "Alice hit Widget.").values()))
        self.assert_not_fully_grounded(
            "Alice swam Channel.",
            "Alice filed 12,000, Bob swam Channel.")

    def test_comparison_operator_cannot_come_from_a_second_event(self):
        target = "Lucid will manufacture more than 10,000 vehicles in 2023."
        basis = (
            "Lucid results | SEC exhibit\n"
            "The Company produced 10,000 vehicles, Bob delivered more than "
            "10,000 packages."
        )
        self.assertFalse(dimension_evidence_is_grounded(
            "comparison_baseline", target, basis, "supported"))

        actual_plus_forecast = (
            "Lucid results | SEC exhibit\n"
            "The Company produced 8,428 vehicles compared with a "
            "12,000-vehicle forecast."
        )
        self.assertFalse(dimension_evidence_is_grounded(
            "comparison_baseline", target, actual_plus_forecast,
            "supported"))

    def test_non_entailing_comparison_bounds_remain_unresolved(self):
        target = "Lucid will manufacture more than 10,000 vehicles in 2023."
        for metric in (
                "fewer than 12,000", "at most 12,000", "up to 12,000",
                "more than 8,000", "at least 10,000",
                "approximately 10,000"):
            basis = (
                "Lucid results | SEC exhibit\n"
                f"The Company produced {metric} vehicles in 2023."
            )
            for verdict in ("supported", "contradicted"):
                with self.subTest(metric=metric, verdict=verdict):
                    self.assertFalse(dimension_evidence_is_grounded(
                        "comparison_baseline", target, basis, verdict))

    def test_nominalized_second_event_cannot_supply_metric(self):
        target = "Alice produced more than 10,000 Widget during 2023."
        tails = (
            "following delivery of 12,000 Gadget by Bob during 2023",
            "after delivery of 12,000 Gadget by Bob during 2023",
            "subsequent to delivery of 12,000 Gadget by Bob during 2023",
            "before the delivery of 12,000 Gadget by Bob during 2023",
        )
        for tail in tails:
            basis = f"Alice produced Widget {tail}."
            for dimension in (
                    "quantity_unit_denominator", "comparison_baseline"):
                for verdict in ("supported", "contradicted"):
                    with self.subTest(
                            tail=tail, dimension=dimension, verdict=verdict):
                        self.assertFalse(dimension_evidence_is_grounded(
                            dimension, target, basis, verdict))

    def test_object_measurement_cannot_masquerade_as_object_count(self):
        cases = (
            ("Lucid will manufacture more than 10,000 vehicles during 2023.",
             "Lucid results | SEC exhibit\n"
             "The Company produced 12,000-pound vehicles during 2023."),
            ("Acme will manufacture more than 100 batteries during 2023.",
             "Acme results | SEC exhibit\n"
             "The Company produced 500 watt batteries during 2023."),
        )
        for target, basis in cases:
            for dimension in (
                    "quantity_unit_denominator", "comparison_baseline"):
                with self.subTest(target=target, dimension=dimension):
                    self.assertFalse(dimension_evidence_is_grounded(
                        dimension, target, basis, "supported"))

    def test_qualifiers_cannot_come_from_a_second_event(self):
        target = "Alice produced Widget during 2023."
        basis = "Alice produced Widget, Bob delivered Gadget during 2023."
        self.assertFalse(dimension_evidence_is_grounded(
            "time", target, basis, "supported"))
        self.assertFalse(dimension_evidence_is_grounded(
            "time", target,
            "Bob swam in 2023, Alice produced Widget.", "supported"))
        self.assertTrue(dimension_evidence_is_grounded(
            "time", target,
            "During 2023, Alice produced Widget.", "supported"))

        negated_other_event = (
            "Alice produced Widget, Bob did not deliver Gadget."
        )
        self.assertFalse(dimension_evidence_is_grounded(
            "predicate_object", "Alice produced Widget.",
            negated_other_event, "contradicted"))

        quantity_target = (
            "Alice produced more than 10,000 Widget during 2023."
        )
        subordinate_templates = (
            "after Bob delivered", "following Bob delivering",
            "once Bob delivered", "upon Bob delivering",
            "where Bob delivered", "whenever Bob delivered",
            "prior to Bob delivering", "subsequent to Bob delivering",
        )
        for linker in subordinate_templates:
            subordinate = (
                f"Alice produced Widget {linker} 12,000 Gadget during 2023."
            )
            for dimension in (
                    "time", "quantity_unit_denominator",
                    "comparison_baseline"):
                with self.subTest(linker=linker, dimension=dimension):
                    self.assertFalse(dimension_evidence_is_grounded(
                        dimension, quantity_target, subordinate, "supported"))

    def test_adjunct_negation_does_not_negate_target_predicate(self):
        target = "Alice produced Widget."
        for basis in (
                "Alice produced Widget without defects.",
                "Alice produced Widget with no help from Bob.",
                "Alice produced Widget without Bob delivering Gadget."):
            with self.subTest(basis=basis):
                self.assertTrue(dimension_evidence_is_grounded(
                    "predicate_object", target, basis, "supported"))
                self.assertFalse(dimension_evidence_is_grounded(
                    "predicate_object", target, basis, "contradicted"))
        for basis in (
                "Alice did not produce Widget.",
                "Alice never produced Widget.",
                "Alice produced no Widget."):
            with self.subTest(basis=basis):
                self.assertFalse(dimension_evidence_is_grounded(
                    "predicate_object", target, basis, "supported"))
                self.assertTrue(dimension_evidence_is_grounded(
                    "predicate_object", target, basis, "contradicted"))

    def test_header_report_year_cannot_override_body_event_year(self):
        target = "Lucid will manufacture 8,428 vehicles during 2023."
        basis = (
            "Lucid Q4 2023 results | SEC exhibit filed February 21, 2024\n"
            "On a full-year basis, the Company produced 8,428 vehicles "
            "during 2022."
        )
        self.assertFalse(dimension_evidence_is_grounded(
            "time", target, basis, "supported"))
        self.assertTrue(dimension_evidence_is_grounded(
            "time", target, basis, "contradicted"))

    def test_role_order_and_conjunction_scope_remain_rejected(self):
        for probe, basis in (
            ("Alice defeated Bob.", "Bob defeated Alice."),
            (
                "The agency alleged that Alice failed and Bob cheated.",
                "The agency alleged that Alice failed. Bob cheated.",
            ),
            ("苹果公司在北京收购微软。", "苹果公司在上海发布新品。"),
        ):
            self.assert_not_fully_grounded(probe, basis)

    def test_cjk_roles_cannot_be_stitched_across_events(self):
        target = "苹果公司收购微软。"
        for basis in (
                "苹果公司发布新品。谷歌收购微软。",
                "苹果公司发布新品，谷歌收购微软。",
                "苹果公司发布新品而谷歌收购微软。",
                "苹果公司发布新品但谷歌收购微软。",
                "苹果公司发布新品然后谷歌收购微软。",
                "苹果公司发布新品因为谷歌收购微软。"):
            with self.subTest(basis=basis):
                self.assert_not_fully_grounded(target, basis)
        self.assertTrue(all(self.core_results(target, "苹果公司收购微软。")
                            .values()))

    def test_role_reversal_cannot_masquerade_as_a_contradiction(self):
        for dimension in CORE_DIMENSIONS:
            with self.subTest(dimension=dimension):
                self.assertFalse(dimension_evidence_is_grounded(
                    dimension, "Alice defeated Bob.",
                    "Bob defeated Alice.", "contradicted"))

    def test_contradiction_requires_ordered_event_identity(self):
        header = "Boeing Q3 2024 Form 10-Q | SEC filing dated October 23, 2024"
        acronym_only = "The CFT launched on June 5, 2024, and docked with the ISS."

        self.assertFalse(dimension_evidence_is_grounded(
            "time", BOEING_TARGET, header, "contradicted"))
        self.assertFalse(dimension_evidence_is_grounded(
            "time", BOEING_TARGET, acronym_only, "contradicted"))
        self.assertFalse(dimension_evidence_is_grounded(
            "time", BOEING_TARGET, BOEING_CONTEXT, "contradicted"))

    def test_simple_object_identity_still_allows_a_grounded_contradiction(self):
        self.assertTrue(dimension_evidence_is_grounded(
            "time", "The bridge reopened before Friday.",
            "The bridge remains closed until Friday.", "contradicted"))

    def test_closed_opposition_cannot_cross_events(self):
        target = "The bridge reopened before Friday."
        basis = "The bridge remained stable, Bob closed Store after Friday."
        for dimension in (*CORE_DIMENSIONS, "time"):
            with self.subTest(dimension=dimension):
                self.assertFalse(dimension_evidence_is_grounded(
                    dimension, target, basis, "contradicted"))


if __name__ == "__main__":
    unittest.main()
