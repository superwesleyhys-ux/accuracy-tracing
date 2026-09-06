"""Budgeted official-API transport and strict dataclass codec; no credentials persisted."""
from __future__ import annotations
from copy import deepcopy
from collections import deque
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


class ResourceBudgetError(RuntimeError):
    code = "budget_exhausted"

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

    def reserve(self, calls, output_tokens=None):
        """Fail before a multi-stage transaction if it cannot finish at full caps."""
        if type(calls) is not int or calls < 0:
            raise ValueError("reservation calls must be a nonnegative integer")
        with self.lock:
            remaining_seconds = self.budget.seconds - (time.monotonic() - self.start)
            remaining_calls = self.budget.calls - self.calls
            remaining_output = self.budget.output_tokens - self.used_output
            required_output = (calls * self.budget.per_call_output_tokens
                               if output_tokens is None else output_tokens)
            if type(required_output) is not int or required_output < 0:
                raise ValueError("reservation output_tokens must be a nonnegative integer")
            if (remaining_seconds <= 0 or remaining_calls < calls
                    or remaining_output < required_output):
                raise ResourceBudgetError("Per-arm resource budget cannot cover staged transaction")

    def call(self, system, user, json_schema=None, json_mode=False, *,
             stage=None, prompt_version=None, max_output_tokens=None):
        # Serialize calls in BOTH arms for deterministic budget reservations.
        with self.lock:
            remaining = self.budget.seconds - (time.monotonic() - self.start)
            requested_cap = (self.budget.per_call_output_tokens
                             if max_output_tokens is None else max_output_tokens)
            if type(requested_cap) is not int or requested_cap < 1:
                raise ValueError("max_output_tokens must be a positive integer")
            cap = min(requested_cap, self.budget.per_call_output_tokens,
                      self.budget.output_tokens - self.used_output)
            if remaining <= 0 or self.calls >= self.budget.calls or cap <= 0:
                raise ResourceBudgetError("Per-arm resource budget exhausted")
            self.calls += 1
            response_mode = ("json_schema" if json_schema else
                             "json_object" if json_mode else "text")
            record = {"sequence": self.calls, "system": system, "user": user,
                      "request_digest": digest([system, user]),
                      "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
                      "user_payload_sha256": hashlib.sha256(user.encode()).hexdigest(),
                      "max_completion_tokens": cap,
                      "requested_model": self.model,
                      "response_mode": response_mode,
                      "output_schema_sha256": (digest(json_schema)
                                                if json_schema else None),
                      "reasoning_effort": self.reasoning_effort}
            if stage is not None:
                record["stage"] = stage
            if prompt_version is not None:
                record["prompt_version"] = prompt_version
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
                record["output_sha256"] = hashlib.sha256(text.encode()).hexdigest()
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
    _REQUEST_FIELDS = {
        "requested_model", "system", "user", "request_digest",
        "system_prompt_sha256", "user_payload_sha256",
        "output_schema_sha256", "response_mode", "max_completion_tokens",
        "reasoning_effort",
    }
    _RESPONSE_FIELDS = {
        "actual_model", "response_id", "output", "output_sha256",
        "usage", "seconds",
    }

    @staticmethod
    def _sha_text(value):
        return hashlib.sha256(value.encode()).hexdigest()

    @classmethod
    def _record_key(cls, record):
        """Validate a current-format cache record and return its exact key."""
        if type(record) is not dict:
            raise ValueError("Cached response record must be an object")
        missing = (cls._REQUEST_FIELDS | cls._RESPONSE_FIELDS) - set(record)
        if missing:
            raise ValueError("Cached response record is missing integrity fields")
        if (type(record["requested_model"]) is not str
                or not record["requested_model"]
                or type(record["actual_model"]) is not str
                or not record["actual_model"]
                or type(record["system"]) is not str
                or type(record["user"]) is not str
                or type(record["output"]) is not str
                or type(record["response_id"]) is not str
                or not record["response_id"]):
            raise ValueError("Cached response record has invalid text fields")
        if record["request_digest"] != digest(
                [record["system"], record["user"]]):
            raise ValueError("Cached request digest failed integrity validation")
        if record["system_prompt_sha256"] != cls._sha_text(record["system"]):
            raise ValueError("Cached system prompt failed integrity validation")
        if record["user_payload_sha256"] != cls._sha_text(record["user"]):
            raise ValueError("Cached user payload failed integrity validation")
        if record["output_sha256"] != cls._sha_text(record["output"]):
            raise ValueError("Cached output failed integrity validation")
        if record["response_mode"] not in {"text", "json_object", "json_schema"}:
            raise ValueError("Cached response mode is invalid")
        schema_hash = record["output_schema_sha256"]
        if ((record["response_mode"] == "json_schema")
                != (type(schema_hash) is str and len(schema_hash) == 64)):
            raise ValueError("Cached schema declaration is inconsistent")
        if (record["response_mode"] != "json_schema"
                and schema_hash is not None):
            raise ValueError("Cached non-schema request declares a schema")
        if (type(record["max_completion_tokens"]) is not int
                or record["max_completion_tokens"] < 1):
            raise ValueError("Cached output cap is invalid")
        reasoning = record["reasoning_effort"]
        if reasoning is not None and (type(reasoning) is not str or not reasoning):
            raise ValueError("Cached reasoning setting is invalid")
        usage = record["usage"]
        if (type(usage) is not dict
                or set(usage) != {"input_tokens", "output_tokens"}
                or any(type(usage[key]) is not int or usage[key] < 0
                       for key in usage)
                or type(record["seconds"]) not in (int, float)
                or record["seconds"] < 0):
            raise ValueError("Cached usage record is invalid")
        return (
            record["requested_model"], record["request_digest"],
            record["system_prompt_sha256"], record["user_payload_sha256"],
            schema_hash, record["response_mode"],
            record["max_completion_tokens"], reasoning,
        )

    @classmethod
    def _request_key(cls, kwargs):
        messages = kwargs.get("messages")
        if (type(messages) is not list or len(messages) != 2
                or any(type(item) is not dict for item in messages)
                or [item.get("role") for item in messages] != ["system", "user"]
                or any(type(item.get("content")) is not str for item in messages)):
            raise ValueError("Replay request must contain one system and one user message")
        response_format = kwargs.get("response_format")
        if response_format is None:
            response_mode, spec = "text", None
        elif (type(response_format) is dict
              and response_format.get("type") == "json_object"
              and set(response_format) == {"type"}):
            response_mode, spec = "json_object", None
        elif (type(response_format) is dict
              and response_format.get("type") == "json_schema"
              and type(response_format.get("json_schema")) is dict
              and type(response_format["json_schema"].get("schema")) is dict):
            response_mode = "json_schema"
            spec = response_format["json_schema"]["schema"]
        else:
            raise ValueError("Replay request has an unsupported response format")
        system, user = (messages[0]["content"], messages[1]["content"])
        cap = kwargs.get("max_completion_tokens")
        reasoning = kwargs.get("reasoning_effort")
        if type(kwargs.get("model")) is not str or not kwargs["model"]:
            raise ValueError("Replay request model is invalid")
        if type(cap) is not int or cap < 1:
            raise ValueError("Replay request output cap is invalid")
        if reasoning is not None and (type(reasoning) is not str or not reasoning):
            raise ValueError("Replay request reasoning setting is invalid")
        return (
            kwargs["model"], digest([system, user]), cls._sha_text(system),
            cls._sha_text(user), digest(spec) if spec is not None else None,
            response_mode, cap, reasoning,
        )

    def __init__(self, records, model, live_transport):
        self.live_transport = live_transport
        self.by_key = {}
        self.by_id = {}
        for record in records:
            if type(record) is not dict or "error_type" in record:
                continue
            # Records explicitly produced for another requested model cannot
            # match this cache. Missing model declarations are old/incomplete
            # records and are safely ignored rather than inferred from a
            # server-side alias.
            if record.get("requested_model") != model:
                continue
            candidate = deepcopy(record)
            key = self._record_key(candidate)
            self.by_key.setdefault(key, []).append(candidate)
            self.by_id[candidate["response_id"]] = candidate
        self.by_key = {key: deque(sorted(values, key=lambda item: item.get("sequence", 0)))
                       for key, values in self.by_key.items()}

    def __call__(self, **kwargs):
        key = self._request_key(kwargs)
        records = self.by_key.get(key)
        if not records: return self.live_transport(**kwargs)
        record = records.popleft()
        # Validate immediately before replay as well as at admission so later
        # mutation of cache internals cannot turn an indexed record into a
        # different response.
        if self._record_key(record) != key:
            raise ValueError("Cached response no longer matches its request")
        return SimpleNamespace(id=record["response_id"], model=record["actual_model"],
            usage=SimpleNamespace(prompt_tokens=record["usage"]["input_tokens"], completion_tokens=record["usage"]["output_tokens"]),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=record["output"], refusal=None))])
