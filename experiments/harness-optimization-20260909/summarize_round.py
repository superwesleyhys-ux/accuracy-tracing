"""Score one registered optimization round after its paired inference completes.

Published JSON contains metadata, decisions and receipts, never source text,
model prose or prompts. Future labels are parsed only after every recorded
request and response has passed the admission and binding audit.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import runpy
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = ROOT / "experiments/historical-cutoff-20260908"
HELPER_PATH = ROOT / "experiments/gstack-harness-eval-20260908/summarize_test.py"
HELPERS = runpy.run_path(str(HELPER_PATH))
from newsverify.news_client import url_key
CORPUS_SHA = "b5ad5c900145a7a5b208fe8752c1051119d2be18bfa45ececd4d025f6dcf2826"
GOLD_SHA = "b2b10af8b6c3018088ead31a5b0ab91f91f6c6e000903f0cf67c5679b30d328a"
HELPER_SHA = "f5524ee1a92bb5be07d8148477e416d6a11db2ab82cf41ef4ffbf116649e771f"
CONDITIONS = ("direct", "news_tracing")
VARIANTS = ("original", "blinded")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
FORMAL_STAGES = {"decompose", "verify", "select"}
RESEARCH_STAGES = {"deconstruct", "search_plan", "source_trace", "source_verify", "causal_dig",
                   "grounding_check", "timeline_build", "perspective", "direct_response", "synthesis"}
LOOP_FLAGS = ("accepted_revisit_executed", "reanalysis_executed", "verification_feedback_executed",
              "both_loops_executed", "recorded_analysis_changed")
CLAIM_OMITTED_STAGES = ["causal_dig", "grounding_check", "timeline_build", "perspective", "direct_response"]


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return HELPERS["read"](path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value):
    return type(value) is int and value >= 0


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def normalize_usage(usage):
    if not isinstance(usage, dict) or not all(integer(usage.get(k)) for k in ("input_tokens", "output_tokens")):
        return None
    total = usage["input_tokens"] + usage["output_tokens"]
    if usage.get("total_tokens") is not None and (not integer(usage["total_tokens"]) or usage["total_tokens"] != total):
        return None
    result = {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"], "total_tokens": total}
    for key, bound in (("cached_input_tokens", usage["input_tokens"]), ("reasoning_output_tokens", usage["output_tokens"])):
        value = usage.get(key)
        result[key] = value if integer(value) and value <= bound else None
    return result


def token_stats(calls):
    values = [normalize_usage(call.get("usage")) for call in calls]
    known = [u for u in values if u is not None]
    result = {"attempts": len(calls), "successful_calls": sum(call.get("success") is True for call in calls),
              "known_usage_calls": len(known), "usage_complete": bool(calls) and len(known) == len(calls)}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        result["known_" + key] = sum(u[key] for u in known)
        result[key] = result["known_" + key] if result["usage_complete"] else None
    for key in ("cached_input_tokens", "reasoning_output_tokens"):
        found = [u[key] for u in known if u[key] is not None]
        result["known_" + key] = sum(found)
        result["known_" + key + "_calls"] = len(found)
        result[key] = sum(found) if calls and len(found) == len(calls) else None
    return result


def expected_research_excerpts(case):
    sources = case["materials"]
    limits = [min(16000, len(source["content"])) for source in sources]
    lengths, remaining = [0] * len(sources), 60000
    active = [i for i, limit in enumerate(limits) if limit]
    while active and remaining:
        share, extra = divmod(remaining, len(active))
        for position, index in enumerate(active):
            take = min(limits[index] - lengths[index], share + (position < extra))
            lengths[index] += take
            remaining -= take
        active = [i for i in active if lengths[i] < limits[i]]
    return [{"version_id": source["version_id"], "url": source["url"], "title": source["issuer"],
             "content": source["content"][:length], "content_start": 0, "content_end": length,
             "context_excerpt": length < len(source["content"]),
             "retrieved_at": source["retrieved_at"], "published_at": source["published_at"]}
            for source, length in zip(sources, lengths)]


def expected_research_scope(research_mode, target_text):
    require(research_mode in {"full", "claim"}, "Unknown registered research mode")
    return {"mode": research_mode, "fixed_claim": target_text if research_mode == "claim" else None,
            "intentionally_omitted_stages": list(CLAIM_OMITTED_STAGES) if research_mode == "claim" else [],
            "omitted_stages_are_not_failed_checks": True}


def audit_exposure(packet, case, stage, expected_advice=None, research_mode="full"):
    require(isinstance(packet, dict) and packet.get("historical_target") == case["target"], "Missing or changed historical target")
    fields = {"direct": {"target", "materials"}, "select": {"target", "tasks", "catalog", "research_advice"},
              "decompose": {"target", "material", "context", "research_advice"},
              "verify": {"target", "context", "research_advice"}}
    fields.update({name: {"request", "fetched_evidence", "collection_errors", "evidence_scope"} for name in RESEARCH_STAGES})
    fields["direct_response"] = {"request", "fetched_evidence"}
    require(stage in fields and set(packet) == fields[stage] | {"historical_target"}, "Unexpected fields in actual stage packet")
    pool = {m["version_id"]: m for m in case["materials"]}
    full, previews, excerpts = set(), set(), []
    admitted_excerpt_objects = set()
    expected_excerpts = expected_research_excerpts(case)
    expected_target = case["target"]
    if research_mode == "claim":
        require(stage not in CLAIM_OMITTED_STAGES, "Claim mode invoked an intentionally omitted stage")
    if stage == "synthesis":
        request = json.loads(packet["request"])
        require(isinstance(request, dict) and request.get("research_scope") == expected_research_scope(research_mode, expected_target["text"]),
                "Synthesis request does not disclose the exact registered research scope")
        require(request["research_scope"]["omitted_stages_are_not_failed_checks"] is True,
                "Invalid synthesis scope flag")
    if stage == "direct":
        require(packet.get("target") == expected_target and packet.get("materials") == case["materials"], "Direct baseline did not receive the complete canonical packet")
    if stage in FORMAL_STAGES:
        require(expected_advice is not None and packet["research_advice"] == expected_advice,
                "Formal research advice differs from the retained bounded proposals")
        require(len(json.dumps(expected_advice, ensure_ascii=False)) <= 6000
                and expected_advice.get("trust") == "untrusted_model_proposals_not_evidence"
                and type(packet["research_advice"].get("research_had_errors")) is bool
                and type(packet["research_advice"].get("truncated")) is bool
                and all(cid in pool for cid in expected_advice.get("candidate_version_ids", [])), "Unbounded or unregistered research advice")

    def walk(value):
        if isinstance(value, dict):
            require(not {"cutoff_expected", "future_expected", "gold", "gold_labels"} & set(value), "Future-gold field entered inference")
            if {"version_id", "content"} <= set(value):
                if id(value) not in admitted_excerpt_objects:
                    require(isinstance(value["version_id"], str) and value["version_id"] in pool
                            and value == pool[value["version_id"]], "Unregistered material entered a model request")
                    full.add(value["version_id"])
            elif {"url", "content"} <= set(value):
                require(id(value) in admitted_excerpt_objects, "Unrecognized source object entered model context")
            if "target" in value:
                target = value["target"]
                require(isinstance(target, dict) and set(target) == set(expected_target)
                        and all(target[k] == expected_target[k] for k in ("text", "as_of", "source_version_id"))
                        and target["id"] in {expected_target["id"], expected_target["id"] + ":c1"}, "Formal target changed")
            if "catalog" in value:
                catalog = value["catalog"]
                require(isinstance(catalog, list), "Malformed source catalog")
                seen = set()
                for row in catalog:
                    require(isinstance(row, dict) and isinstance(row.get("version_id"), str)
                            and row["version_id"] in pool and row["version_id"] not in seen, "Unknown or duplicate catalog source")
                    source = pool[row["version_id"]]
                    expected = {k: source[k] for k in ("version_id", "url", "issuer", "published_at", "available_at")}
                    expected["preview"] = source["content"][:800]
                    require(row == expected, "Catalog differs from canonical metadata or preview")
                    seen.add(row["version_id"]); previews.add(row["version_id"])
            if "fetched_evidence" in value:
                evidence = value["fetched_evidence"]
                require(isinstance(evidence, list) and evidence == expected_excerpts,
                        "Research evidence differs from exact all-version fair projection")
                for row in evidence:
                    require(type(row["context_excerpt"]) is bool and type(row["content_start"]) is int
                            and type(row["content_end"]) is int, "Invalid research excerpt metadata types")
                    admitted_excerpt_objects.add(id(row))
                    excerpts.append({"matching_version_ids": [row["version_id"]], "characters": len(row["content"]),
                                     "content_start": row["content_start"], "content_end": row["content_end"],
                                     "text_sha256": hashlib.sha256(row["content"].encode()).hexdigest()})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(packet)
    return {"full_material_ids": sorted(full), "catalog_preview_ids": sorted(previews),
            "research_excerpts": excerpts, "canonical_materials_only": True,
            "untrusted_research_advice_present": stage in FORMAL_STAGES}


def error_list(value):
    return value if isinstance(value, list) else [{"invalid_error_list": True}]


def research_completion_valid(run, research_mode="full", target_text=None):
    """Credit only the registered research scope, with explicit intentional skips."""
    if run.get("condition") == "direct":
        return True
    report = run.get("news_report")
    items = report.get("results", []) if isinstance(report, dict) else []
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return False
    analysis = items[0].get("analysis")
    analysis = analysis.get("report", {}) if isinstance(analysis, dict) else {}
    phases = analysis.get("phase_status") if isinstance(analysis, dict) else None
    if not isinstance(phases, list) or any(not isinstance(p, dict) for p in phases):
        return False
    limits = analysis.get("limits")
    expected_scope = expected_research_scope(research_mode, target_text)
    if (not isinstance(limits, dict) or limits.get("research_mode") != research_mode
            or limits.get("research_scope") != expected_scope
            or limits["research_scope"].get("omitted_stages_are_not_failed_checks") is not True):
        return False
    required = {"deconstruct", "synthesis"}
    if research_mode == "full":
        required.add("direct_response")
    else:
        # Claim mode pins a nonempty explicit claim, so planning cannot take
        # the full-mode "no parsed event or claims" skip path.
        required.add("search_plan")
        for stage in CLAIM_OMITTED_STAGES:
            matches = [p for p in phases if p.get("stage") == stage]
            if len(matches) != 1 or matches[0].get("status") != "skipped":
                return False
        if any(c.get("stage") in CLAIM_OMITTED_STAGES for c in run.get("calls", []) if isinstance(c, dict)):
            return False
    completed = {p.get("stage") for p in phases if p.get("status") == "completed"}
    attempted = {c.get("stage") for c in run.get("calls", []) if isinstance(c, dict) and c.get("success") is True}
    return required <= completed & attempted and not any(p.get("status") == "failed" for p in phases)


def assess_run(run, case):
    """Compute validity without parsing or consulting any answer labels."""
    arm = run["condition"]
    base = dict(run)
    outer_ok, outer_errors = True, error_list(run.get("errors"))
    visible_origin = None
    if arm == "news_tracing":
        report = run.get("news_report")
        items = report.get("results") if isinstance(report, dict) else None
        item = items[0] if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict) else {}
        claims = item.get("claims")
        claim = claims[0] if isinstance(claims, list) and len(claims) == 1 and isinstance(claims[0], dict) else {}
        inner = claim.get("trace")
        visible_origin = claim.get("provenance_status")
        analysis = item.get("analysis", {}).get("report", {}) if isinstance(item.get("analysis"), dict) else {}
        outer_errors = (outer_errors + error_list(item.get("errors")) + error_list(claim.get("errors"))
                        + error_list(analysis.get("errors")) if isinstance(analysis, dict) else [{"invalid_analysis": True}])
        outer_ok = bool(item.get("id") == case["target"]["id"] and claim.get("text") == case["target"]["text"]
                        and item.get("status") == "completed" and not outer_errors
                        and isinstance(report.get("summary"), dict) and report["summary"].get("news_items") == 1
                        and report["summary"].get("claims") == 1 and report["summary"].get("completed") == 1
                        and report["summary"].get("partial") == 0 and report["summary"].get("failed") == 0)
        require(run.get("report") == inner, "Nested formal report differs from row report")
        if claim:
            require(run.get("fact_status") == claim.get("fact_status"), "Row verdict differs from its retained claim")
            if isinstance(inner, dict) and not error_list(claim.get("errors")):
                require(claim.get("fact_status") == inner.get("fact_status"), "Displayed fact verdict differs from successful formal trace")
        base.update(condition="double_loop", report=inner,
                    errors=error_list(claim.get("errors")) + error_list(inner.get("errors")) if isinstance(inner, dict) else [{"missing_trace": True}],
                    calls=[call for call in run["calls"] if call["stage"] in FORMAL_STAGES])
    formal = HELPERS["score_run"](base, case, {"expected_fact_status": "unresolved"})
    complete = bool(formal["pipeline_success"] and outer_ok and not outer_errors
                    and run["calls"] and all(call.get("success") is True for call in run["calls"]))
    final = formal["final_output"]
    raw = final.get("verdict") if isinstance(final, dict) else None
    observed = run.get("fact_status")
    mechanisms = formal.get("mechanisms") or {}
    unique_errors = []
    for error in outer_errors:
        if error not in unique_errors:
            unique_errors.append(error)
    allowed_origins = {"unresolved", "partial", "original_material_located"}
    return {"pipeline_success": complete, "formal_pipeline_success": formal["pipeline_success"],
            "citation_integrity": formal["citations"]["passed"],
            "formal_evidence_valid": bool(formal["pipeline_success"] and formal["citations"]["passed"]),
            "valid": bool(complete and formal["citations"]["passed"]),
            "observed": observed if isinstance(observed, str) and observed in VERDICTS else "execution_failed",
            "raw_verdict": raw if isinstance(raw, str) and raw in VERDICTS else None,
            "error_count": len(unique_errors), "shape_valid": formal["shape_valid"],
            "displayed_provenance_status": visible_origin if isinstance(visible_origin, str) and visible_origin in allowed_origins else None,
            "citation_count": len(formal["citations"]["spans"]),
            "mechanisms": {key: mechanisms.get(key) is True for key in LOOP_FLAGS},
            "clock_discrepancy": formal["clock_discrepancy"], "final_output": final}


def verify_batch(out):
    """Audit every inference byte before future gold is even parsed."""
    out = Path(out)
    manifest, registration = read(out / "manifest.json"), read(out / "registration.json")
    corpus, preflight = read(out / "corpus.json"), read(out / "preflight.json")
    plan, inventory = read(out / "plan.json"), read(out / "code-manifest.json")
    require(isinstance(plan, dict) and set(plan) == {"schema_version", "round_id", "phase", "development_round", "case_ids", "conditions", "max_development_rounds", "research_mode"}, "Invalid plan fields")
    require(type(plan["schema_version"]) is int and plan["schema_version"] == 2
            and type(plan["development_round"]) is int and 1 <= plan["development_round"] <= 3
            and type(plan["max_development_rounds"]) is int and plan["max_development_rounds"] == 3, "Invalid optimization round limit")
    require(plan["research_mode"] in {"full", "claim"}, "Research mode must be explicitly registered")
    expected_ids = ["h01", "h02", "h05", "h06"] if plan["phase"] == "development" else [f"h{i:02d}" for i in range(1, 9)]
    require(plan["phase"] in {"development", "confirmation"} and plan["case_ids"] == expected_ids
            and plan["conditions"] == list(CONDITIONS)
            and plan["round_id"] == (f"round-{plan['development_round']}" if plan["phase"] == "development" else "confirmation"), "Invalid round identity or denominator")
    for key in ("round_id", "phase", "development_round", "case_ids", "research_mode"):
        require(manifest.get(key) == plan[key], "Manifest differs from the registered plan")
    registration_fields = {"corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256", "input_review_sha256", "gold_review_sha256", "driver_sha256", "plan_sha256", "protocol_sha256", "code_manifest_sha256"}
    require(set(registration) == registration_fields | {"schema_version", "registered_at"}
            and type(registration["schema_version"]) is int and registration["schema_version"] == 1
            and all(isinstance(registration[k], str) and re.fullmatch(r"[0-9a-f]{64}", registration[k]) for k in registration_fields), "Invalid registration schema")
    for name, key in (("plan.json", "plan_sha256"), ("protocol.md", "protocol_sha256"), ("code-manifest.json", "code_manifest_sha256")):
        require(sha(out / name) == registration[key] == manifest.get(key), "Round commitment differs")
    predictions = read(out / "stage-artifacts/predictions.json")
    require(manifest.get("worker_exit_code") == 0 and isinstance(manifest.get("frozen_integrity"), dict)
            and manifest["frozen_integrity"] and all(v is True for v in manifest["frozen_integrity"].values()), "Incomplete or changed inference batch")
    require(manifest.get("gold_loaded") is False and predictions.get("gold_loaded") is False
            and manifest.get("test_stub") is False and predictions.get("test_stub") is False, "Gold or stub isolation metadata failed")
    require((manifest.get("model"), manifest.get("reasoning_effort"), manifest.get("tunnel")) == ("gpt-6-astra", "medium", "local"), "Arm settings differ")
    require(sha(out / "corpus.json") == manifest["corpus_sha256"] == preflight["corpus_sha256"] == registration["corpus_sha256"] == CORPUS_SHA, "Corpus commitment differs")
    require(sha(out / "preflight.json") == manifest["review_sha256"] and sha(out / "registration.json") == manifest["registration_sha256"], "Review or registration commitment differs")
    require(all(preflight.get(k) is True for k in ("passed", "cutoff_evidence_reviewed", "claim_dates_reviewed", "future_gold_separated", "variant_transforms_reviewed", "local_transport_ready")), "Preflight gate failed")
    require(registration["gold_sha256"] == GOLD_SHA and registration["helper_sha256"] == sha(HELPER_PATH) == HELPER_SHA
            and registration["scorer_sha256"] == sha(Path(__file__)), "Registered gold/helper/scorer differs")
    for key, name, expected in (
        ("input_review_sha256", "input_review.json", "042e22e24598aaed460095cbe89eeeb7e5721a93976ae82f31cbed8e00f02f8d"),
        ("gold_review_sha256", "gold_review.json", "5761361f1cbfcd69e3a67b7b4444bb93af2643ebe20bbfc568d8d80a4c71273c")):
        require(registration.get(key) == sha(ORIGINAL / "private/registered-artifacts" / name) == expected,
                "Original independent review commitment differs")
    registered = datetime.fromisoformat(registration["registered_at"].replace("Z", "+00:00"))
    started = datetime.fromisoformat(manifest["started_at"].replace("Z", "+00:00"))
    require(registered.utcoffset() is not None and started.utcoffset() is not None
            and registered <= started <= datetime.now(timezone.utc), "Registration occurred after inference or has no timezone")
    frozen = manifest["frozen_code_sha256"]
    require(isinstance(frozen, dict) and bool(frozen), "Missing frozen executable inventory")
    require(set(manifest["frozen_integrity"]) == set(frozen), "Frozen integrity denominator differs")
    for name, expected in frozen.items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts and sha(out / "frozen-inputs" / path) == expected, "Frozen executable differs")
    driver = "experiments/harness-optimization-20260909/run_round.py"
    require(inventory == {"schema_version": 1, "files": frozen}, "Code inventory differs from its frozen archive")
    expected_files = {driver, "experiments/historical-cutoff-20260908/run_test.py", "experiments/double-loop-pilot/run_test.py"}
    expected_files.update(str(path.relative_to(ROOT)) for path in (ROOT / "newsverify").rglob("*.py"))
    require(set(frozen) == expected_files, "Frozen executable inventory omits or adds files")
    require(all(sha(ROOT / name) == expected for name, expected in frozen.items()), "Current scoring imports differ from registered code")
    require(frozen.get(driver) == registration["driver_sha256"], "Driver commitment differs")
    require(sha(ROOT / "newsverify/provenance.py") == frozen.get("newsverify/provenance.py"), "Scoring eligibility implementation changed")
    require(sha(ROOT / "newsverify/news_client.py") == frozen.get("newsverify/news_client.py"), "Scoring URL projection implementation changed")
    require(sha(ORIGINAL / "run_test.py") == frozen.get("experiments/historical-cutoff-20260908/run_test.py"), "Scoring corpus validator changed")
    require(manifest.get("conditions") == list(CONDITIONS) and manifest.get("timeout_seconds_per_call") == 90
            and manifest.get("max_model_calls_per_harness_case") == 24
            and manifest.get("max_model_calls_per_claim_trace") == 10
            and manifest.get("max_logical_calls") == len(expected_ids) * 25
            and manifest.get("case_deadline_seconds") == {"direct": 120, "news_tracing": 2190}, "Registered arm limits differ")
    require(manifest.get("research_excerpt_limits") == {"per_document_characters": 16000, "total_characters": 60000,
            "duplicate_url_policy": "all eligible versions retained; fair allocation across versions; offsets explicit"}, "Research evidence limits differ")
    require(manifest.get("research_advice") == {"maximum_serialized_characters": 6000, "untrusted": True,
            "formal_stages": ["decompose", "select", "verify"], "admitted_as_evidence": False}, "Research advice boundary differs")
    isolation = read(out / "stage-artifacts/isolation.json")
    require(manifest.get("source_network_disabled") is True and isolation == {
        "filesystem_denial_verified": True, "source_network_disabled": True,
        "registration_loaded": False, "gold_loaded": False, "test_stub": False}, "Worker isolation audit differs")
    validator = runpy.run_path(str(ORIGINAL / "run_test.py"))
    validator["validate_corpus"](corpus)
    all_cases = {c["target"]["id"]: c for c in corpus["cases"]}
    require(len(all_cases) == len(corpus["cases"]) == 8, "Frozen corpus denominator differs")
    cases = {cid: all_cases[cid] for cid in expected_ids}
    worker_corpus = {**corpus, "cases": list(cases.values())}
    require(read(out / "worker-corpus.json") == worker_corpus
            and sha(out / "worker-corpus.json") == manifest.get("worker_corpus_sha256"), "Worker corpus differs from exact registered case subset")
    require(manifest["case_count"] == len(cases), "Case denominator differs")
    expected_variants = {"original": 4} if plan["phase"] == "development" else {"original": 4, "blinded": 4}
    require(Counter(c["variant"]["kind"] for c in cases.values()) == expected_variants, "Variant denominator differs")
    payloads = {}
    for cid, case in cases.items():
        target = case["target"]
        payloads[cid] = {"news": [{"id": cid, "text": target["text"], "claims": [target["text"]],
            "materials": case["materials"], "as_of": target["as_of"], "source_version_id": target["source_version_id"]}],
            "config": {"depth": 1, "max_queries": 2, "max_claims": 1, "research_mode": plan["research_mode"],
                "max_documents": case.get("config", {}).get("max_documents", 6), "max_searches": 0,
                "max_origin_depth": 0, "max_origin_calls": 10}}
    expected_payloads = [{"id": cid, "sha256": validator["object_hash"](payload), "config": payload["config"]}
                         for cid, payload in payloads.items()]
    require(manifest.get("news_payloads") == expected_payloads, "Prespecified research configuration or input differs")
    runs = predictions.get("results")
    require(isinstance(runs, list) and len(runs) == len(cases) * 2 and all(isinstance(r, dict) for r in runs), "Missing result rows")
    keys = [(r.get("id"), r.get("condition")) for r in runs]
    expected_keys = [(cid, arm) for index, cid in enumerate(cases)
                     for arm in (CONDITIONS if index % 2 == 0 else tuple(reversed(CONDITIONS)))]
    require(keys == expected_keys, "Missing, duplicate or reordered condition")
    receipts, exposure, prepared = [], [], []
    temporal = manifest["temporal_instruction"]
    require(temporal == validator["TEMPORAL_INSTRUCTION"], "Temporal contract differs")
    for run in runs:
        cid, arm = run["id"], run["condition"]
        case, folder = cases[cid], out / "stage-artifacts" / cid / arm
        require(read(folder / "result.json") == run, "Result sidecar differs")
        calls = run.get("calls")
        require(isinstance(calls, list) and len(calls) <= (1 if arm == "direct" else 24), "Logical invocation cap exceeded")
        require(len(list(folder.glob("*.calls.json"))) == len(calls)
                and len(list(folder.glob("*.input.json"))) == len(calls), "Call sidecar denominator differs")
        news = run.get("news_report")
        items = news.get("results") if isinstance(news, dict) else None
        io = items[0].get("execution", {}).get("model_io", []) if isinstance(items, list) and len(items) == 1 else []
        advice = None
        if arm == "news_tracing" and isinstance(news, dict):
            require(len(io) == len(calls), "News report input denominator differs")
            from newsverify.news_tracing_runner import _research_advice, RESEARCH_ADVICE_RULE
            from newsverify.provenance import MaterialVersion
            advice = _research_advice(items[0].get("analysis", {}).get("report", {}),
                                      [MaterialVersion(**m) for m in case["materials"]])
            require(items[0].get("research_advice") == advice, "Retained advisory differs from research proposals")
            require(sum(call.get("stage") in FORMAL_STAGES for call in calls) <= 10, "Formal call cap exceeded")
        if arm == "news_tracing":
            payload_path = folder / "news-input.json"
            require(payload_path.is_file() or not calls, "Invoked research lacks frozen news input")
            if payload_path.is_file():
                require(read(payload_path) == payloads[cid], "Actual news input differs from its registration")
        last_verified, invalid_research_responses = None, 0
        for n, call in enumerate(calls, 1):
            allowed = {"direct"} if arm == "direct" else FORMAL_STAGES | RESEARCH_STAGES
            require(isinstance(call, dict) and call.get("stage") in allowed and type(call.get("success")) is bool, "Invalid call receipt")
            require(call.get("status") == ("completed" if call["success"] else "failed") and not call.get("test_stub"), "Invalid receipt status")
            require((call.get("model"), call.get("reasoning_effort"), call.get("tunnel")) == ("gpt-6-astra", "medium", "local")
                    and finite(call.get("timeout_seconds")) and 0 < call["timeout_seconds"] <= 90, "Invocation settings differ")
            require(finite(call.get("wall_seconds")), "Invalid invocation timer")
            if call["success"]:
                require(integer(call.get("local_skills_disabled")) and call["local_skills_disabled"] > 0, "Successful local call lacks skill isolation receipt")
            stem = folder / f"{n:02d}-{call['stage']}"
            require(read(stem.with_suffix(".calls.json")) == [call], "Call receipt differs")
            actual = read(stem.with_suffix(".input.json"))
            require(actual["instructions"].startswith(temporal + "\n"), "Actual invocation lacks historical contract")
            admitted = audit_exposure(actual["packet"], case, call["stage"], advice, plan["research_mode"])
            if call["stage"] in FORMAL_STAGES:
                require(RESEARCH_ADVICE_RULE in actual["instructions"], "Formal advice lacks the untrusted boundary instruction")
            path = stem.with_suffix(".response.json")
            require(path.is_file() or not call["success"], "Successful invocation lacks raw response")
            response = read(path) if path.is_file() else None
            if call["stage"] in RESEARCH_STAGES:
                from newsverify.news_tracing.schemas import TEXT_SCHEMA, research_schema, validate_research_output
                from newsverify.tunnels import TunnelError
                expected_schema = TEXT_SCHEMA if call["stage"] == "direct_response" else research_schema(call["stage"], actual["packet"]["request"])
                require(actual["schema"] == expected_schema, "Research invocation differs from its native registered schema")
                if call["success"]:
                    try:
                        validate_research_output(response, expected_schema)
                    except TunnelError:
                        invalid_research_responses += 1
            if arm == "direct" and response is not None:
                require(response == run.get("raw_response"), "Direct result differs from raw response")
            if arm == "news_tracing" and io:
                audit = io[n - 1]
                expected_packet = {**audit["packet"], "historical_target": case["target"]}
                require(actual["packet"] == expected_packet and actual["schema"] == audit["schema"]
                        and actual["instructions"] == temporal + "\n" + audit["instructions"], "News request differs from actual invocation")
                if path.is_file():
                    require(response == audit.get("response"), "News response differs from actual invocation")
            if call["stage"] == "verify" and call["success"]:
                last_verified = response
            rid = f"{cid}:{arm}:{n:02d}"
            receipts.append({"id": rid, "case_id": cid, "condition": arm, "ordinal": n, "stage": call["stage"],
                "model": call["model"], "reasoning_effort": call["reasoning_effort"], "tunnel": call["tunnel"],
                "success": call["success"], "status": call["status"], "wall_seconds": call["wall_seconds"], "timeout_seconds": call["timeout_seconds"],
                "usage": normalize_usage(call.get("usage")), "local_skills_disabled": call.get("local_skills_disabled"),
                "input_sha256": sha(stem.with_suffix(".input.json")), "response_sha256": sha(path) if path.is_file() else None,
                "original_receipt_sha256": sha(stem.with_suffix(".calls.json"))})
            exposure.append({"receipt_id": rid, **admitted})
        score = assess_run(run, case)
        score["invalid_research_responses"] = invalid_research_responses
        score["research_required_phases_completed"] = research_completion_valid(run, plan["research_mode"], case["target"]["text"])
        if invalid_research_responses or not score["research_required_phases_completed"]:
            score["pipeline_success"] = score["valid"] = False
        if arm == "news_tracing" and score["formal_pipeline_success"]:
            final = score["final_output"]
            require(isinstance(last_verified, dict) and all(final[k] == last_verified[k] for k in ("verdict", "rationale")), "Final formal answer differs from raw verifier response")
            require([{k: b[k] for k in ("version_id", "quote")} for b in final["basis"]] == last_verified["basis"], "Final formal citations differ from raw verifier response")
        prepared.append((run, score))
    return manifest, registration, cases, prepared, receipts, exposure


def label_score(run, score, label):
    score = dict(score)
    final = score.pop("final_output")
    prose = " ".join([final.get("rationale", "")] + [b["quote"] for b in final.get("basis", [])]) if isinstance(final, dict) and HELPERS["output_shape_valid"](final, "direct" if run["condition"] == "direct" else "double_loop") else ""
    return {"id": run["id"], "condition": run["condition"], "event_family": label["event_family"],
        "role": label["role"], "variant": label["variant"], "cutoff_expected": label["cutoff_expected"],
        "future_expected": label["future_expected"], **score,
        "cutoff_match": bool(score["valid"] and score["observed"] == label["cutoff_expected"]),
        "formal_cutoff_match": bool(score["formal_evidence_valid"] and score["observed"] == label["cutoff_expected"]),
        "formal_future_verdict_match": bool(score["formal_evidence_valid"] and score["observed"] == label["future_expected"]),
        "formal_abstained": bool(score["formal_evidence_valid"] and score["observed"] == "unresolved"),
        "future_verdict_match": bool(score["valid"] and score["observed"] == label["future_expected"]),
        "abstained": bool(score["valid"] and score["observed"] == "unresolved"),
        "accepted_later_false_claim": bool(score["valid"] and label["role"] == "authenticity" and score["observed"] == "supported"),
        "called_later_false_claim_false": bool(score["valid"] and label["role"] == "authenticity" and score["observed"] == "contradicted"),
        "unwarranted_settled_cutoff_verdict": bool(score["valid"] and label["cutoff_expected"] == "unresolved" and score["observed"] != "unresolved"),
        "logical_calls": len(run["calls"]), "usage": token_stats(run["calls"]),
        "explicit_future_years_in_final_prose": sorted(set(re.findall(r"\b20(?:2[4-9]|[3-9]\d)\b", prose)))}


def aggregate(rows):
    by_variant = {}
    for variant in VARIANTS:
        if not any(r["variant"] == variant for r in rows):
            continue
        by_variant[variant] = {}
        for arm in CONDITIONS:
            selected = [r for r in rows if r["variant"] == variant and r["condition"] == arm]
            authenticity = [r for r in selected if r["role"] == "authenticity"]
            controls = [r for r in selected if r["role"] == "attribution_control"]
            require(len(selected) == 4 and len(authenticity) == len(controls) == 2, "Role or variant denominator differs")
            by_variant[variant][arm] = {
                "cases": 4, "pipeline_completed": sum(r["pipeline_success"] for r in selected),
                "evidence_valid": sum(r["valid"] for r in selected), "failed_or_invalid": sum(not r["valid"] for r in selected),
                "cutoff_matches": sum(r["cutoff_match"] for r in selected),
                "formal_evidence_valid": sum(r["formal_evidence_valid"] for r in selected),
                "formal_cutoff_matches": sum(r["formal_cutoff_match"] for r in selected),
                "unwarranted_settled_cutoff_verdicts": sum(r["unwarranted_settled_cutoff_verdict"] for r in selected),
                "future_verdict_matches": sum(r["future_verdict_match"] for r in selected),
                "authenticity_cases": 2, "authenticity_abstentions": sum(r["abstained"] for r in authenticity),
                "authenticity_called_false": sum(r["called_later_false_claim_false"] for r in authenticity),
                "authenticity_accepted": sum(r["accepted_later_false_claim"] for r in authenticity),
                "authenticity_conflicts": sum(r["valid"] and r["observed"] == "conflicting" for r in authenticity),
                "authenticity_failed_or_invalid": sum(not r["valid"] for r in authenticity),
                "controls": 2, "control_matches": sum(r["cutoff_match"] for r in controls)}
    return by_variant


def safe_url(url):
    p = urlsplit(url)
    require(p.scheme in {"http", "https"} and p.hostname and p.username is None and p.password is None, "Unsafe source metadata URL")
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def summarize(out, gold_path=ORIGINAL / "private/gold.json"):
    out, gold_path = Path(out), Path(gold_path)
    manifest, registration, cases, prepared, receipts, exposure = verify_batch(out)
    # No future label bytes are parsed until every actual model request passed.
    require(sha(gold_path) == registration["gold_sha256"] == GOLD_SHA, "Prespecified gold differs")
    gold = read(gold_path)
    labels = {row["id"]: row for row in gold["cases"]}
    require(len(labels) == len(gold["cases"]) == 8 and set(labels) == {f"h{i:02d}" for i in range(1, 9)} and set(cases) <= set(labels) and gold["event_families"] == 2, "Gold denominator differs")
    rows = []
    for run, score in prepared:
        label = labels[run["id"]]
        require(label["variant"] == cases[run["id"]]["variant"]["kind"] and label["role"] in {"authenticity", "attribution_control"}
                and label["cutoff_expected"] in VERDICTS and label["future_expected"] in VERDICTS, "Invalid registered label metadata")
        rows.append(label_score(run, score, label))
    stages = defaultdict(list)
    for receipt in receipts:
        stages[receipt["condition"], receipt["stage"]].append(receipt)
    conditions = {arm: {"cases": len(cases), "pipeline_completed": sum(r["pipeline_success"] for r in rows if r["condition"] == arm),
        "evidence_valid": sum(r["valid"] for r in rows if r["condition"] == arm),
        "failed_or_invalid": sum(not r["valid"] for r in rows if r["condition"] == arm),
        **token_stats([c for c in receipts if c["condition"] == arm])} for arm in CONDITIONS}
    sources = [{"case_id": cid, "version_id": m["version_id"], "canonical_url": safe_url(m["url"]),
                "content_sha256": hashlib.sha256(m["content"].encode()).hexdigest(), "available_at": m["available_at"]}
               for cid, case in cases.items() for m in case["materials"]]
    summary = {"schema_version": 1, "model": "gpt-6-astra", "reasoning_effort": "medium", "tunnel": "local",
        "cutoff": gold["evidence_cutoff"], "event_families": 2, "cases": len(cases), "runs": len(rows),
        "round_id": manifest["round_id"], "phase": manifest["phase"], "development_round": manifest["development_round"],
        "research_mode": manifest["research_mode"],
        "plan_sha256": manifest["plan_sha256"], "protocol_sha256": manifest["protocol_sha256"],
        "code_manifest_sha256": manifest["code_manifest_sha256"], "worker_corpus_sha256": manifest["worker_corpus_sha256"],
        "conditions": conditions, "scores_by_variant": aggregate(rows), "rows": rows,
        "stages": [{"condition": arm, "stage": stage, "phase": "formal" if stage in FORMAL_STAGES else "direct" if stage == "direct" else "research",
                    **token_stats(calls)} for (arm, stage), calls in sorted(stages.items())],
        "source_metadata": sources, "exposure": exposure,
        "manifest_sha256": sha(out / "manifest.json"), "registration_sha256": sha(out / "registration.json"),
        "corpus_sha256": CORPUS_SHA, "gold_sha256": GOLD_SHA, "scorer_sha256": sha(Path(__file__)), "helper_sha256": HELPER_SHA,
        "frozen_input_checks_passed": True,
        "scope": {"primary_validity_requires_all_research_and_formal_stages_successful": True,
            "formal_validity_is_a_separate_diagnostic": True, "future_gold_parsed_after_all_request_audits": True,
            "model_memory_erased": False, "independent_held_out_accuracy": False, "development_cases_previously_observed": True, "confirmation_is_same_family_sensitivity_not_external_validation": True, "equal_token_budget": False,
            "source_bytes_or_model_prose_published": False,
            "direct_baseline": "Skill-free local Codex Astra receiving the entire canonical pool; not raw model weights.",
            "research_evidence": "Every eligible source version remains visible with exact prefix offsets; fair allocation up to 16000 characters each and 60000 total. Same-URL versions are not independent evidence.",
            "formal_evidence": "Initial canonical version plus selected eligible snapshots. Bounded research advice is visible as untrusted proposals; it cannot admit evidence or resolve gaps.",
            "future_scores": "Abstention is not advance detection; matching later falsehood can be unjustified by cutoff evidence.",
            "usage": "Logical invocations include failures; internal CLI retries are not separately controlled. Cached input is included in input tokens, not added again.",
            "future_screen": "Final rationale/quote year screening only; absence does not establish absence of model memory."}}
    documents = {"SUMMARY.json": summary, "SANITIZED_RECEIPTS.json": {"receipts": receipts}}
    for name, value in documents.items():
        serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        require(not re.search(r"/Users/|/private/var/|/home/|jsessionid|\"(?:session_id|thread_id|rationale|quote|prompt|packet|final_output)\"", serialized, re.I), "Private/source/model content entered public artifacts")
        (out / name).write_text(serialized, encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--gold", type=Path, default=ORIGINAL / "private/gold.json")
    args = parser.parse_args()
    summarize(args.results, args.gold)
