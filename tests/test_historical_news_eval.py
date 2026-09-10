"""Deterministic scoring/admission regressions; no models or private labels."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "experiments/historical-news-tracing-20260908/summarize_test.py"
spec = importlib.util.spec_from_file_location("historical_news_scorer", SCORER)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def case(identifier="h01", text="Synthetic measurement record: 30 units."):
    material = {"version_id": "v1", "url": "https://fixture.invalid/record", "issuer": "Fixture",
        "content": text, "retrieved_at": "2026-01-01T00:00:00Z", "published_at": "2023-01-01T00:00:00Z",
        "available_at": "2023-01-01T00:00:00Z", "availability_basis": "Synthetic historical fixture."}
    return {"target": {"id": identifier, "text": "The measurement is authentic.",
                       "as_of": "2023-12-31T23:59:59Z", "source_version_id": "v1"},
            "materials": [material], "initial_version_ids": ["v1"],
            "claim_made_at": "2023-01-01T00:00:00Z", "variant": {"kind": "original", "pair_id": identifier}}


def call(stage="verify", success=True, usage=None):
    return {"stage": stage, "success": success, "status": "completed" if success else "failed",
            "usage": {"input_tokens": 10, "output_tokens": 2, "cached_input_tokens": 4,
                      "reasoning_output_tokens": 1} if usage is None and success else usage}


def result(item, arm="news_tracing", verdict="unresolved"):
    basis = [] if verdict == "unresolved" else [{"version_id": "v1", "quote": item["materials"][0]["content"]}]
    final = {"verdict": verdict, "basis": basis, "rationale": "Synthetic evidence assessment."}
    row = {"id": item["target"]["id"], "condition": arm, "fact_status": verdict,
           "errors": [], "timer_seconds": 1, "utc_elapsed_seconds": 1}
    if arm == "direct":
        row.update(raw_response=final, calls=[call("direct")])
        return row
    final.update(round=1, gaps=[], resolutions=[])
    trace = {"target": {**item["target"], "id": item["target"]["id"] + ":c1"},
        "fact_status": verdict, "errors": [], "verification_history": [final], "analysis_history": [],
        "operations": [], "gaps": [], "execution": {"provider_requests": []},
        "provenance_status": "original_material_located"}
    claim = {"text": item["target"]["text"], "fact_status": verdict, "provenance_status": "unresolved",
             "trace": trace, "errors": []}
    news_item = {"id": item["target"]["id"], "status": "completed", "claims": [claim], "errors": [],
                 "analysis": {"report": {"errors": []}}}
    row.update(report=trace, calls=[call("synthesis"), call("verify")],
        news_report={"results": [news_item], "summary": {"news_items": 1, "claims": 1, "completed": 1, "partial": 0, "failed": 0}})
    return row


def label(variant="original", role="authenticity"):
    return {"variant": variant, "role": role, "event_family": "synthetic-family",
            "cutoff_expected": "unresolved" if role == "authenticity" else "supported",
            "future_expected": "contradicted" if role == "authenticity" else "supported"}


class HistoricalNewsScoringTests(unittest.TestCase):
    def test_optional_research_failure_invalidates_primary_but_preserves_formal_diagnostic(self):
        item = case(); run = result(item)
        error = {"stage": "source_verify", "type": "InvalidReference", "message": "PRIVATE_CANARY"}
        run["errors"] = [error]
        news = run["news_report"]["results"][0]
        news.update(status="partial", errors=[error])
        news["analysis"]["report"]["errors"] = [error]
        run["news_report"]["summary"].update(completed=0, partial=1)
        score = scorer.assess_run(run, item)
        row = scorer.label_score(run, score, label())
        self.assertTrue(row["formal_pipeline_success"])
        self.assertTrue(row["formal_evidence_valid"])
        self.assertFalse(row["pipeline_success"])
        self.assertFalse(row["valid"])
        self.assertFalse(row["cutoff_match"])
        self.assertFalse(row["abstained"])
        self.assertEqual(1, row["error_count"])
        self.assertNotIn("PRIVATE_CANARY", json.dumps(row))
        self.assertNotIn("rationale", json.dumps(row))
        self.assertEqual("unresolved", row["displayed_provenance_status"])

    def test_final_failure_does_not_count_prior_unresolved_verdict_as_abstention(self):
        item = case(); run = result(item)
        run["calls"].append(call("verify", success=False))
        error = {"stage": "verify", "type": "Timeout"}
        run["errors"] = [error]
        run["report"]["errors"] = [error]
        run["news_report"]["results"][0]["claims"][0]["errors"] = [error]
        row = scorer.label_score(run, scorer.assess_run(run, item), label())
        self.assertFalse(row["formal_pipeline_success"])
        self.assertFalse(row["abstained"])
        self.assertEqual(3, row["usage"]["attempts"])
        self.assertEqual(24, row["usage"]["known_total_tokens"])
        self.assertIsNone(row["usage"]["total_tokens"])
        self.assertEqual(2, row["usage"]["successful_calls"])

    def test_failures_before_report_or_after_research_remain_failed_rows(self):
        item = case()
        early = {"id": "h01", "condition": "news_tracing", "fact_status": "execution_failed", "calls": [],
                 "errors": [{"type": "TransportInitializationFailure"}], "timer_seconds": 0, "utc_elapsed_seconds": 0}
        late = result(item)
        late["report"] = None
        late["calls"] = [call("synthesis")]
        news = late["news_report"]["results"][0]
        news["claims"][0].update(trace=None, errors=[{"type": "BudgetExhausted"}])
        news.update(status="failed", errors=[{"type": "BudgetExhausted"}])
        late["errors"] = news["errors"]
        for run in (early, late):
            row = scorer.label_score(run, scorer.assess_run(run, item), label())
            self.assertFalse(row["pipeline_success"])
            self.assertFalse(row["formal_pipeline_success"])
            self.assertFalse(row["abstained"])
            self.assertFalse(row["cutoff_match"])
            self.assertEqual(len(run["calls"]), row["logical_calls"])

    def test_malformed_direct_verdict_and_empty_or_inexact_settled_basis_fail_safely(self):
        for broken in ([], {}, None):
            with self.subTest(broken=broken):
                item = case(); run = result(item, "direct")
                run["raw_response"]["verdict"] = broken
                self.assertFalse(scorer.assess_run(run, item)["valid"])
        item = case(); run = result(item, "direct", "supported")
        for basis in ([], [{"version_id": "v1", "quote": "An invented quote"}],
                      [{"version_id": "v1", "quote": item["materials"][0]["content"], "start": True, "end": 37}]):
            run["raw_response"]["basis"] = basis
            self.assertFalse(scorer.assess_run(run, item)["valid"])

    def test_research_prefix_must_match_canonical_version_and_historical_target(self):
        item = case(text="A" * 17000)
        second = {**item["materials"][0], "version_id": "v2", "content": "B" * 17000}
        item["materials"].append(second)  # Same URL, different canonical version.
        evidence = {"url": second["url"], "title": second["issuer"], "content": second["content"][:16000],
                    "context_excerpt": True, "retrieved_at": second["retrieved_at"], "published_at": second["published_at"]}
        packet = {"historical_target": deepcopy(item["target"]), "request": "Synthetic research request.",
                  "fetched_evidence": [evidence], "collection_errors": [], "evidence_scope": "Synthetic fixture"}
        accepted = scorer.audit_exposure(packet, item, "source_trace")
        self.assertEqual(["v2"], accepted["research_excerpts"][0]["matching_version_ids"])
        for mutation in ("future", "date", "duplicate", "target", "gold", "empty", "old-version"):
            changed = deepcopy(packet)
            if mutation == "future": changed["fetched_evidence"][0]["content"] = "FUTURE_GOLD_CANARY"
            elif mutation == "date": changed["fetched_evidence"][0]["published_at"] = "2025-01-01T00:00:00Z"
            elif mutation == "duplicate": changed["fetched_evidence"].append(deepcopy(evidence))
            elif mutation == "target": changed["historical_target"]["as_of"] = "2025-01-01T00:00:00Z"
            elif mutation == "empty": changed["fetched_evidence"] = []
            elif mutation == "old-version": changed["fetched_evidence"][0]["content"] = "A" * 16000
            else: changed["future_expected"] = "contradicted"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                scorer.audit_exposure(changed, item, "source_trace")

    def test_direct_full_pool_and_formal_catalog_preview_are_exact(self):
        item = case()
        packet = {"historical_target": item["target"], "target": item["target"], "materials": item["materials"]}
        self.assertEqual(["v1"], scorer.audit_exposure(packet, item, "direct")["full_material_ids"])
        changed = deepcopy(packet); changed["materials"] = []
        with self.assertRaises(ValueError): scorer.audit_exposure(changed, item, "direct")
        changed = deepcopy(packet)
        changed["extra_source"] = {"url": "https://future.invalid/source", "content": "UNADMITTED_FUTURE_SOURCE_CANARY"}
        with self.assertRaises(ValueError): scorer.audit_exposure(changed, item, "direct")
        changed = {"historical_target": item["target"], "target": item["target"], "context": {"extra_source": changed["extra_source"]}}
        with self.assertRaises(ValueError): scorer.audit_exposure(changed, item, "verify")
        material = item["materials"][0]
        catalog = {k: material[k] for k in ("version_id", "url", "issuer", "published_at", "available_at")}
        catalog["preview"] = material["content"][:800]
        packet = {"historical_target": item["target"], "target": {**item["target"], "id": "h01:c1"}, "catalog": [catalog], "tasks": []}
        self.assertEqual(["v1"], scorer.audit_exposure(packet, item, "select")["catalog_preview_ids"])
        packet["catalog"][0]["preview"] += " later result"
        with self.assertRaises(ValueError): scorer.audit_exposure(packet, item, "select")

    def test_all_research_and_formal_calls_count_and_invalid_usage_remains_unknown(self):
        calls = [call("synthesis") for _ in range(23)] + [call("verify", success=False)]
        stats = scorer.token_stats(calls)
        self.assertEqual(24, stats["attempts"])
        self.assertEqual(23, stats["known_usage_calls"])
        self.assertEqual(276, stats["known_total_tokens"])
        self.assertIsNone(stats["total_tokens"])
        for usage in ({"input_tokens": True, "output_tokens": 1}, {"input_tokens": -1, "output_tokens": 2},
                      {"input_tokens": 10, "output_tokens": 2, "total_tokens": 99}):
            self.assertIsNone(scorer.token_stats([call(usage=usage)])["total_tokens"])
        stats = scorer.token_stats([call(usage={"input_tokens": 10, "output_tokens": 2,
                                                "cached_input_tokens": 11, "reasoning_output_tokens": 3})])
        self.assertEqual(12, stats["total_tokens"])
        self.assertIsNone(stats["cached_input_tokens"])
        self.assertIsNone(stats["reasoning_output_tokens"])

    def test_sixteen_row_denominator_preserves_failed_sibling_and_variant_partition(self):
        rows = []
        for variant in scorer.VARIANTS:
            for number in range(4):
                item = case(f"{variant}-{number}")
                role = "authenticity" if number < 2 else "attribution_control"
                for arm in scorer.CONDITIONS:
                    run = result(item, arm, "unresolved" if role == "authenticity" else "supported")
                    if variant == "blinded" and number == 0:
                        run["calls"][-1].update(success=False, status="failed", usage=None)
                    rows.append(scorer.label_score(run, scorer.assess_run(run, item), label(variant, role)))
        aggregate = scorer.aggregate(rows)
        for arm in scorer.CONDITIONS:
            self.assertEqual(4, aggregate["original"][arm]["cutoff_matches"])
            self.assertEqual(4, aggregate["blinded"][arm]["cases"])
            self.assertEqual(3, aggregate["blinded"][arm]["cutoff_matches"])
            self.assertEqual(1, aggregate["blinded"][arm]["authenticity_abstentions"])
            self.assertEqual(1, aggregate["blinded"][arm]["authenticity_failed_or_invalid"])
        with self.assertRaises(ValueError): scorer.aggregate(rows[:-1])

    def test_failed_request_audit_prevents_any_gold_read(self):
        item = case()
        packet = {"historical_target": item["target"], "fetched_evidence": [{"content": "UNADMITTED_FUTURE_EVIDENCE"}]}
        def failing_audit(_):
            scorer.audit_exposure(packet, item, "synthesis")
        with patch.object(scorer, "verify_batch", side_effect=failing_audit), patch.object(scorer, "read") as gold_reader:
            with self.assertRaises(ValueError):
                scorer.summarize(Path("never-opened"), Path("PRIVATE_GOLD_MUST_NOT_BE_PARSED"))
            gold_reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
