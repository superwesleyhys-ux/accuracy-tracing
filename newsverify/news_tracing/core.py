"""Bounded, transport-independent adaptation of the uploaded tracing workflow."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime
from typing import Any

from .models import (
    CredibilityBreakdown, EventNode, FactClaim, SourceEntry, TimelineEvent,
    TracingReport,
)
from .prompts import (
    CAUSAL_DIG_PROMPT, DECONSTRUCT_PROMPT, DIRECT_RESPONSE_PROMPT,
    GROUNDING_CHECK_PROMPT, PERSPECTIVE_PROMPT, SEARCH_PLAN_PROMPT,
    SOURCE_TRACE_PROMPT, SOURCE_VERIFY_PROMPT, SYNTHESIS_PROMPT,
    TIMELINE_BUILD_PROMPT,
)


CLAIM_OMITTED_STAGES = ("causal_dig", "grounding_check", "timeline_build", "perspective", "direct_response")


class NewsTracingAgent:
    """Generate research proposals; the caller owns evidence and origin checks.

    ``llm`` is a duck-typed async client exposing query_json(system, user,
    web_search=False) and query(...). It owns transport, call budgets and search
    admission. This module never fetches URLs or initializes an API client.
    """

    def __init__(self, llm: Any, max_depth: int = 1, console: Any = None, *,
                 max_queries: int = 2, max_causes: int = 2, max_nodes: int = 8,
                 research_mode: str = "full"):
        if not isinstance(research_mode, str) or research_mode not in {"full", "claim"}:
            raise ValueError("research_mode must be full or claim")
        for name, value, low, high in (
            ("max_depth", max_depth, 0, 3), ("max_queries", max_queries, 1, 3),
            ("max_causes", max_causes, 1, 2), ("max_nodes", max_nodes, 1, 8),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        self.llm, self.console = llm, console
        self.max_depth, self.max_queries = max_depth, max_queries
        self.max_causes, self.max_nodes = max_causes, max_nodes
        self.research_mode = research_mode
        self.research_scope: dict = {}
        self.errors: list[dict] = []
        self.phase_status: list[dict] = []
        self.parsed_claims: list[str] = []
        self.parsed_event: dict = {}
        self._node_count = 1

    def _error(self, stage: str, kind: str, message: str) -> None:
        self.errors.append({"stage": stage, "type": kind, "message": message[:1000]})

    def _skip(self, stage: str, reason: str) -> None:
        self.phase_status.append({"stage": stage, "status": "skipped", "reason": reason})

    def _log(self, message: str) -> None:
        if self.console is not None:
            # Only caller-independent status text is emitted, never model markup.
            self.console.print(message)

    async def _json(self, stage: str, system: str, user: str, *,
                    web_search: bool = False) -> dict:
        try:
            result = await self.llm.query_json(system, user, web_search=web_search)
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
        except Exception as exc:
            self._error(stage, type(exc).__name__, str(exc))
            self.phase_status.append({"stage": stage, "status": "failed"})
            return {}
        self.phase_status.append({"stage": stage, "status": "completed"})
        return result

    def _text(self, value: Any, stage: str, field: str, limit: int = 6000) -> str:
        if not isinstance(value, str):
            self._error(stage, "InvalidField", f"{field} must be a string")
            return ""
        if len(value) > limit:
            self._error(stage, "OutputLimit", f"{field} truncated at {limit} characters")
        return value[:limit].strip()

    def _items(self, value: Any, stage: str, field: str, limit: int) -> list:
        if not isinstance(value, list):
            self._error(stage, "InvalidField", f"{field} must be an array")
            return []
        if len(value) > limit:
            self._error(stage, "OutputLimit", f"{field} truncated at {limit} items")
        return value[:limit]

    def _objects(self, value: Any, stage: str, field: str, limit: int) -> list[dict]:
        result = []
        for item in self._items(value, stage, field, limit):
            if isinstance(item, dict):
                result.append(item)
            else:
                self._error(stage, "InvalidField", f"{field} items must be objects")
        return result

    def _strings(self, value: Any, stage: str, field: str, limit: int) -> list[str]:
        return list(dict.fromkeys(
            text for item in self._items(value, stage, field, limit)
            if (text := self._text(item, stage, field))
        ))

    def _bool(self, value: Any, stage: str, field: str) -> bool:
        if type(value) is not bool:
            self._error(stage, "InvalidField", f"{field} must be a boolean")
            return False
        return value

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    async def run(self, news_input: str) -> TracingReport:
        if not isinstance(news_input, str) or not news_input.strip():
            raise ValueError("news_input must be nonempty text")
        if len(news_input) > 100_000:
            raise ValueError("news_input exceeds 100000 characters")
        self.errors, self.phase_status = [], []
        self.parsed_claims, self.parsed_event = [], {}
        self._node_count = 1
        self._log("Preparing news research proposals.")
        self.research_scope = {"mode": self.research_mode,
            "fixed_claim": news_input if self.research_mode == "claim" else None,
            "intentionally_omitted_stages": list(CLAIM_OMITTED_STAGES) if self.research_mode == "claim" else [],
            "omitted_stages_are_not_failed_checks": True}
        parsed = await self._deconstruct(news_input)
        if self.research_mode == "claim":
            # This input is an explicit claim selected by the caller. Parsing
            # may annotate it, but cannot substitute a different research target.
            parsed["key_claims"] = [news_input]
        self.parsed_event = parsed
        self.parsed_claims = list(parsed["key_claims"])
        queries = await self._plan_searches(parsed)
        event = EventNode(title=parsed["core_event"], date=parsed["date"],
                          summary="; ".join(self.parsed_claims), node_id="event_000")
        pool: list[SourceEntry] = []
        verify_data: dict = {}
        if self.research_mode == "claim":
            try:
                pool, verify_data = await self._trace_sources(queries)
            except Exception as exc:
                self._error("source_track", type(exc).__name__, str(exc))
            for stage in CLAIM_OMITTED_STAGES:
                self._skip(stage, "Intentionally omitted by claim mode; source research and formal evidence checks remain separate.")
            timeline, direct = [], ""
        else:
            tracks = await asyncio.gather(
                self._trace_sources(queries), self._dig_causes(event, 0),
                return_exceptions=True,
            )
            if isinstance(tracks[0], BaseException):
                self._error("source_track", type(tracks[0]).__name__, str(tracks[0]))
            else:
                pool, verify_data = tracks[0]
            if isinstance(tracks[1], BaseException):
                self._error("causal_track", type(tracks[1]).__name__, str(tracks[1]))
            else:
                event = tracks[1]
            event = await self._ground_check(event, pool)
            timeline = await self._build_timeline(pool, event)
            timeline = await self._analyze_perspectives(timeline, pool)
        credibility = self._compute_credibility(pool, verify_data, event)
        if self.research_mode == "full":
            direct = await self._generate_direct_response(
                news_input, timeline, verify_data, event, credibility)
        report = await self._synthesize(event, pool, verify_data, timeline, credibility)
        report.direct_response = direct
        report.errors = list(self.errors)
        report.phase_status = list(self.phase_status)
        report.parsed_claims = list(self.parsed_claims)
        report.parsed_event = dict(self.parsed_event)
        report.limits = {
            "max_depth": self.max_depth, "max_queries": self.max_queries,
            "max_causes": self.max_causes, "max_nodes": self.max_nodes,
            "max_claims": 1 if self.research_mode == "claim" else 3, "allocated_nodes": self._node_count,
            "research_mode": self.research_mode, "research_scope": dict(self.research_scope),
        }
        if self.errors:
            report.information_gaps.append(
                "Some research stages failed or returned invalid/truncated data; inspect errors.")
        return report

    async def _deconstruct(self, news_input: str) -> dict:
        stage = "deconstruct"
        result = await self._json(stage, DECONSTRUCT_PROMPT, news_input)
        entities = result.get("entities", {})
        if not isinstance(entities, dict):
            self._error(stage, "InvalidField", "entities must be an object")
            entities = {}
        return {
            "core_event": self._text(result.get("core_event", ""), stage, "core_event"),
            "date": self._text(result.get("date", "未知"), stage, "date", 200),
            "entities": {key: self._strings(entities.get(key, []), stage, key, 20)
                         for key in ("people", "organizations", "locations")},
            "key_claims": self._strings(result.get("key_claims", []), stage, "key_claims", 3),
            "causal_hints": self._strings(result.get("causal_hints", []), stage, "causal_hints", 6),
        }

    async def _plan_searches(self, parsed: dict) -> list[dict]:
        if not parsed["key_claims"] and not parsed["core_event"]:
            self._skip("search_plan", "No parsed event or claims")
            return []
        result = await self._json("search_plan", SEARCH_PLAN_PROMPT,
                                  self._dump({"news": parsed, "max_queries": self.max_queries}))
        queries = []
        for q in self._objects(result.get("queries", []), "search_plan", "queries", self.max_queries):
            query = self._text(q.get("query", ""), "search_plan", "query", 1000)
            if query:
                queries.append({"query": query, "angle": self._text(
                    q.get("angle", ""), "search_plan", "angle", 200)})
        return queries

    async def _trace_sources(self, queries: list[dict]) -> tuple[list[SourceEntry], dict]:
        results = await asyncio.gather(*(self._search_one_angle(q) for q in queries))
        pool = self._merge_sources([source for group in results for source in group])
        if not pool:
            self._skip("source_verify", "No source proposals")
            return [], {}
        data = await self._json("source_verify", SOURCE_VERIFY_PROMPT,
                                self._format_pool_for_verify(pool))
        # Do not forward arbitrary verifier fields or oversized lists into later
        # prompts. All agreement remains an unverified model proposal.
        normalized = {}
        for key in ("consistent_facts", "disputed_facts"):
            normalized[key] = [{"claim": f.claim, "source_urls": f.source_urls,
                                "versions": f.versions}
                               for f in self._fact_proposals(data, key, pool)]
        normalized["credibility_note"] = self._text(
            data.get("credibility_note", ""), "source_verify", "credibility_note")
        return pool, normalized

    async def _search_one_angle(self, query: dict) -> list[dict]:
        result = await self._json("source_trace", SOURCE_TRACE_PROMPT,
                                  self._dump(query), web_search=True)
        return self._objects(result.get("sources", []), "source_trace", "sources", 5)

    def _merge_sources(self, sources: list[dict]) -> list[SourceEntry]:
        pool: list[SourceEntry] = []
        by_url: dict[str, SourceEntry] = {}
        stage = "source_trace"
        for raw in sources:
            url = self._text(raw.get("url", ""), stage, "url", 2000)
            fields = {key: self._text(raw.get(key, ""), stage, key, 500)
                      for key in ("outlet", "publish_time", "source_type")}
            proposal = self._bool(raw.get("is_original", False), stage, "is_original")
            # Missing URLs cannot establish identity, even for the same outlet.
            entry = by_url.get(url) if url else None
            if entry is None:
                entry = SourceEntry(url=url, **fields, model_proposed_original=proposal)
                pool.append(entry)
                if url:
                    by_url[url] = entry
            else:
                entry.model_proposed_original |= proposal
                for key, value in fields.items():
                    existing = getattr(entry, key)
                    if value and not existing:
                        setattr(entry, key, value)
                    elif value and value != existing:
                        entry.metadata_conflicts.append({"field": key, "first": existing,
                                                         "additional": value})
            seen = {(fact.claim, fact.date_mentioned) for fact in entry.key_facts}
            for fact in self._objects(raw.get("facts", []), stage, "facts", 12):
                claim = self._text(fact.get("claim", ""), stage, "claim")
                date = self._text(fact.get("date_mentioned", ""), stage, "date_mentioned", 200)
                if claim and (claim, date) not in seen:
                    entry.key_facts.append(FactClaim(claim, [url] if url else [], date_mentioned=date))
                    seen.add((claim, date))
        return pool

    def _format_pool_for_verify(self, pool: list[SourceEntry]) -> str:
        return self._dump([{
            "outlet": s.outlet, "source_type": s.source_type, "url": s.url,
            "publish_time": s.publish_time, "metadata_conflicts": s.metadata_conflicts,
            "facts": [{"claim": f.claim, "date_mentioned": f.date_mentioned}
                      for f in s.key_facts], "status": "unverified_model_proposal",
        } for s in pool])

    def _source_refs(self, value: Any, stage: str) -> list[dict]:
        refs = []
        for item in self._items(value, stage, "sources", 10):
            if isinstance(item, str):
                item = {"url": item, "title": ""}
            if not isinstance(item, dict):
                self._error(stage, "InvalidField", "source reference must be an object or URL")
                continue
            ref = {key: self._text(item.get(key, ""), stage, key, 2000)
                   for key in ("url", "title")}
            if ref not in refs:
                refs.append(ref)
        return refs

    async def _dig_causes(self, event: EventNode, depth: int) -> EventNode:
        if depth >= self.max_depth or self._node_count >= self.max_nodes or not event.title:
            self._skip("causal_dig", "Depth/node bound reached or no event")
            return event
        remaining = min(self.max_causes, self.max_nodes - self._node_count)
        result = await self._json("causal_dig", CAUSAL_DIG_PROMPT, self._dump({
            "node_id": event.node_id, "title": event.title, "date": event.date,
            "summary": event.summary, "max_causes": remaining,
        }), web_search=True)
        children = []
        for raw in self._objects(result.get("causes", []), "causal_dig", "causes", remaining):
            title = self._text(raw.get("title", ""), "causal_dig", "title")
            if not title:
                continue
            confidence = raw.get("confidence", 0.0)
            if (type(confidence) not in (int, float) or not 0 <= confidence <= 1
                    or not math.isfinite(confidence)):
                self._error("causal_dig", "InvalidField", "confidence must be finite and between 0 and 1")
                confidence = 0.0
            child = EventNode(
                title=title, date=self._text(raw.get("date", "未知"), "causal_dig", "date", 200),
                summary=self._text(raw.get("summary", ""), "causal_dig", "summary"),
                relation=self._text(raw.get("relation", ""), "causal_dig", "relation"),
                sources=self._source_refs(raw.get("sources", []), "causal_dig"),
                confidence=float(confidence), node_id=f"event_{self._node_count:03d}",
                model_grounded=self._bool(raw.get("grounded", False), "causal_dig", "grounded"),
                model_is_root=self._bool(raw.get("is_root", False), "causal_dig", "is_root"),
            )
            self._node_count += 1
            children.append(child)
        # Reserve siblings before recursion so the global bound includes all of them.
        event.causes = children
        for child in children:
            if not child.model_is_root:
                await self._dig_causes(child, depth + 1)
        return event

    @staticmethod
    def _nodes(root: EventNode) -> list[EventNode]:
        nodes = [root]
        for child in root.causes:
            nodes.extend(NewsTracingAgent._nodes(child))
        return nodes

    def _tree_to_text(self, root: EventNode) -> str:
        return self._dump([{
            "node_id": n.node_id, "title": n.title, "date": n.date,
            "summary": n.summary, "relation": n.relation, "sources": n.sources,
            "child_ids": [c.node_id for c in n.causes], "status": "unverified_model_proposal",
        } for n in self._nodes(root)])

    async def _ground_check(self, tree: EventNode, pool: list[SourceEntry]) -> EventNode:
        if not tree.causes:
            self._skip("grounding_check", "No proposed causal nodes")
            return tree
        data = await self._json("grounding_check", GROUNDING_CHECK_PROMPT, self._dump({
            "tree": json.loads(self._tree_to_text(tree)),
            "sources": json.loads(self._format_pool_for_verify(pool)),
        }))
        nodes = {node.node_id: node for node in self._nodes(tree)}
        pool_urls = {source.url for source in pool if source.url}
        seen = set()
        for check in self._objects(data.get("checks", []), "grounding_check", "checks", self.max_nodes):
            node_id = self._text(check.get("node_id", ""), "grounding_check", "node_id", 100)
            if node_id not in nodes or node_id in seen:
                self._error("grounding_check", "InvalidReference", "Unknown or duplicate node_id")
                continue
            seen.add(node_id)
            node = nodes[node_id]
            urls = self._strings(check.get("matching_urls", []), "grounding_check", "matching_urls", 15)
            allowed = pool_urls | {ref["url"] for ref in node.sources if ref["url"]}
            if any(url not in allowed for url in urls):
                self._error("grounding_check", "InvalidReference", "matching_urls included a URL outside supplied proposals")
            node.model_grounding_check = {
                "grounded": self._bool(check.get("grounded", False), "grounding_check", "grounded"),
                "matching_urls": [url for url in urls if url in allowed],
                "note": self._text(check.get("note", ""), "grounding_check", "note"),
            }
        return tree

    def _compute_credibility(self, pool: list[SourceEntry], verify_data: dict,
                             tree: EventNode) -> CredibilityBreakdown:
        nodes = self._nodes(tree)[1:]
        return CredibilityBreakdown(
            source_count=len(pool), source_types=sorted({s.source_type for s in pool if s.source_type}),
            consistent_count=len(self._fact_proposals(verify_data, "consistent_facts", pool)),
            disputed_count=len(self._fact_proposals(verify_data, "disputed_facts", pool)),
            total_causal_nodes=len(nodes), model_grounded_count=sum(n.model_grounded for n in nodes),
        )

    def _causal_link_text(self, value: Any) -> list[str]:
        """Keep legacy target/relation suggestions as text, never trusted edges."""
        result = []
        for item in self._items(value, "timeline_build", "causal_links", 10):
            if isinstance(item, dict):
                if (set(item) != {"target", "relation"}
                        or any(not isinstance(item[key], str) for key in ("target", "relation"))):
                    self._error("timeline_build", "InvalidField",
                                "causal_links objects require only string target and relation")
                    continue
                target = self._text(item["target"], "timeline_build", "causal_links.target", 2000)
                relation = self._text(item["relation"], "timeline_build", "causal_links.relation", 6000)
                text = f"{target} — {relation}" if target or relation else ""
            else:
                text = self._text(item, "timeline_build", "causal_links")
            if text and text not in result:
                result.append(text)
        return result

    async def _build_timeline(self, pool: list[SourceEntry], tree: EventNode) -> list[TimelineEvent]:
        if not any(s.key_facts for s in pool) and not tree.causes:
            self._skip("timeline_build", "No facts or causal proposals")
            return []
        data = await self._json("timeline_build", TIMELINE_BUILD_PROMPT, self._dump({
            "sources": json.loads(self._format_pool_for_verify(pool)),
            "tree": json.loads(self._tree_to_text(tree)),
        }))
        allowed = {s.url for s in pool if s.url} | {
            ref["url"] for node in self._nodes(tree) for ref in node.sources if ref["url"]}
        events = []
        for raw in self._objects(data.get("events", []), "timeline_build", "events", 20):
            refs = self._source_refs(raw.get("sources", []), "timeline_build")
            if any(ref["url"] and ref["url"] not in allowed for ref in refs):
                self._error("timeline_build", "InvalidReference", "Event included an unsupplied source URL")
            refs = [ref for ref in refs if ref["url"] in allowed]
            count = raw.get("source_count", 0)
            if type(count) is not int or count < 0:
                self._error("timeline_build", "InvalidField", "source_count must be a nonnegative integer")
                count = 0
            significance = self._text(raw.get("significance", "重要"), "timeline_build", "significance", 100)
            if significance not in {"重大", "重要", "背景"}:
                self._error("timeline_build", "InvalidField", "Unknown significance")
                significance = "重要"
            events.append(TimelineEvent(
                date=self._text(raw.get("date", "未知"), "timeline_build", "date", 200),
                title=self._text(raw.get("title", ""), "timeline_build", "title"),
                description=self._text(raw.get("description", ""), "timeline_build", "description"),
                significance=significance, sources=refs,
                causal_links=self._causal_link_text(raw.get("causal_links", [])),
                event_id=f"timeline_{len(events):03d}", proposed_source_count=count,
                unique_source_url_count=len({ref["url"] for ref in refs if ref["url"]}),
            ))
        return events

    async def _analyze_perspectives(self, timeline: list[TimelineEvent],
                                     pool: list[SourceEntry]) -> list[TimelineEvent]:
        major = {event.event_id: event for event in timeline if event.significance == "重大"}
        if not major:
            self._skip("perspective", "No major events")
            return timeline
        data = await self._json("perspective", PERSPECTIVE_PROMPT, self._dump({
            "events": [{"event_id": e.event_id, "title": e.title, "description": e.description}
                       for e in major.values()],
            "sources": json.loads(self._format_pool_for_verify(pool)),
        }))
        seen = set()
        for raw in self._objects(data.get("perspectives", []), "perspective", "perspectives", 20):
            event_id = self._text(raw.get("event_id", ""), "perspective", "event_id", 100)
            if event_id not in major or event_id in seen:
                self._error("perspective", "InvalidReference", "Unknown or duplicate event_id")
                continue
            seen.add(event_id)
            major[event_id].perspectives = [
                {key: self._text(view.get(key, ""), "perspective", key) for key in ("source", "framing")}
                for view in self._objects(raw.get("views", []), "perspective", "views", 4)]
            major[event_id].divergence_note = self._text(raw.get("divergence_note", ""), "perspective", "divergence_note")
        return timeline

    def _fact_proposals(self, data: dict, key: str, pool: list[SourceEntry]) -> list[FactClaim]:
        facts = []
        allowed = {s.url for s in pool if s.url}
        for raw in self._objects(data.get(key, []), "source_verify", key, 30):
            claim = self._text(raw.get("claim", ""), "source_verify", "claim")
            urls = self._strings(raw.get("source_urls", []), "source_verify", "source_urls", 15)
            if any(url not in allowed for url in urls):
                self._error("source_verify", "InvalidReference", "Fact included an unsupplied source URL")
            versions = [{k: self._text(v.get(k, ""), "source_verify", k)
                         for k in ("source", "statement")}
                        for v in self._objects(raw.get("versions", []), "source_verify", "versions", 10)]
            if claim:
                facts.append(FactClaim(claim, [url for url in urls if url in allowed],
                                       model_agreement="consistent" if key == "consistent_facts" else "disputed",
                                       versions=versions))
        return facts

    async def _generate_direct_response(self, news_input: str, timeline: list[TimelineEvent],
                                        verify_data: dict, tree: EventNode,
                                        credibility: CredibilityBreakdown) -> str:
        user = self._dump({"input": news_input, "tree": json.loads(self._tree_to_text(tree)),
                           "timeline": [vars(e) for e in timeline],
                           "agreement_proposals": verify_data, "errors": self.errors,
                           "all_analysis_unverified": True})
        try:
            response = await self.llm.query(DIRECT_RESPONSE_PROMPT, user, web_search=False)
            if not isinstance(response, str):
                raise ValueError("Expected a plain-text response")
        except Exception as exc:
            self._error("direct_response", type(exc).__name__, str(exc))
            self.phase_status.append({"stage": "direct_response", "status": "failed"})
            return ""
        self.phase_status.append({"stage": "direct_response", "status": "completed"})
        return self._text(response, "direct_response", "response", 12000)

    @staticmethod
    def _publication_key(source: SourceEntry) -> tuple:
        # Order only parseable calendar dates; preserve uncertain dates last.
        text = source.publish_time
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return (0, parsed.date().isoformat())
        except ValueError:
            return (1, "")

    async def _synthesize(self, tree: EventNode, pool: list[SourceEntry], verify_data: dict,
                           timeline: list[TimelineEvent], credibility: CredibilityBreakdown) -> TracingReport:
        data = await self._json("synthesis", SYNTHESIS_PROMPT, self._dump({
            "tree": json.loads(self._tree_to_text(tree)),
            "sources": json.loads(self._format_pool_for_verify(pool)),
            "timeline": [vars(e) for e in timeline], "agreement_proposals": verify_data,
            "proposal_counts": vars(credibility), "errors": self.errors,
            "research_scope": self.research_scope,
        }))
        return TracingReport(
            event=tree, sources=pool, source_timeline=sorted(pool, key=self._publication_key),
            event_timeline=timeline, credibility=credibility,
            consistent_facts=self._fact_proposals(verify_data, "consistent_facts", pool),
            disputed_facts=self._fact_proposals(verify_data, "disputed_facts", pool),
            key_findings=self._strings(data.get("key_findings", []), "synthesis", "key_findings", 20),
            information_gaps=self._strings(data.get("information_gaps", []), "synthesis", "information_gaps", 20),
            causal_summary=self._text(data.get("causal_summary", ""), "synthesis", "causal_summary", 12000),
            bias_notes=self._strings(data.get("bias_notes", []), "synthesis", "bias_notes", 20),
        )
