"""Unverified research proposals adapted from the uploaded news-tracing agent.

These models describe generated analysis. Trusted source admission, origin chains
and claim verdicts belong to the harness and are reported separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FactClaim:
    claim: str
    source_urls: list[str] = field(default_factory=list)
    agreed: bool = False
    date_mentioned: str = ""
    model_agreement: str = "unassessed"
    versions: list[dict] = field(default_factory=list)
    verified: bool = False


@dataclass
class EventNode:
    title: str
    date: str
    summary: str
    sources: list[dict] = field(default_factory=list)
    relation: str = ""
    causes: list[EventNode] = field(default_factory=list)
    confidence: float = 0.0
    grounded: bool = False
    node_id: str = ""
    model_grounded: bool = False
    model_is_root: bool = False
    model_grounding_check: dict = field(default_factory=dict)


@dataclass
class SourceEntry:
    outlet: str
    url: str
    publish_time: str
    source_type: str = ""
    is_original: bool = False
    key_facts: list[FactClaim] = field(default_factory=list)
    model_proposed_original: bool = False
    metadata_conflicts: list[dict] = field(default_factory=list)
    fetched_and_verified: bool = False


@dataclass
class TimelineEvent:
    date: str
    title: str
    description: str
    significance: str = "重要"
    sources: list[dict] = field(default_factory=list)
    perspectives: list[dict] = field(default_factory=list)
    verified: bool = False
    causal_links: list[str] = field(default_factory=list)
    event_id: str = ""
    proposed_source_count: int = 0
    unique_source_url_count: int = 0
    divergence_note: str = ""


@dataclass
class CredibilityBreakdown:
    source_count: int = 0
    source_types: list[str] = field(default_factory=list)
    consistent_count: int = 0
    disputed_count: int = 0
    grounding_rate: float = 0.0
    grounded_count: int = 0
    total_causal_nodes: int = 0
    model_grounded_count: int = 0
    counts_are_model_proposals: bool = True


@dataclass
class TracingReport:
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
    errors: list[dict] = field(default_factory=list)
    phase_status: list[dict] = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    parsed_claims: list[str] = field(default_factory=list)
    parsed_event: dict = field(default_factory=dict)
    analysis_is_model_generated: bool = True
    analysis_is_unverified: bool = True
    trust_note: str = (
        "Sources, agreement, timelines and causes are model proposals. Only the "
        "separate harness evidence and origin checks can establish claim verdicts "
        "or accepted provenance. Repetition across sources is not independence."
    )
