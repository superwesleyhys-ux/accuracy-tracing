"""Verification requests must supersede older resolution evidence."""

from dataclasses import replace
import unittest

from newsverify.provenance import (
    Analysis, Gap, MaterialVersion, ReplayTraceProvider, Resolution, Span, Target,
    TraceConfig, VerificationResult, run_provenance,
)


GAP = Gap("verification:measurement", "Check the measurement record.", "verification")
TARGET = Target("measurement", "The measured result was 30 units.",
                "2026-01-03T00:00:00Z", "notice")


def material(identifier):
    return MaterialVersion(identifier, "https://fixture.invalid/" + identifier,
                           identifier + ": the measured result was 30 units.",
                           "2026-01-03T00:00:00Z", available_at="2026-01-01T00:00:00Z",
                           availability_basis="Synthetic contract fixture.")


NOTICE, RECORD, UPDATE = (material(identifier) for identifier in ("notice", "record", "update"))


def resolution(source=RECORD):
    return Resolution(GAP.id, (Span(source.version_id, 0, len(source.content), source.content),),
                      "This exact measurement record answers the question.")


def supported(*, gaps=(), resolutions=()):
    return VerificationResult("supported", resolution().basis,
                              "The supplied record supports the measurement.", gaps, resolutions)


class GapReopeningTests(unittest.TestCase):
    def run_trace(self, *, revisit=False, refreshed_resolution=False, third_round=False,
                  final_resolution=False, same_response_resolution=False, cosmetic_revision=False):
        class Decomposer:
            def decompose(self, target, source, context):
                if source.version_id == "record":
                    refreshed = refreshed_resolution and "update" in context["analyses"]
                    evidence = resolution(UPDATE if refreshed else RECORD)
                    if cosmetic_revision and "update" in context["analyses"]:
                        evidence = replace(evidence, rationale="Reworded conclusion from the same evidence.")
                    return Analysis(resolutions=(evidence,))
                return Analysis(revisit_versions=("record",) if revisit and source == UPDATE else ())

        class Verifier:
            def verify(self, target, context):
                round_number = context["usage"]["rounds"]
                if round_number == 1:
                    return VerificationResult(gaps=(GAP,))
                if round_number == 2:
                    return supported(gaps=(replace(GAP, question="New doubt: check the measurement again."),),
                                     resolutions=(resolution(),) if same_response_resolution else ())
                return supported(resolutions=(resolution(),) if final_resolution else ())

        rounds = ((NOTICE,), (RECORD,), (UPDATE,)) if third_round else ((NOTICE,), (RECORD,))
        return run_provenance(TARGET, ReplayTraceProvider(rounds), Decomposer(), Verifier(),
                              TraceConfig(max_rounds=len(rounds)))

    def assert_open(self, report):
        self.assertEqual([], report["errors"])
        self.assertEqual("unresolved", report["fact_status"])
        self.assertIn(GAP.id, [gap["id"] for gap in report["gaps"]])
        self.assertNotIn(GAP.id, [item["gap_id"] for item in report["resolutions"]])
        # The superseded evidence is still present in the immutable audit.
        self.assertIn(GAP.id, [item["gap_id"] for entry in report["analysis_history"]
                              for item in entry["analysis"]["resolutions"]])

    def assert_resolved(self, report):
        self.assertEqual([], report["errors"])
        self.assertEqual("supported", report["fact_status"])
        self.assertNotIn(GAP.id, [gap["id"] for gap in report["gaps"]])
        self.assertIn(GAP.id, [item["gap_id"] for item in report["resolutions"]])

    def test_reopened_verification_gap_supersedes_decomposition_resolution(self):
        self.assert_open(self.run_trace())

    def test_unrelated_analysis_does_not_restore_superseded_resolution(self):
        self.assert_open(self.run_trace(third_round=True))

    def test_revisit_preserving_old_resolution_does_not_close_reopened_gap(self):
        report = self.run_trace(third_round=True, revisit=True)
        self.assertEqual(2, sum(entry["version_id"] == "record" for entry in report["analysis_history"]))
        self.assert_open(report)

    def test_later_reanalysis_with_new_evidence_can_resolve_reopened_gap(self):
        self.assert_resolved(self.run_trace(third_round=True, revisit=True, refreshed_resolution=True))

    def test_rewording_old_resolution_does_not_close_reopened_gap(self):
        self.assert_open(self.run_trace(third_round=True, revisit=True, cosmetic_revision=True))

    def test_later_verifier_can_explicitly_resolve_reopened_gap(self):
        self.assert_resolved(self.run_trace(third_round=True, final_resolution=True))

    def test_verifier_can_open_and_resolve_gap_in_same_response(self):
        self.assert_resolved(self.run_trace(same_response_resolution=True))


class ProvenanceGapBoundaryTests(unittest.TestCase):
    def run_collision(self, *, retirement=None, verifier_resolution=False, reserved_origin=False):
        gap_id = "origin:" + TARGET.id if reserved_origin else "source-link"
        provenance_gap = Gap(gap_id, "Find the producing source and citation path.")
        evidence = replace(resolution(), gap_id=gap_id)

        class Decomposer:
            def decompose(self, target, source, context):
                if source == NOTICE and "notice" not in context["analyses"]:
                    return Analysis(gaps=() if reserved_origin else (provenance_gap,))
                if source == RECORD and retirement == "resolve":
                    return Analysis(resolutions=(evidence,))
                return Analysis(revisit_versions=("notice",) if source == RECORD and retirement == "remove" else ())

        class Verifier:
            def verify(self, target, context):
                if context["usage"]["rounds"] == 1:
                    return VerificationResult()
                if verifier_resolution:
                    return supported(resolutions=(evidence,))
                return supported(gaps=(Gap(gap_id, "Reclassify the provenance question.", "verification"),))

        return run_provenance(TARGET, ReplayTraceProvider(((NOTICE,), (RECORD,))),
                              Decomposer(), Verifier(), TraceConfig(max_rounds=2))

    def assert_rejected_before_mutation(self, report):
        self.assertEqual("verifier_error", report["stop_reason"])
        self.assertEqual("unresolved", report["fact_status"])
        self.assertEqual("unresolved", report["provenance_status"])
        self.assertIn("provenance gap", report["errors"][0]["message"])
        self.assertEqual(1, len(report["verification_history"]))

    def test_verifier_cannot_reclassify_current_or_reserved_provenance_gap(self):
        for reserved in (False, True):
            with self.subTest(reserved_origin=reserved):
                self.assert_rejected_before_mutation(self.run_collision(reserved_origin=reserved))

    def test_verifier_cannot_reclassify_removed_or_resolved_provenance_gap(self):
        for retirement in ("remove", "resolve"):
            with self.subTest(retirement=retirement):
                self.assert_rejected_before_mutation(self.run_collision(retirement=retirement))

    def test_verifier_cannot_resolve_historical_provenance_gap(self):
        for retirement in ("remove", "resolve"):
            with self.subTest(retirement=retirement):
                self.assert_rejected_before_mutation(self.run_collision(
                    retirement=retirement, verifier_resolution=True))


if __name__ == "__main__":
    unittest.main()
