from __future__ import annotations

import asyncio

from rich.console import Console

from . import prompts
from .llm_client import LLMClient
from .models import (
    CredibilityBreakdown,
    EventNode,
    FactClaim,
    SourceEntry,
    TimelineEvent,
    TracingReport,
)


class NewsTracingAgent:
    """双轨并行 + 递归因果挖掘的新闻溯源 Agent（精细化版）。"""

    def __init__(
        self,
        llm: LLMClient,
        max_depth: int = 3,
        console: Console | None = None,
    ) -> None:
        self.llm = llm
        self.max_depth = max_depth
        self.console = console or Console()

    # ══ 主入口 ══════════════════════════════════════════════

    async def run(self, news_input: str) -> TracingReport:
        # Phase 1: 解构 + 搜索规划
        self.console.print("\n[bold cyan]Phase 1: 解构 + 搜索规划[/bold cyan]")
        parsed = await self._deconstruct(news_input)

        self.console.print(f"  核心事件: {parsed.get('core_event', '?')}")
        self.console.print(f"  日期: {parsed.get('date', '未知')}")
        entities = parsed.get("entities", {})
        ent_list = entities.get("people", []) + entities.get("organizations", [])
        if ent_list:
            self.console.print(f"  关键实体: {', '.join(ent_list)}")

        queries = await self._plan_searches(parsed)
        self.console.print(f"  搜索策略: {len(queries)} 个角度")
        for q in queries:
            self.console.print(f"    - [{q['angle']}] {q['query']}")

        root_event = EventNode(
            title=parsed.get("core_event", "未知事件"),
            date=parsed.get("date", "未知"),
            summary="\n".join(parsed.get("key_claims", [])),
        )

        # Phase 2: 双轨并行
        self.console.print("\n[bold cyan]Phase 2: 双轨并行分析[/bold cyan]")

        source_result, causal_tree = await asyncio.gather(
            self._trace_sources(queries),
            self._dig_causes(root_event, depth=0),
        )
        source_pool, verify_data = source_result

        # Phase 3: 时间线构建 + 锚定验证 + 综合研判
        self.console.print(
            "\n[bold cyan]Phase 3: 时间线构建 + 综合研判[/bold cyan]"
        )

        causal_tree = await self._ground_check(causal_tree, source_pool)

        event_timeline = await self._build_timeline(source_pool, causal_tree)
        self.console.print(f"  事件时间线: {len(event_timeline)} 个事件")

        event_timeline = await self._analyze_perspectives(
            event_timeline, source_pool,
        )

        cred = self._compute_credibility(
            source_pool, verify_data, causal_tree,
        )
        self.console.print(
            f"  可信度: {cred.source_count} 信源 | "
            f"{len(cred.source_types)} 类 | "
            f"锚定 {cred.grounded_count}/{cred.total_causal_nodes}"
        )

        direct_response = await self._generate_direct_response(
            news_input, source_pool, verify_data,
            event_timeline, causal_tree, cred,
        )

        report = await self._synthesize(
            source_pool, verify_data, causal_tree,
            event_timeline, cred, direct_response,
        )

        self.console.print(f"\n[dim]{self.llm.token_summary}[/dim]")
        return report

    # ══ Phase 1: 解构 + 搜索规划 ═══════════════════════════

    async def _deconstruct(self, news_input: str) -> dict:
        return await self.llm.query_json(
            prompts.DECONSTRUCT_PROMPT, news_input,
        )

    async def _plan_searches(self, parsed: dict) -> list[dict]:
        plan_input = (
            f"核心事件: {parsed.get('core_event', '')}\n"
            f"日期: {parsed.get('date', '未知')}\n"
            f"人物: {parsed.get('entities', {}).get('people', [])}\n"
            f"组织: {parsed.get('entities', {}).get('organizations', [])}\n"
            f"地点: {parsed.get('entities', {}).get('locations', [])}\n"
            f"关键声明:\n"
            + "\n".join(f"- {c}" for c in parsed.get("key_claims", []))
        )
        result = await self.llm.query_json(
            prompts.SEARCH_PLAN_PROMPT, plan_input,
        )
        return result.get("queries", [])

    # ══ Track A: 多轮信源采集 ══════════════════════════════

    async def _trace_sources(
        self, queries: list[dict],
    ) -> tuple[list[SourceEntry], dict]:
        # A1: 并行多角度搜索
        self.console.print("  [yellow]Track A[/yellow]: 并行搜索中…")
        tasks = [self._search_one_angle(q) for q in queries]
        raw_batches = await asyncio.gather(*tasks)

        # A2: 合并去重
        pool = self._merge_sources(raw_batches)
        self.console.print(
            f"  [yellow]Track A[/yellow]: "
            f"合并去重后 {len(pool)} 个信源"
        )

        # A3: 交叉验证
        self.console.print("  [yellow]Track A[/yellow]: 交叉验证中…")
        verify_input = self._format_pool_for_verify(pool)
        verify_data = await self.llm.query_json(
            prompts.SOURCE_VERIFY_PROMPT,
            verify_input,
            web_search=True,
        )
        self.console.print("  [yellow]Track A[/yellow]: 信源考古完成 ✓")
        return pool, verify_data

    async def _search_one_angle(self, q: dict) -> list[dict]:
        angle = q.get("angle", "")
        query = q.get("query", "")
        self.console.print(
            f"    [yellow]搜索[/yellow] [{angle}] {query}"
        )
        try:
            result = await self.llm.query_json(
                prompts.SOURCE_TRACE_PROMPT,
                f"搜索主题: {query}\n搜索角度: {angle}",
                web_search=True,
            )
            return result.get("sources", [])
        except Exception as e:
            self.console.print(f"    [red]搜索失败: {e}[/red]")
            return []

    @staticmethod
    def _merge_sources(raw_batches: list[list[dict]]) -> list[SourceEntry]:
        seen_urls: set[str] = set()
        seen_outlets: set[str] = set()
        pool: list[SourceEntry] = []

        for batch in raw_batches:
            for s in batch:
                url = s.get("url", "").strip()
                outlet = s.get("outlet", "").strip()

                # URL 去重
                if url and url in seen_urls:
                    continue
                # 无 URL 时按媒体名去重
                if not url and outlet and outlet in seen_outlets:
                    continue

                if url:
                    seen_urls.add(url)
                if outlet:
                    seen_outlets.add(outlet)

                facts = [
                    FactClaim(
                        claim=f.get("claim", ""),
                        source_urls=[url] if url else [],
                    )
                    for f in s.get("facts", [])
                ]

                pool.append(SourceEntry(
                    outlet=outlet,
                    url=url,
                    publish_time=s.get("publish_time", ""),
                    source_type=s.get("source_type", ""),
                    is_original=s.get("is_original", False),
                    key_facts=facts,
                ))

        return pool

    @staticmethod
    def _format_pool_for_verify(pool: list[SourceEntry]) -> str:
        lines = []
        for s in pool:
            header = f"[{s.outlet}] ({s.source_type}) {s.url}"
            facts = "\n".join(
                f"  - {f.claim}" for f in s.key_facts
            )
            lines.append(f"{header}\n{facts}")
        return "以下是多个信源的报道及其事实声明，请逐条交叉验证:\n\n" + "\n\n".join(lines)

    # ══ Track B: 有据因果挖掘 ══════════════════════════════

    async def _dig_causes(self, event: EventNode, depth: int) -> EventNode:
        if depth >= self.max_depth:
            return event

        indent = "  " + "  " * depth
        self.console.print(
            f"{indent}[magenta]Track B[/magenta]: "
            f"挖掘因果 (层 {depth + 1}/{self.max_depth}) — {event.title}"
        )

        prompt_input = (
            f"事件: {event.title}\n"
            f"日期: {event.date}\n"
            f"概要: {event.summary}"
        )

        try:
            result = await self.llm.query_json(
                prompts.CAUSAL_DIG_PROMPT,
                prompt_input,
                web_search=True,
            )
        except Exception as e:
            self.console.print(f"{indent}[red]因果挖掘失败: {e}[/red]")
            return event

        children: list[EventNode] = []
        for c in result.get("causes", []):
            raw_sources = c.get("sources", [])
            sources = []
            for src in raw_sources:
                if isinstance(src, dict):
                    sources.append(src)
                elif isinstance(src, str):
                    sources.append({"url": "", "title": src})

            child = EventNode(
                title=c.get("title", "未知"),
                date=c.get("date", "未知"),
                summary=c.get("summary", ""),
                sources=sources,
                relation=c.get("relation", ""),
                confidence=c.get("confidence", 0.5),
                grounded=c.get("grounded", False),
            )
            if not c.get("is_root", False):
                child = await self._dig_causes(child, depth + 1)
            children.append(child)

        event.causes = children

        if depth == 0:
            self.console.print("  [magenta]Track B[/magenta]: 因果挖掘完成 ✓")

        return event

    # ══ Phase 3: 锚定验证 + 综合研判 ══════════════════════

    async def _ground_check(
        self, tree: EventNode, pool: list[SourceEntry],
    ) -> EventNode:
        self.console.print("  锚定检查: 因果树 vs 信源池…")

        tree_text = self._tree_to_text(tree)
        pool_text = "\n".join(
            f"- [{s.outlet}] {s.url}: "
            + "; ".join(f.claim for f in s.key_facts)
            for s in pool
        )

        try:
            result = await self.llm.query_json(
                prompts.GROUNDING_CHECK_PROMPT,
                f"=== 因果事件树 ===\n{tree_text}\n\n"
                f"=== 信源池 ===\n{pool_text}",
            )
        except Exception as e:
            self.console.print(f"  [red]锚定检查失败: {e}[/red]")
            return tree

        check_map = {
            c["event_title"]: c
            for c in result.get("checks", [])
        }
        self._apply_grounding(tree, check_map)
        return tree

    def _apply_grounding(self, node: EventNode, check_map: dict) -> None:
        check = check_map.get(node.title)
        if check:
            node.grounded = check.get("grounded", node.grounded)
        for child in node.causes:
            self._apply_grounding(child, check_map)

    @staticmethod
    def _count_grounding(tree: EventNode) -> tuple[int, int]:
        total, grounded = 0, 0

        def walk(node: EventNode) -> None:
            nonlocal total, grounded
            for child in node.causes:
                total += 1
                if child.grounded:
                    grounded += 1
                walk(child)

        walk(tree)
        return total, grounded

    @staticmethod
    def _compute_credibility(
        pool: list[SourceEntry],
        verify_data: dict,
        causal_tree: EventNode,
    ) -> CredibilityBreakdown:
        source_types = sorted({s.source_type for s in pool if s.source_type})
        n_consistent = len(verify_data.get("consistent_facts", []))
        n_disputed = len(verify_data.get("disputed_facts", []))
        total, grounded = NewsTracingAgent._count_grounding(causal_tree)
        return CredibilityBreakdown(
            source_count=len(pool),
            source_types=source_types,
            consistent_count=n_consistent,
            disputed_count=n_disputed,
            grounding_rate=grounded / total if total else 0.0,
            grounded_count=grounded,
            total_causal_nodes=total,
        )

    # ── 时间线构建 ─────────────────────────────────────────

    async def _build_timeline(
        self,
        pool: list[SourceEntry],
        causal_tree: EventNode,
    ) -> list[TimelineEvent]:
        self.console.print("  构建事件时间线…")

        facts_text = self._collect_facts_text(pool)
        causal_text = self._flatten_tree_text(causal_tree)

        build_input = (
            f"=== 信源事实 ===\n{facts_text}\n\n"
            f"=== 因果事件 ===\n{causal_text}"
        )

        try:
            result = await self.llm.query_json(
                prompts.TIMELINE_BUILD_PROMPT, build_input,
            )
        except Exception as e:
            self.console.print(f"  [red]时间线构建失败: {e}[/red]")
            return []

        events: list[TimelineEvent] = []
        for ev in result.get("events", []):
            raw_sources = ev.get("sources", [])
            sources = []
            for src in raw_sources:
                if isinstance(src, dict):
                    sources.append(src)
                elif isinstance(src, str):
                    sources.append({"url": "", "title": src})

            src_count = ev.get("source_count", len(sources))
            events.append(TimelineEvent(
                date=ev.get("date", "未知"),
                title=ev.get("title", ""),
                description=ev.get("description", ""),
                significance=ev.get("significance", "重要"),
                sources=sources,
                verified=src_count >= 2,
                causal_links=ev.get("causal_links", []),
            ))

        return events

    @staticmethod
    def _collect_facts_text(pool: list[SourceEntry]) -> str:
        lines: list[str] = []
        for s in pool:
            for f in s.key_facts:
                lines.append(
                    f"- [{s.outlet}] {f.claim} (来源: {s.url or '无链接'})"
                )
        return "\n".join(lines) if lines else "(无事实数据)"

    @staticmethod
    def _flatten_tree_text(node: EventNode) -> str:
        items: list[str] = []

        def walk(n: EventNode) -> None:
            src_info = ", ".join(
                s.get("title", s.get("url", "?")) for s in n.sources[:3]
            )
            items.append(
                f"- {n.title} ({n.date}): {n.summary}"
                + (f" [来源: {src_info}]" if src_info else "")
            )
            for child in n.causes:
                walk(child)

        walk(node)
        return "\n".join(items) if items else "(无因果数据)"

    # ── 多方视角对比 ───────────────────────────────────────

    async def _analyze_perspectives(
        self,
        timeline: list[TimelineEvent],
        pool: list[SourceEntry],
    ) -> list[TimelineEvent]:
        major_events = [e for e in timeline if e.significance == "重大"]
        if not major_events:
            return timeline

        self.console.print(
            f"  多方视角分析 ({len(major_events)} 个重大事件)…"
        )

        events_text = "\n".join(
            f"- {e.title}: {e.description}" for e in major_events
        )
        pool_text = "\n".join(
            f"- [{s.outlet}] ({s.source_type}): "
            + "; ".join(f.claim for f in s.key_facts[:3])
            for s in pool
        )

        try:
            result = await self.llm.query_json(
                prompts.PERSPECTIVE_PROMPT,
                f"=== 重大事件 ===\n{events_text}\n\n"
                f"=== 信源池 ===\n{pool_text}",
            )
        except Exception as e:
            self.console.print(f"  [red]视角分析失败: {e}[/red]")
            return timeline

        perspective_map: dict[str, list[dict]] = {}
        for p in result.get("perspectives", []):
            perspective_map[p.get("event_title", "")] = p.get("views", [])

        for ev in timeline:
            views = perspective_map.get(ev.title, [])
            if views:
                ev.perspectives = views

        self.console.print("  多方视角分析完成 ✓")
        return timeline

    # ── 直答生成 ───────────────────────────────────────────

    async def _generate_direct_response(
        self,
        news_input: str,
        pool: list[SourceEntry],
        verify_data: dict,
        event_timeline: list[TimelineEvent],
        causal_tree: EventNode,
        cred: CredibilityBreakdown,
    ) -> str:
        self.console.print("  生成直答…")

        timeline_text = "\n".join(
            f"- [{e.significance}] {e.date}: {e.title} — {e.description}"
            for e in event_timeline[:15]
        )
        tree_text = self._tree_to_text(causal_tree)

        dr_input = (
            f"=== 用户原始输入 ===\n{news_input}\n\n"
            f"=== 事件时间线 ({len(event_timeline)} 个事件) ===\n"
            f"{timeline_text}\n\n"
            f"=== 交叉验证 ===\n"
            f"一致事实: {verify_data.get('consistent_facts', [])}\n"
            f"分歧事实: {verify_data.get('disputed_facts', [])}\n\n"
            f"=== 因果链摘要 ===\n{tree_text}\n\n"
            f"=== 可信度原始数据 ===\n"
            f"信源总数: {cred.source_count}\n"
            f"信源类型: {', '.join(cred.source_types)}\n"
            f"多源一致事实: {cred.consistent_count} 条\n"
            f"存在分歧事实: {cred.disputed_count} 条\n"
            f"因果锚定: {cred.grounded_count}/{cred.total_causal_nodes}"
        )

        try:
            return await self.llm.query(
                prompts.DIRECT_RESPONSE_PROMPT, dr_input,
            )
        except Exception as e:
            self.console.print(f"  [red]直答生成失败: {e}[/red]")
            return ""

    # ── 综合研判 ───────────────────────────────────────────

    async def _synthesize(
        self,
        pool: list[SourceEntry],
        verify_data: dict,
        causal_tree: EventNode,
        event_timeline: list[TimelineEvent],
        cred: CredibilityBreakdown,
        direct_response: str,
    ) -> TracingReport:
        self.console.print("  生成详细研判…")

        timeline_text = "\n".join(
            f"- [{e.significance}] {e.date}: {e.title} — {e.description}"
            for e in event_timeline
        )
        pool_summary = "\n".join(
            f"- [{s.outlet}] ({s.source_type}) {s.publish_time}"
            for s in pool
        )
        tree_text = self._tree_to_text(causal_tree)

        synthesis_input = (
            f"=== 事件时间线 ({len(event_timeline)} 个事件) ===\n"
            f"{timeline_text}\n\n"
            f"=== 信源池 ({len(pool)} 个来源) ===\n{pool_summary}\n\n"
            f"=== 交叉验证 ===\n"
            f"一致事实: {verify_data.get('consistent_facts', [])}\n"
            f"分歧事实: {verify_data.get('disputed_facts', [])}\n\n"
            f"=== 因果事件树 ===\n{tree_text}\n\n"
            f"=== 因果锚定 ===\n"
            f"{cred.grounded_count}/{cred.total_causal_nodes}"
        )

        result = await self.llm.query_json(
            prompts.SYNTHESIS_PROMPT, synthesis_input,
        )

        source_timeline = sorted(pool, key=lambda s: s.publish_time or "")

        consistent_facts = [
            FactClaim(
                claim=f.get("claim", f) if isinstance(f, dict) else str(f),
                source_urls=f.get("source_urls", []) if isinstance(f, dict) else [],
                agreed=True,
            )
            for f in verify_data.get("consistent_facts", [])
        ]
        disputed_facts = [
            FactClaim(
                claim=f.get("claim", f) if isinstance(f, dict) else str(f),
                source_urls=f.get("source_urls", []) if isinstance(f, dict) else [],
                agreed=False,
            )
            for f in verify_data.get("disputed_facts", [])
        ]

        return TracingReport(
            event=causal_tree,
            direct_response=direct_response,
            credibility=cred,
            event_timeline=event_timeline,
            sources=pool,
            source_timeline=source_timeline,
            key_findings=result.get("key_findings", []),
            information_gaps=result.get("information_gaps", []),
            consistent_facts=consistent_facts,
            disputed_facts=disputed_facts,
            causal_summary=result.get("causal_summary", ""),
            bias_notes=result.get("bias_notes", []),
        )

    # ══ 辅助 ═══════════════════════════════════════════════

    @staticmethod
    def _tree_to_text(node: EventNode, indent: int = 0) -> str:
        prefix = "  " * indent
        rel = f" [{node.relation}]" if node.relation else ""
        grounded_tag = " [有据]" if node.grounded else ""
        lines = [
            f"{prefix}- {node.title} ({node.date}){rel}{grounded_tag}",
            f"{prefix}  {node.summary}",
        ]
        for child in node.causes:
            lines.append(NewsTracingAgent._tree_to_text(child, indent + 1))
        return "\n".join(lines)
