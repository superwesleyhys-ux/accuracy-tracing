from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FactClaim:
    """一条事实声明，附带来源 URL 和多源一致性标记。"""

    claim: str
    source_urls: list[str] = field(default_factory=list)
    agreed: bool = True


@dataclass
class EventNode:
    """因果事件树的节点。通过 causes 递归引用前因事件。"""

    title: str
    date: str
    summary: str
    sources: list[dict] = field(default_factory=list)  # [{"url": ..., "title": ...}]
    relation: str = ""
    causes: list[EventNode] = field(default_factory=list)
    confidence: float = 0.0
    grounded: bool = False


@dataclass
class SourceEntry:
    """信源池中的一条记录。"""

    outlet: str
    url: str
    publish_time: str
    source_type: str = ""  # 通讯社 / 官方媒体 / 门户网站 / 自媒体 / ...
    is_original: bool = False
    key_facts: list[FactClaim] = field(default_factory=list)


@dataclass
class TimelineEvent:
    """事件时间线上的一个节点，代表一件实际发生的事。"""

    date: str
    title: str
    description: str
    significance: str = "重要"  # "重大" / "重要" / "背景"
    sources: list[dict] = field(default_factory=list)  # [{"url": ..., "title": ...}]
    perspectives: list[dict] = field(default_factory=list)  # [{"source": ..., "framing": ...}]
    verified: bool = False  # 至少 2 个来源佐证
    causal_links: list[str] = field(default_factory=list)  # 指向其他事件 title


@dataclass
class CredibilityBreakdown:
    """透明的多维度可信度指标，取代单一评分。"""

    source_count: int = 0
    source_types: list[str] = field(default_factory=list)
    consistent_count: int = 0
    disputed_count: int = 0
    grounding_rate: float = 0.0
    grounded_count: int = 0
    total_causal_nodes: int = 0


@dataclass
class TracingReport:
    """最终溯源报告，以直答为核心，时间线和因果树为补充。"""

    event: EventNode
    direct_response: str = ""
    credibility: CredibilityBreakdown = field(default_factory=CredibilityBreakdown)
    event_timeline: list[TimelineEvent] = field(default_factory=list)
    sources: list[SourceEntry] = field(default_factory=list)
    source_timeline: list[SourceEntry] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    information_gaps: list[str] = field(default_factory=list)
    consistent_facts: list[FactClaim] = field(default_factory=list)
    disputed_facts: list[FactClaim] = field(default_factory=list)
    causal_summary: str = ""
    bias_notes: list[str] = field(default_factory=list)
