"""Regression coverage for live research-output shapes; no model or network."""
from copy import deepcopy
import json
import unittest

from newsverify.news_tracing.core import NewsTracingAgent
from newsverify.news_tracing.models import EventNode
from newsverify.news_tracing import prompts


class TimelineClient:
    def __init__(self, links):
        self.links = links

    async def query_json(self, system, user, *, web_search=False):
        return {"events": [{"title": "Galaxy crossing", "date": "未知",
                "description": "A proposed causal interpretation.",
                "significance": "重要", "sources": [], "source_count": 2,
                "causal_links": deepcopy(self.links)}]}


class ResearchModeClient:
    """All stages have relevant fixture data, so full mode really executes them."""
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    async def query_json(self, system, user, *, web_search=False):
        stage = next(name.removesuffix("_PROMPT").lower() for name in vars(prompts)
                     if name.endswith("_PROMPT") and getattr(prompts, name) == system)
        self.calls.append((stage, user))
        if stage == self.fail:
            raise ValueError("Synthetic retained-stage failure")
        source = {"url": "https://synthetic.invalid/record", "title": "Record"}
        values = {
            "deconstruct": {"core_event": "Model-proposed replacement", "date": "2023-01-01",
                "entities": {"people": [], "organizations": [], "locations": []},
                "key_claims": ["Model-proposed replacement"], "causal_hints": []},
            "search_plan": {"queries": [{"angle": "record", "query": "Original record"}]},
            "source_trace": {"sources": [{"url": source["url"], "outlet": "Record", "publish_time": "2023-01-01",
                "source_type": "record", "is_original": False,
                "facts": [{"claim": "A recorded claim.", "date_mentioned": "2023-01-01"}]}]},
            "source_verify": {"consistent_facts": [], "disputed_facts": [], "credibility_note": "One source only."},
            "causal_dig": {"causes": [{"title": "Earlier event", "date": "2023-01-01", "summary": "Proposal only.",
                "relation": "Reported background", "sources": [source], "confidence": 0.0, "grounded": False, "is_root": True}]},
            "grounding_check": {"checks": [{"node_id": "event_001", "event_title": "Earlier event", "grounded": False,
                "matching_urls": [], "note": "No causal proof."}]},
            "timeline_build": {"events": [{"date": "2023-01-01", "title": "Record", "description": "Reported event.",
                "significance": "重大", "sources": [source], "causal_links": [], "source_count": 1}]},
            "perspective": {"perspectives": [{"event_id": "timeline_000", "event_title": "Record", "views": [], "divergence_note": ""}]},
            "synthesis": {"key_findings": ["Inspect the record."], "information_gaps": ["Independent proof is missing."],
                "causal_summary": "", "bias_notes": []},
        }
        return deepcopy(values[stage])

    async def query(self, system, user, *, web_search=False):
        self.calls.append(("direct_response", user))
        return "Unverified research draft."


class NewsTracingCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_mode_keeps_exact_claim_source_research_and_intentional_skips(self):
        exact = "  The supplied record stated seven.  "
        client = ResearchModeClient()
        report = await NewsTracingAgent(client, research_mode="claim").run(exact)
        self.assertEqual([], report.errors)
        self.assertEqual([exact], report.parsed_claims)
        self.assertEqual(["deconstruct", "search_plan", "source_trace", "source_verify", "synthesis"],
                         [stage for stage, _ in client.calls])
        self.assertEqual(exact, client.calls[0][1])
        self.assertEqual([exact], json.loads(client.calls[1][1])["news"]["key_claims"])
        omitted = {"causal_dig", "grounding_check", "timeline_build", "perspective", "direct_response"}
        skips = [item for item in report.phase_status if item["status"] == "skipped"]
        self.assertEqual(omitted, {item["stage"] for item in skips})
        self.assertEqual(5, len(skips))
        self.assertEqual([], report.event.causes)
        self.assertEqual([], report.event_timeline)
        self.assertEqual("", report.direct_response)
        scope = report.limits["research_scope"]
        self.assertEqual("claim", report.limits["research_mode"])
        self.assertEqual(exact, scope["fixed_claim"])
        self.assertEqual(omitted, set(scope["intentionally_omitted_stages"]))
        self.assertEqual(scope, json.loads(client.calls[-1][1])["research_scope"])
        self.assertTrue(report.information_gaps)
        self.assertFalse(report.sources[0].is_original)

    async def test_default_full_mode_retains_every_research_and_presentation_phase(self):
        client = ResearchModeClient()
        report = await NewsTracingAgent(client).run("A supplied claim.")
        self.assertEqual([], report.errors)
        self.assertEqual({"deconstruct", "search_plan", "source_trace", "source_verify", "causal_dig", "grounding_check",
                          "timeline_build", "perspective", "direct_response", "synthesis"}, {stage for stage, _ in client.calls})
        self.assertEqual("full", report.limits["research_mode"])
        self.assertEqual([], report.limits["research_scope"]["intentionally_omitted_stages"])
        self.assertIsNone(report.limits["research_scope"]["fixed_claim"])
        self.assertTrue(report.event.causes)
        self.assertTrue(report.event_timeline)
        self.assertTrue(report.direct_response)

    async def test_claim_mode_retained_stage_failure_is_failed_never_relabelled_skipped(self):
        client = ResearchModeClient(fail="source_verify")
        report = await NewsTracingAgent(client, research_mode="claim").run("A fixed claim.")
        self.assertTrue(report.errors)
        self.assertEqual(["failed"], [p["status"] for p in report.phase_status if p["stage"] == "source_verify"])
        self.assertTrue(any("failed" in gap for gap in report.information_gaps))
        self.assertIn("source_verify", [stage for stage, _ in client.calls])
        self.assertEqual(5, sum(p["status"] == "skipped" for p in report.phase_status))

    async def test_unknown_or_nonstring_mode_is_rejected(self):
        for value in (None, True, [], "auto"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                NewsTracingAgent(ResearchModeClient(), research_mode=value)

    async def timeline(self, links):
        agent = NewsTracingAgent(TimelineClient(links))
        tree = EventNode("Galaxy", "未知", "Unverified event", node_id="event_000",
                         causes=[EventNode("Crossing", "未知", "Unverified cause",
                                           node_id="event_001")])
        timeline = await agent._build_timeline([], tree)
        self.assertFalse(timeline[0].verified)
        self.assertFalse(tree.grounded)
        self.assertFalse(tree.causes[0].grounded)
        return agent, timeline[0]

    async def test_live_legacy_causal_object_preserves_target_and_unverified_relation(self):
        target = "Bullseye环结构形成"
        relation = "报道将矮星系穿越中心解释为环形成的原因；此处仅保留为因果建议，未经独立验证。"
        agent, event = await self.timeline([{"target": target, "relation": relation}])
        self.assertEqual([], agent.errors)
        self.assertEqual(1, len(event.causal_links))
        self.assertIsInstance(event.causal_links[0], str)
        self.assertIn(target, event.causal_links[0])
        self.assertIn(relation, event.causal_links[0])

    async def test_unknown_or_mistyped_causal_objects_are_rejected_without_losing_text_links(self):
        agent, event = await self.timeline([
            "An existing unverified text link",
            {"target": "Missing relation"},
            {"target": "Extra field", "relation": "Proposed", "verified": True},
            {"target": 7, "relation": "Wrong target type"},
            {"target": "Wrong relation type", "relation": ["Proposed"]},
        ])
        self.assertEqual(["An existing unverified text link"], event.causal_links)
        self.assertEqual(4, len(agent.errors))
        self.assertTrue(all(e["stage"] == "timeline_build" and e["type"] == "InvalidField"
                            for e in agent.errors))


if __name__ == "__main__":
    unittest.main()
