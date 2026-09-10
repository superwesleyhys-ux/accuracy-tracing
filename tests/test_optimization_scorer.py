"""Optimization scoring checks using synthetic source text only."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from newsverify.news_tracing_runner import _research_advice
from newsverify.provenance import MaterialVersion
from tests.test_historical_news_eval import case, call, result, label


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "optimization_scorer", ROOT / "experiments/harness-optimization-20260909/summarize_round.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
driver_spec = importlib.util.spec_from_file_location(
    "optimization_driver", ROOT / "experiments/harness-optimization-20260909/run_round.py")
driver = importlib.util.module_from_spec(driver_spec)
driver_spec.loader.exec_module(driver)


class OptimizationScorerTests(unittest.TestCase):
    def test_all_snapshot_versions_offsets_and_cutoff_are_bound(self):
        item = case(text="A" * 17000)
        item["materials"].append({**item["materials"][0], "version_id": "v2", "content": "B" * 17000})
        packet = {"historical_target": deepcopy(item["target"]), "request": "{}",
                  "fetched_evidence": scorer.expected_research_excerpts(item),
                  "collection_errors": [], "evidence_scope": "Synthetic fixture"}
        admitted = scorer.audit_exposure(packet, item, "source_trace")
        self.assertEqual([["v1"], ["v2"]], [e["matching_version_ids"] for e in admitted["research_excerpts"]])
        for mutation in ("content", "date", "missing_version", "duplicate", "offset", "offset_type", "target", "extra"):
            changed = deepcopy(packet)
            if mutation == "content": changed["fetched_evidence"][0]["content"] = "UNSUPPLIED_CANARY"
            elif mutation == "date": changed["fetched_evidence"][0]["published_at"] = "2025-01-01T00:00:00Z"
            elif mutation == "missing_version": changed["fetched_evidence"].pop()
            elif mutation == "duplicate": changed["fetched_evidence"].append(changed["fetched_evidence"][0])
            elif mutation == "offset": changed["fetched_evidence"][0]["content_start"] = 1
            elif mutation == "offset_type": changed["fetched_evidence"][0]["content_start"] = False
            elif mutation == "target": changed["historical_target"]["as_of"] = "2025-01-01T00:00:00Z"
            else: changed["extra_source"] = {"url": "https://unknown.invalid", "content": "UNSUPPLIED_CANARY"}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                scorer.audit_exposure(changed, item, "source_trace")

    def test_advice_is_bound_to_retained_proposals_and_cannot_supply_source_text(self):
        item = case()
        advice = _research_advice({"information_gaps": ["Inspect the original measurement record."],
                                   "sources": [{"url": item["materials"][0]["url"]}]},
                                  [MaterialVersion(**m) for m in item["materials"]])
        packet = {"historical_target": item["target"], "target": item["target"],
                  "context": {"materials": item["materials"]}, "research_advice": advice}
        admitted = scorer.audit_exposure(packet, item, "verify", advice)
        self.assertTrue(admitted["untrusted_research_advice_present"])
        self.assertEqual(["v1"], admitted["full_material_ids"])
        for mutate in (lambda p: p["research_advice"].update(trust="accepted_evidence"),
                       lambda p: p["research_advice"]["candidate_version_ids"].append("unknown-version"),
                       lambda p: p["research_advice"].update(research_had_errors=0),
                       lambda p: p["context"].update(extra_source={"url": "https://unknown.invalid", "content": "UNSUPPLIED_CANARY"}),
                       lambda p: p["research_advice"].update(information_gaps=["Altered model proposal."])):
            changed = deepcopy(packet); mutate(changed)
            with self.assertRaises(ValueError):
                scorer.audit_exposure(changed, item, "verify", advice)

    def test_decomposition_accepts_current_material_once_without_requiring_select(self):
        item = case()
        advice = _research_advice({}, [MaterialVersion(**m) for m in item["materials"]])
        packet = {"historical_target": item["target"], "target": item["target"],
                  "material": item["materials"][0], "context": {"materials": []}, "research_advice": advice}
        self.assertEqual(["v1"], scorer.audit_exposure(packet, item, "decompose", advice)["full_material_ids"])

    def test_research_failure_retains_formal_diagnostic_without_abstention_credit(self):
        item = case(); run = result(item)
        error = {"stage": "source_trace", "type": "TunnelError", "message": "PRIVATE_CANARY"}
        run["errors"] = [error]
        news = run["news_report"]["results"][0]
        news.update(status="partial", errors=[error])
        news["analysis"]["report"]["errors"] = [error]
        run["news_report"]["summary"].update(completed=0, partial=1)
        row = scorer.label_score(run, scorer.assess_run(run, item), label())
        self.assertTrue(row["formal_cutoff_match"])
        self.assertTrue(row["formal_abstained"])
        self.assertFalse(row["cutoff_match"])
        self.assertFalse(row["abstained"])
        self.assertNotIn("PRIVATE_CANARY", json.dumps(row))

    def test_required_research_phases_cannot_be_silently_skipped(self):
        run = result(case())
        analysis = run["news_report"]["results"][0]["analysis"]["report"]
        analysis["phase_status"] = [{"stage": s, "status": "completed"}
                                    for s in ("deconstruct", "direct_response", "synthesis")]
        analysis["limits"] = {"research_mode": "full", "research_scope": scorer.expected_research_scope("full", None)}
        run["calls"] = [call(s) for s in ("deconstruct", "direct_response", "synthesis", "verify")]
        self.assertTrue(scorer.research_completion_valid(run))
        analysis["phase_status"].append({"stage": "causal_dig", "status": "skipped"})
        self.assertTrue(scorer.research_completion_valid(run))
        analysis["phase_status"][0]["status"] = "skipped"
        self.assertFalse(scorer.research_completion_valid(run))
        analysis["phase_status"][0]["status"] = "completed"
        run["calls"].pop(0)
        self.assertFalse(scorer.research_completion_valid(run))

    def test_claim_mode_requires_exact_scope_and_explicit_skips(self):
        item = case(); run = result(item)
        analysis = run["news_report"]["results"][0]["analysis"]["report"]
        analysis["limits"] = {"research_mode": "claim", "research_scope": scorer.expected_research_scope("claim", item["target"]["text"])}
        analysis["phase_status"] = ([{"stage": stage, "status": "completed"} for stage in ("deconstruct", "search_plan", "synthesis")]
            + [{"stage": stage, "status": "skipped", "reason": "Declared claim-only scope"} for stage in scorer.CLAIM_OMITTED_STAGES])
        run["calls"] = [call(stage) for stage in ("deconstruct", "search_plan", "synthesis", "verify")]
        self.assertTrue(scorer.research_completion_valid(run, "claim", item["target"]["text"]))
        self.assertFalse(scorer.research_completion_valid(run, "full", item["target"]["text"]))
        for mutation in ("missing_skip", "failed_skip", "omitted_call", "changed_claim", "failed_retained", "missing_plan"):
            changed = deepcopy(run)
            report = changed["news_report"]["results"][0]["analysis"]["report"]
            if mutation == "missing_skip": report["phase_status"].pop()
            elif mutation == "failed_skip": report["phase_status"][-1]["status"] = "failed"
            elif mutation == "omitted_call": changed["calls"].append(call("direct_response"))
            elif mutation == "changed_claim": report["limits"]["research_scope"]["fixed_claim"] = "Different target"
            elif mutation == "missing_plan": changed["calls"] = [c for c in changed["calls"] if c["stage"] != "search_plan"]
            else: report["phase_status"][0]["status"] = "failed"
            with self.subTest(mutation=mutation):
                self.assertFalse(scorer.research_completion_valid(changed, "claim", item["target"]["text"]))

    def test_synthesis_packet_discloses_omitted_stages_and_exact_claim(self):
        item = case()
        scope = scorer.expected_research_scope("claim", item["target"]["text"])
        packet = {"historical_target": item["target"], "request": json.dumps({"research_scope": scope}),
                  "fetched_evidence": scorer.expected_research_excerpts(item), "collection_errors": [], "evidence_scope": "Synthetic fixture"}
        scorer.audit_exposure(packet, item, "synthesis", research_mode="claim")
        for mutate in (lambda s: s.update(fixed_claim="Changed claim"),
                       lambda s: s.update(intentionally_omitted_stages=[]),
                       lambda s: s.update(omitted_stages_are_not_failed_checks=1),
                       lambda s: s.update(mode="full")):
            changed = deepcopy(packet); changed_scope = deepcopy(scope); mutate(changed_scope)
            changed["request"] = json.dumps({"research_scope": changed_scope})
            with self.assertRaises(ValueError):
                scorer.audit_exposure(changed, item, "synthesis", research_mode="claim")
        omitted = {"historical_target": item["target"], "request": "{}", "fetched_evidence": scorer.expected_research_excerpts(item)}
        with self.assertRaises(ValueError):
            scorer.audit_exposure(omitted, item, "direct_response", research_mode="claim")

    def test_v2_plan_explicitly_binds_mode_to_the_unchanged_claim_payload(self):
        item = case()
        item["config"] = {"max_documents": 6}
        plan = {"schema_version": 2, "round_id": "round-2", "phase": "development", "development_round": 2,
                "case_ids": ["h01", "h02", "h05", "h06"], "conditions": list(scorer.CONDITIONS),
                "max_development_rounds": 3, "research_mode": "claim"}
        driver.validate_plan(plan)
        payload = driver.news_payload(item, plan["research_mode"])
        self.assertEqual(payload["config"]["research_mode"], "claim")
        self.assertEqual(payload["config"]["max_origin_calls"], 10)
        self.assertEqual(payload["news"][0]["claims"], [item["target"]["text"]])
        self.assertEqual(payload["news"][0]["materials"], item["materials"])
        for mutate in (lambda p: p.update(schema_version=1), lambda p: p.pop("research_mode"),
                       lambda p: p.update(research_mode="undeclared")):
            changed = deepcopy(plan); mutate(changed)
            with self.assertRaises(ValueError): driver.validate_plan(changed)

    def test_development_and_confirmation_denominators_preserve_failed_siblings(self):
        rows = []
        for variant in ("original", "blinded"):
            for index in range(4):
                item = case(f"{variant}-{index}")
                role = "authenticity" if index < 2 else "attribution_control"
                for arm in scorer.CONDITIONS:
                    run = result(item, arm, "unresolved" if role == "authenticity" else "supported")
                    if index == 0:
                        run["calls"][-1].update(success=False, status="failed", usage=None)
                    rows.append(scorer.label_score(run, scorer.assess_run(run, item), label(variant, role)))
        dev = scorer.aggregate([row for row in rows if row["variant"] == "original"])
        self.assertEqual(set(dev), {"original"})
        full = scorer.aggregate(rows)
        for variant in full:
            for arm in scorer.CONDITIONS:
                self.assertEqual(full[variant][arm]["cases"], 4)
                self.assertEqual(full[variant][arm]["cutoff_matches"], 3)
                self.assertEqual(full[variant][arm]["authenticity_failed_or_invalid"], 1)
                self.assertEqual(full[variant][arm]["authenticity_abstentions"], 1)
        with self.assertRaises(ValueError): scorer.aggregate(rows[:-1])

    def test_failed_usage_is_unknown_and_never_zero_cost(self):
        stats = scorer.token_stats([call("synthesis"), call("verify", success=False)])
        self.assertEqual(stats["attempts"], 2)
        self.assertEqual(stats["known_total_tokens"], 12)
        self.assertIsNone(stats["total_tokens"])
        self.assertFalse(stats["usage_complete"])

    def test_failed_request_audit_prevents_gold_read(self):
        with patch.object(scorer, "verify_batch", side_effect=ValueError("Unadmitted packet")), patch.object(scorer, "read") as reader:
            with self.assertRaises(ValueError):
                scorer.summarize(Path("never-opened"), Path("PRIVATE_GOLD"))
            reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
