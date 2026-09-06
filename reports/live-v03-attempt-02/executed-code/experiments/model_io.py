"""Budgeted official-API transport and strict dataclass codec; no credentials persisted."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import types
from typing import Union, get_args, get_origin, get_type_hints
from types import SimpleNamespace

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

def schema(kind):
    origin, args = get_origin(kind), get_args(kind)
    if origin in (Union, types.UnionType):
        return {"anyOf": [schema(x) for x in args]}
    if origin in (tuple, list):
        return {"type": "array", "items": schema(args[0])}
    if is_dataclass(kind):
        hints = get_type_hints(kind)
        properties = {f.name: schema(hints[f.name]) for f in fields(kind)}
        enums = {
            "Relation": {"kind": ["quotes", "cites", "reprints", "translates", "derives", "supports", "contradicts"],
                         "status": ["direct", "declared", "inferred", "unresolved", "excluded"]},
            "OriginFinding": {"material_kind": ["original_record", "original_interview", "original_dataset", "original_observation"]},
            "Gap": {"stage": ["provenance", "verification"],
                    "dimension": ["provenance", "evidence", "world"],
                    "action": ["fetch", "search", "reanalyse"]},
            "VerificationResult": {"verdict": ["supported", "contradicted", "conflicting", "unresolved"]},
        }
        for name, values in enums.get(kind.__name__, {}).items():
            properties[name]["enum"] = values
        if kind.__name__ == "VerificationResult":
            properties["gaps"]["items"]["properties"]["stage"]["enum"] = ["verification"]
            properties["gaps"]["items"]["properties"]["dimension"]["enum"] = ["evidence", "world"]
            for field in ("evidence_verdict", "world_verdict"):
                properties[field] = {"type": "string", "enum": ["supported", "contradicted", "conflicting", "unresolved"]}
        return {"type": "object", "properties": properties,
                "required": [f.name for f in fields(kind)], "additionalProperties": False}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}[kind]}

def decode(kind, raw):
    origin, args = get_origin(kind), get_args(kind)
    if origin in (Union, types.UnionType):
        if raw is None and type(None) in args: return None
        return decode(next(x for x in args if x is not type(None)), raw)
    if origin in (tuple, list):
        if not isinstance(raw, list): raise ValueError("Expected JSON array")
        return tuple(decode(args[0], x) for x in raw)
    if is_dataclass(kind):
        if not isinstance(raw, dict): raise ValueError("Expected JSON object")
        hints = get_type_hints(kind)
        if set(raw) != {f.name for f in fields(kind)}: raise ValueError("Unexpected/missing dataclass fields")
        return kind(**{f.name: decode(hints[f.name], raw[f.name]) for f in fields(kind)})
    if kind is float:
        if type(raw) not in (float, int): raise ValueError("Expected number")
    elif type(raw) is not kind: raise ValueError(f"Expected {kind.__name__}")
    return raw

@dataclass(frozen=True)
class Budget:
    calls: int = 24
    output_tokens: int = 24000
    per_call_output_tokens: int = 2000
    seconds: float = 300

class BudgetClient:
    """One independent per-arm budget; SDK retries disabled, exact server usage logged.

    Output token caps and call caps are enforced. Input tokens are measured, not
    capped. A timeout/error marks the arm invalid; it is never dropped in scoring.
    """
    def __init__(self, model, budget, transport=None, reasoning_effort=None):
        self.model, self.budget, self.reasoning_effort = model, budget, reasoning_effort
        self.start = time.monotonic()
        self.records = []
        self.lock = threading.Lock()
        self.used_output = self.used_input = self.calls = 0
        if transport is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is not configured; no model calls were made")
            from openai import OpenAI
            transport = OpenAI(max_retries=0, base_url="https://api.openai.com/v1").chat.completions.create
        self.transport = transport

    def call(self, system, user, json_schema=None, json_mode=False):
        # Serialize calls in BOTH arms for deterministic budget reservations.
        with self.lock:
            remaining = self.budget.seconds - (time.monotonic() - self.start)
            cap = min(self.budget.per_call_output_tokens, self.budget.output_tokens - self.used_output)
            if remaining <= 0 or self.calls >= self.budget.calls or cap <= 0:
                raise RuntimeError("Per-arm resource budget exhausted")
            self.calls += 1
            record = {"sequence": self.calls, "system": system, "user": user,
                      "request_digest": digest([system, user]), "max_completion_tokens": cap}
            if json_schema: record["output_schema_sha256"] = digest(json_schema)
            self.records.append(record)
            kwargs = dict(model=self.model, messages=[{"role": "system", "content": system},
                           {"role": "user", "content": user}], max_completion_tokens=cap, timeout=remaining)
            if self.reasoning_effort: kwargs["reasoning_effort"] = self.reasoning_effort
            if json_schema:
                kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "result", "strict": True, "schema": json_schema}}
            elif json_mode: kwargs["response_format"] = {"type": "json_object"}
            started = time.monotonic()
            try:
                response = self.transport(**kwargs)
                record["seconds"] = time.monotonic() - started
                record["response_id"] = response.id
                record["actual_model"] = response.model
                usage = response.usage
                if usage is None: raise RuntimeError("Missing actual token usage")
                self.used_input += usage.prompt_tokens
                self.used_output += usage.completion_tokens
                record["usage"] = {"input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens}
                message = response.choices[0].message
                text = message.content or ""
                record["output"] = text
                if getattr(message, "refusal", None): raise RuntimeError("Model declined this request")
                if response.choices[0].finish_reason != "stop": raise RuntimeError("Incomplete model output")
                if self.used_output > self.budget.output_tokens or time.monotonic() - self.start > self.budget.seconds:
                    raise RuntimeError("Observed resource budget exceeded")
                return json.loads(text) if json_schema or json_mode else text
            except Exception as exc:
                # Do not copy arbitrary remote errors or secrets into logs.
                record["error_type"] = type(exc).__name__
                raise RuntimeError("Model call failed: " + type(exc).__name__) from None

    def usage(self):
        return {"model_calls": self.calls, "input_tokens": self.used_input,
                "output_tokens": self.used_output, "seconds": time.monotonic() - self.start}

def align_spans(raw, materials):
    """Resolve a verbatim quote only if its occurrence is unique; never edit it."""
    raw = deepcopy(raw)
    content = {m["version_id"]: m["content"] for m in materials}
    def walk(value):
        if isinstance(value, list):
            for x in value: walk(x)
        elif isinstance(value, dict):
            if set(value) == {"version_id", "start", "end", "quote"}:
                text = content.get(value["version_id"], "")
                quote = value["quote"]
                start, end = value["start"], value["end"]
                if type(start) is int and type(end) is int and 0 <= start < end <= len(text) and text[start:end] == quote:
                    return
                if not quote or text.count(quote) != 1:
                    raise ValueError("Quote missing or ambiguous; offsets cannot be repaired")
                start = text.index(quote)
                value.update(start=start, end=start + len(quote))
            else:
                for x in value.values(): walk(x)
    walk(raw)
    return raw


class PriorResponseCache:
    """Reuse only identical requests from this same case/variant's prior real run.

    Responses retain original API IDs and usage. This is explicit response replay,
    never a synthetic substitute, and callers must charge the historical usage.
    """
    def __init__(self, records, model, live_transport):
        self.live_transport = live_transport
        self.by_key = {}
        self.by_id = {}
        for record in records:
            if ("error_type" in record or record.get("actual_model") != model
                    or not all(k in record for k in ["response_id", "output", "usage", "seconds"])):
                continue
            key = (model, record["request_digest"], record.get("output_schema_sha256"), record["max_completion_tokens"])
            self.by_key.setdefault(key, record)
            self.by_id[record["response_id"]] = record

    def __call__(self, **kwargs):
        messages = kwargs["messages"]
        spec = kwargs.get("response_format", {}).get("json_schema", {}).get("schema")
        key = (kwargs["model"], digest([messages[0]["content"], messages[1]["content"]]),
               digest(spec) if spec else None, kwargs["max_completion_tokens"])
        record = self.by_key.get(key)
        if record is None: return self.live_transport(**kwargs)
        return SimpleNamespace(id=record["response_id"], model=record["actual_model"],
            usage=SimpleNamespace(prompt_tokens=record["usage"]["input_tokens"], completion_tokens=record["usage"]["output_tokens"]),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=record["output"], refusal=None))])
