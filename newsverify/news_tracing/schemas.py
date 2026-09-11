"""Strict research output contracts, also checked after the transport returns.

Every stage returns its JSON object directly. A string containing JSON is not a
compatible transport response: its interior cannot be constrained by a schema.
These schemas describe unverified proposals, never trusted evidence or verdicts.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math

from ..model_runner import _object
from ..tunnels import TunnelError


def _text(limit=6000):
    return {"type": "string", "maxLength": limit}


def _items(item, limit):
    return {"type": "array", "items": item, "maxItems": limit}


def _strings(limit, text_limit=6000):
    return _items(_text(text_limit), limit)


_BOOL = {"type": "boolean"}
_REF = _object(url=_text(2000), title=_text(2000))
_FACT = _object(claim=_text(), date_mentioned=_text(200))
_AGREEMENT = _object(claim=_text(), source_urls=_strings(15, 2000))
_DISPUTE = _object(claim=_text(), source_urls=_strings(15, 2000),
                   versions=_items(_object(source=_text(), statement=_text()), 10))

RESEARCH_SCHEMAS = {
    "deconstruct": _object(
        core_event=_text(), date=_text(200),
        entities=_object(people=_strings(20), organizations=_strings(20), locations=_strings(20)),
        key_claims=_strings(3), causal_hints=_strings(6)),
    "search_plan": _object(queries=_items(_object(angle=_text(200), query=_text(1000)), 3)),
    "source_trace": _object(sources=_items(_object(
        outlet=_text(500), source_type=_text(500), url=_text(2000),
        publish_time=_text(500), is_original=_BOOL, facts=_items(_FACT, 12)), 5)),
    "source_verify": _object(
        consistent_facts=_items(_AGREEMENT, 30), disputed_facts=_items(_DISPUTE, 30),
        credibility_note=_text()),
    "causal_dig": _object(causes=_items(_object(
        title=_text(), date=_text(200), summary=_text(), relation=_text(),
        sources=_items(_REF, 10), confidence={"type": "number", "minimum": 0, "maximum": 1},
        grounded=_BOOL, is_root=_BOOL), 2)),
    "grounding_check": _object(checks=_items(_object(
        node_id=_text(100), event_title=_text(), grounded=_BOOL,
        matching_urls=_strings(15, 2000), note=_text()), 8)),
    "timeline_build": _object(events=_items(_object(
        date=_text(200), title=_text(), description=_text(),
        significance={"type": "string", "enum": ["重大", "重要", "背景"]},
        sources=_items(_REF, 10), causal_links=_strings(10),
        source_count={"type": "integer", "minimum": 0, "maximum": 10}), 20)),
    "perspective": _object(perspectives=_items(_object(
        event_id=_text(100), event_title=_text(),
        views=_items(_object(source=_text(), framing=_text()), 4), divergence_note=_text()), 20)),
    "synthesis": _object(key_findings=_strings(20), information_gaps=_strings(20),
                          causal_summary=_text(12000), bias_notes=_strings(20)),
}
TEXT_SCHEMA = _object(text=_text(12000))


def research_schema(stage, user):
    """Return a private schema copy, honoring smaller per-request loop bounds."""
    if stage not in RESEARCH_SCHEMAS:
        raise TunnelError("No structured output contract is registered for this research stage.")
    schema = deepcopy(RESEARCH_SCHEMAS[stage])
    try:
        request = json.loads(user)
    except (TypeError, ValueError):
        request = {}
    if isinstance(request, dict):
        field, bound = {"search_plan": ("queries", "max_queries"),
                        "causal_dig": ("causes", "max_causes")}.get(stage, (None, None))
        if field and type(request.get(bound)) is int and request[bound] >= 0:
            array = schema["properties"][field]
            array["maxItems"] = min(array["maxItems"], request[bound])
    return schema


def validate_research_output(value, schema, path="response"):
    """Reject invalid nested values without coercion, truncation or repair.

    Error messages contain only schema paths and syntax facts, not model/source
    text. The transport retains the untouched raw response for diagnosis.
    """
    def fail(reason):
        raise TunnelError(f"Invalid structured research output at {path}: {reason}.")

    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict):
            fail("expected object")
        if set(value) != set(schema["properties"]):
            fail("fields do not match the required object fields")
        for key, child in schema["properties"].items():
            validate_research_output(value[key], child, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list):
            fail("expected array")
        if len(value) > schema["maxItems"]:
            fail("array exceeds the item limit")
        for index, item in enumerate(value):
            validate_research_output(item, schema["items"], f"{path}[{index}]")
    elif kind == "string":
        if not isinstance(value, str):
            fail("expected string")
        if len(value) > schema.get("maxLength", len(value)):
            fail("string exceeds the character limit")
        if "enum" in schema and value not in schema["enum"]:
            fail("string is outside the allowed values")
    elif kind == "boolean":
        if type(value) is not bool:
            fail("expected boolean")
    elif kind in {"integer", "number"}:
        allowed = (int,) if kind == "integer" else (int, float)
        if type(value) not in allowed or (type(value) is float and not math.isfinite(value)):
            fail(f"expected finite {kind}")
        if not schema["minimum"] <= value <= schema["maximum"]:
            fail("number is outside the allowed range")
    else:
        raise ValueError("Unsupported research schema type")
