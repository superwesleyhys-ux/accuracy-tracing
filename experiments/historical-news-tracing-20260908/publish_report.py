"""Publish completed historical news-harness accounting without source prose.

This post-run tool is not part of the inference worker. --verify requires only
this script and the public bundle. Publication requires a new destination.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_PUBLIC = ROOT / "reports/historical-news-tracing-20260908"
ARMS = ("direct", "news_tracing")
VARIANTS = ("original", "blinded")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
FORMAL = {"decompose", "verify", "select"}
RESEARCH = {"deconstruct", "search_plan", "source_trace", "source_verify", "causal_dig",
            "grounding_check", "timeline_build", "perspective", "direct_response", "synthesis"}
LOOPS = ("accepted_revisit_executed", "reanalysis_executed", "verification_feedback_executed",
         "both_loops_executed", "recorded_analysis_changed")
USAGE = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_output_tokens")
PUBLIC_FILES = ("SUMMARY.json", "SANITIZED_RECEIPTS.json", "REGISTRATION.json",
                "PREREGISTRATION_MANIFEST.json", "PROTOCOL.md", "README.md")
PINS = {
    "corpus_sha256": "b5ad5c900145a7a5b208fe8752c1051119d2be18bfa45ececd4d025f6dcf2826",
    "gold_sha256": "b2b10af8b6c3018088ead31a5b0ab91f91f6c6e000903f0cf67c5679b30d328a",
    "helper_sha256": "f5524ee1a92bb5be07d8148477e416d6a11db2ab82cf41ef4ffbf116649e771f",
    "input_review_sha256": "042e22e24598aaed460095cbe89eeeb7e5721a93976ae82f31cbed8e00f02f8d",
    "gold_review_sha256": "5761361f1cbfcd69e3a67b7b4444bb93af2643ebe20bbfc568d8d80a4c71273c",
    "driver_sha256": "e20a8ff17ec1d33fbaec4f44635f50c99b67c223f6884e0d3df4a6d9e9795f09",
    "scorer_sha256": "b6ea4a6183d1502825de4e2cbe7bfd4a097ab2dc7949f9ccfce77e1e8ca3600e",
}
PINNED_PROTOCOL = "4a5516f45192fc37c73b8b62e970f7908ee77a098f55348098de014956fdd021"


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    def reject(_):
        raise ValueError("Nonfinite JSON in publication input")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value):
    return type(value) is int and value >= 0


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def keys(value, expected, message):
    require(isinstance(value, dict) and set(value) == set(expected), message)


def privacy_scan(text):
    require(not re.search(r"/Users/|/private/var/|/var/folders/|/home/|jsessionid|"
                          r'"(?:session_id|thread_id|conversation_id|rationale|quote|prompt|packet|final_output|content)"|'
                          r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                          text, re.I), "Private source, model, path or credential content in publication")


def stats(calls):
    known = [c["usage"] for c in calls if c["usage"] is not None]
    complete = bool(calls) and len(known) == len(calls)
    result = {"attempts": len(calls), "successful_calls": sum(c["success"] for c in calls),
              "known_usage_calls": len(known), "usage_complete": complete}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        result["known_" + field] = sum(c[field] for c in known)
        result[field] = result["known_" + field] if complete else None
    for field in ("cached_input_tokens", "reasoning_output_tokens"):
        values = [c[field] for c in known if c[field] is not None]
        result["known_" + field] = sum(values)
        result["known_" + field + "_calls"] = len(values)
        result[field] = sum(values) if calls and len(values) == len(calls) else None
    return result


def variant_stats(rows):
    result = {}
    for variant in VARIANTS:
        result[variant] = {}
        for arm in ARMS:
            selected = [r for r in rows if (r["variant"], r["condition"]) == (variant, arm)]
            authenticity = [r for r in selected if r["role"] == "authenticity"]
            controls = [r for r in selected if r["role"] == "attribution_control"]
            require(len(selected) == 4 and len(authenticity) == len(controls) == 2, "Variant/role denominator changed")
            result[variant][arm] = {
                "cases": 4, "pipeline_completed": sum(r["pipeline_success"] for r in selected),
                "evidence_valid": sum(r["valid"] for r in selected), "failed_or_invalid": sum(not r["valid"] for r in selected),
                "cutoff_matches": sum(r["cutoff_match"] for r in selected),
                "future_verdict_matches": sum(r["future_verdict_match"] for r in selected),
                "authenticity_cases": 2, "authenticity_abstentions": sum(r["abstained"] for r in authenticity),
                "authenticity_called_false": sum(r["called_later_false_claim_false"] for r in authenticity),
                "authenticity_accepted": sum(r["accepted_later_false_claim"] for r in authenticity),
                "authenticity_conflicts": sum(r["valid"] and r["observed"] == "conflicting" for r in authenticity),
                "authenticity_failed_or_invalid": sum(not r["valid"] for r in authenticity),
                "controls": 2, "control_matches": sum(r["cutoff_match"] for r in controls)}
    return result


def validate_summary(summary, document):
    keys(summary, ("schema_version", "model", "reasoning_effort", "tunnel", "cutoff", "event_families", "cases", "runs",
        "conditions", "scores_by_variant", "rows", "stages", "source_metadata", "exposure", "manifest_sha256",
        "registration_sha256", "corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256", "frozen_input_checks_passed", "scope"), "Unexpected summary fields")
    require((summary["schema_version"], summary["model"], summary["reasoning_effort"], summary["tunnel"], summary["cutoff"],
             summary["event_families"], summary["cases"], summary["runs"])
            == (1, "gpt-6-astra", "medium", "local", "2023-12-31T23:59:59Z", 2, 8, 16), "Experiment scope changed")
    require(summary["frozen_input_checks_passed"] is True, "Scorer did not finish its input audit")
    for field in ("corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256"):
        require(summary[field] == PINS[field], "Scoring commitment changed")
    require(valid_hash(summary["manifest_sha256"]) and valid_hash(summary["registration_sha256"]), "Invalid manifest commitment")
    keys(document, ("receipts",), "Unexpected receipt document fields")
    calls = document["receipts"]
    require(isinstance(calls, list), "Receipts must be a list")
    rows = summary["rows"]
    require(isinstance(rows, list) and len(rows) == 16, "All sixteen outcomes are required")
    expected = {(f"h{n:02d}", arm) for n in range(1, 9) for arm in ARMS}
    require(all(isinstance(row, dict) for row in rows) and len({(r["id"], r["condition"]) for r in rows}) == 16
            and {(r["id"], r["condition"]) for r in rows} == expected, "Outcome denominator changed")
    grouped, stage_groups = defaultdict(list), defaultdict(list)
    receipt_ids = set()
    for call in calls:
        keys(call, ("id", "case_id", "condition", "ordinal", "stage", "model", "reasoning_effort", "tunnel", "success",
            "status", "wall_seconds", "timeout_seconds", "usage", "local_skills_disabled", "input_sha256", "response_sha256", "original_receipt_sha256"), "Unexpected receipt fields")
        pair = (call["case_id"], call["condition"])
        require(pair in expected and integer(call["ordinal"]) and call["ordinal"] > 0, "Unknown receipt identity")
        require(call["id"] == f"{pair[0]}:{pair[1]}:{call['ordinal']:02d}" and call["id"] not in receipt_ids, "Duplicate or mismatched receipt ID")
        receipt_ids.add(call["id"])
        require(call["stage"] in ({"direct"} if pair[1] == "direct" else FORMAL | RESEARCH), "Unknown model stage")
        require((call["model"], call["reasoning_effort"], call["tunnel"]) == ("gpt-6-astra", "medium", "local"), "Mixed model settings")
        require(type(call["success"]) is bool and call["status"] == ("completed" if call["success"] else "failed"), "Invalid receipt status")
        require(finite(call["wall_seconds"]) and finite(call["timeout_seconds"]) and 0 < call["timeout_seconds"] <= 90, "Invalid receipt timing")
        require(integer(call["local_skills_disabled"]) or call["local_skills_disabled"] is None, "Invalid skill-isolation count")
        require(not call["success"] or integer(call["local_skills_disabled"]) and call["local_skills_disabled"] > 0, "Successful call lacks isolation receipt")
        require(valid_hash(call["input_sha256"]) and valid_hash(call["original_receipt_sha256"])
                and (valid_hash(call["response_sha256"]) or call["response_sha256"] is None and not call["success"]), "Invalid artifact commitment")
        usage = call["usage"]
        if usage is not None:
            keys(usage, USAGE, "Unexpected usage fields")
            require(all(integer(usage[k]) for k in USAGE[:3]) and usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"], "Invalid token totals")
            for field, maximum in (("cached_input_tokens", usage["input_tokens"]), ("reasoning_output_tokens", usage["output_tokens"])):
                require(usage[field] is None or integer(usage[field]) and usage[field] <= maximum, "Invalid cached or reasoning token accounting")
        grouped[pair].append(call); stage_groups[call["condition"], call["stage"]].append(call)
    for pair in expected:
        group = sorted(grouped[pair], key=lambda c: c["ordinal"])
        require(len(group) <= (1 if pair[1] == "direct" else 24)
                and [c["ordinal"] for c in group] == list(range(1, len(group) + 1)), "Call budget or ordinal denominator changed")
        grouped[pair] = group
    boolean_fields = ("pipeline_success", "formal_pipeline_success", "citation_integrity", "formal_evidence_valid", "valid",
        "shape_valid", "clock_discrepancy", "cutoff_match", "future_verdict_match", "abstained", "accepted_later_false_claim",
        "called_later_false_claim_false", "unwarranted_settled_cutoff_verdict")
    row_keys = ("id", "condition", "event_family", "role", "variant", "cutoff_expected", "future_expected", "observed", "raw_verdict",
        "error_count", "displayed_provenance_status", "citation_count", "mechanisms", "logical_calls", "usage", "explicit_future_years_in_final_prose", *boolean_fields)
    for row in rows:
        keys(row, row_keys, "Unexpected outcome fields")
        number = int(row["id"][1:])
        require(row["variant"] == ("original" if number in {1, 2, 5, 6} else "blinded")
                and row["role"] == ("authenticity" if number % 2 else "attribution_control")
                and row["event_family"] == ("osaka-dat-2023" if number <= 4 else "hargreaves-metals-2017"), "Registered case metadata differs")
        require((row["cutoff_expected"], row["future_expected"]) == (("unresolved", "contradicted") if number % 2 else ("supported", "supported")), "Registered labels differ")
        require(all(type(row[key]) is bool for key in boolean_fields), "Invalid decision flags")
        require(row["observed"] in VERDICTS | {"execution_failed"} and (row["raw_verdict"] is None or row["raw_verdict"] in VERDICTS), "Invalid categorical outcome")
        require(integer(row["error_count"]) and integer(row["citation_count"]), "Invalid error/citation counts")
        require(row["displayed_provenance_status"] in {None, "unresolved", "partial", "original_material_located"}, "Invalid displayed provenance")
        keys(row["mechanisms"], LOOPS, "Unexpected loop flags")
        require(all(type(v) is bool for v in row["mechanisms"].values()), "Invalid loop execution flags")
        require(row["mechanisms"]["both_loops_executed"] == (row["mechanisms"]["reanalysis_executed"] and row["mechanisms"]["verification_feedback_executed"]), "Both-loop accounting differs")
        require(row["formal_evidence_valid"] == (row["formal_pipeline_success"] and row["citation_integrity"])
                and row["valid"] == (row["pipeline_success"] and row["citation_integrity"]), "Primary/formal validity differs")
        require(not row["pipeline_success"] or row["formal_pipeline_success"] and row["shape_valid"] and row["error_count"] == 0, "Invalid primary completion")
        correct = {
            "cutoff_match": row["valid"] and row["observed"] == row["cutoff_expected"],
            "future_verdict_match": row["valid"] and row["observed"] == row["future_expected"],
            "abstained": row["valid"] and row["observed"] == "unresolved",
            "accepted_later_false_claim": row["valid"] and row["role"] == "authenticity" and row["observed"] == "supported",
            "called_later_false_claim_false": row["valid"] and row["role"] == "authenticity" and row["observed"] == "contradicted",
            "unwarranted_settled_cutoff_verdict": row["valid"] and row["cutoff_expected"] == "unresolved" and row["observed"] != "unresolved"}
        require(all(row[key] == value for key, value in correct.items()), "Outcome scores do not follow primary validity")
        group = grouped[row["id"], row["condition"]]
        require(row["logical_calls"] == len(group) and row["usage"] == stats(group), "Row call or token totals differ")
        require(not row["pipeline_success"] or group and all(c["success"] for c in group), "Failed invocation received success credit")
        require(isinstance(row["explicit_future_years_in_final_prose"], list)
                and all(isinstance(v, str) and re.fullmatch(r"20(?:2[4-9]|[3-9]\d)", v) for v in row["explicit_future_years_in_final_prose"]), "Invalid future-reference screen")
    conditions = {arm: {"cases": 8, "pipeline_completed": sum(r["pipeline_success"] for r in rows if r["condition"] == arm),
        "evidence_valid": sum(r["valid"] for r in rows if r["condition"] == arm),
        "failed_or_invalid": sum(not r["valid"] for r in rows if r["condition"] == arm),
        **stats([c for c in calls if c["condition"] == arm])} for arm in ARMS}
    stages = [{"condition": arm, "stage": stage, "phase": "formal" if stage in FORMAL else "direct" if stage == "direct" else "research",
               **stats(group)} for (arm, stage), group in sorted(stage_groups.items())]
    require(summary["conditions"] == conditions and summary["stages"] == stages
            and summary["scores_by_variant"] == variant_stats(rows), "Published aggregate accounting differs")
    source_ids = defaultdict(set)
    require(isinstance(summary["source_metadata"], list) and len(summary["source_metadata"]) == 16, "Source-version metadata denominator differs")
    for source in summary["source_metadata"]:
        keys(source, ("case_id", "version_id", "canonical_url", "content_sha256", "available_at"), "Unexpected source metadata")
        require(source["case_id"] in {cid for cid, _ in expected} and isinstance(source["version_id"], str)
                and source["version_id"] not in source_ids[source["case_id"]], "Invalid source identity")
        source_ids[source["case_id"]].add(source["version_id"])
        p = urlsplit(source["canonical_url"])
        require(p.scheme in {"http", "https"} and p.hostname and p.username is None and p.password is None and not p.query and not p.fragment,
                "Unsafe source URL")
        require(valid_hash(source["content_sha256"]) and datetime.fromisoformat(source["available_at"].replace("Z", "+00:00"))
                <= datetime.fromisoformat(summary["cutoff"].replace("Z", "+00:00")), "Invalid source hash/availability metadata")
    require(all(len(ids) == 2 for ids in source_ids.values()) and len(source_ids) == 8, "Source versions missing from a case")
    require(isinstance(summary["exposure"], list) and len(summary["exposure"]) == len(calls)
            and {e["receipt_id"] for e in summary["exposure"]} == receipt_ids, "Exposure receipt denominator differs")
    call_map = {c["id"]: c for c in calls}
    for entry in summary["exposure"]:
        keys(entry, ("receipt_id", "full_material_ids", "catalog_preview_ids", "research_excerpts", "canonical_materials_only"), "Unexpected exposure fields")
        allowed = source_ids[call_map[entry["receipt_id"]]["case_id"]]
        require(entry["canonical_materials_only"] is True and all(isinstance(entry[k], list) and set(entry[k]) <= allowed
                for k in ("full_material_ids", "catalog_preview_ids")), "Invalid canonical exposure metadata")
        require(isinstance(entry["research_excerpts"], list), "Invalid research excerpt audit")
        for excerpt in entry["research_excerpts"]:
            keys(excerpt, ("matching_version_ids", "characters", "text_sha256"), "Unexpected excerpt metadata")
            require(isinstance(excerpt["matching_version_ids"], list) and excerpt["matching_version_ids"]
                    and set(excerpt["matching_version_ids"]) <= allowed and integer(excerpt["characters"])
                    and excerpt["characters"] <= 16000 and valid_hash(excerpt["text_sha256"]), "Invalid excerpt commitment")
        require(sum(e["characters"] for e in entry["research_excerpts"]) <= 60000, "Excerpt budget differs")
    required_scope = {"primary_validity_requires_all_research_and_formal_stages_successful": True,
        "formal_validity_is_a_separate_diagnostic": True, "future_gold_parsed_after_all_request_audits": True,
        "model_memory_erased": False, "independent_held_out_accuracy": False, "equal_token_budget": False,
        "source_bytes_or_model_prose_published": False}
    scope_text = {
        "direct_baseline": "Skill-free local Codex Astra receiving the entire canonical pool; not raw model weights.",
        "research_evidence": "Eligible source prefixes up to 16000 characters each and 60000 total; duplicate URLs may collapse to one version.",
        "formal_evidence": "Initial canonical version plus selected eligible snapshots; research prose is not added as evidence.",
        "future_scores": "Abstention is not advance detection; matching later falsehood can be unjustified by cutoff evidence.",
        "usage": "Logical invocations include failures; internal CLI retries are not separately controlled. Cached input is included in input tokens, not added again.",
        "future_screen": "Final rationale/quote year screening only; absence does not establish absence of model memory."}
    keys(summary["scope"], (*required_scope, *scope_text), "Unexpected evaluation scope metadata")
    require(all(summary["scope"][k] is v for k, v in required_scope.items())
            and all(summary["scope"][k] == v for k, v in scope_text.items()), "Evaluation limitations changed")
    privacy_scan(json.dumps(summary, ensure_ascii=False)); privacy_scan(json.dumps(document, ensure_ascii=False))
    return {"cases": 8, "runs": 16, "event_families": 2, "receipts": len(calls),
            "all_calls": {arm: stats([c for c in calls if c["condition"] == arm]) for arm in ARMS},
            "named_calls": {arm: stats([c for c in calls if c["condition"] == arm and c["case_id"] in {"h01", "h02", "h05", "h06"}]) for arm in ARMS}}


def show(value):
    return "unknown" if value is None else f"{value:,}"


def show_tokens(value):
    return show(value["total_tokens"]) if value["total_tokens"] is not None else f"unknown (known ≥ {value['known_total_tokens']:,})"


def notes_checked(notes):
    require(isinstance(notes, list) and len(notes) <= 4 and all(isinstance(n, str) and n.strip() and len(n) <= 800 and "\n" not in n for n in notes),
            "Failure notes must be at most four short, authored paragraphs")
    for note in notes:
        privacy_scan(note)
    return notes


def render_readme(summary, document, notes):
    notes_checked(notes)
    accounting = validate_summary(summary, document)
    rows, calls = summary["rows"], document["receipts"]
    names = {"direct": "Astra alone", "news_tracing": "Astra + updated harness"}
    outcomes = []
    for arm in ARMS:
        value = summary["scores_by_variant"]["original"][arm]
        counts = [f"{value['authenticity_called_false']} called false",
                  f"{value['authenticity_abstentions']} unresolved",
                  f"{value['authenticity_failed_or_invalid']} failed or invalid"]
        if value["authenticity_accepted"]:
            counts.append(f"{value['authenticity_accepted']} accepted")
        if value["authenticity_conflicts"]:
            counts.append(f"{value['authenticity_conflicts']} conflicting")
        outcomes.append(f"**{names[arm]}: {', '.join(counts)}**")
    lines = ["# Historical Astra versus updated news-tracing harness", "",
        "On the two named authenticity cases per arm, " + "; ".join(outcomes) + ". Failed or invalid pipelines receive no abstention or detection credit. Calling a claim false does not establish justified advance fraud detection.", ""]
    direct_usage, harness_usage = (accounting["named_calls"][arm] for arm in ARMS)
    if (direct_usage["usage_complete"] and harness_usage["usage_complete"]
            and direct_usage["total_tokens"] > 0):
        ratio = harness_usage["total_tokens"] / direct_usage["total_tokens"]
        lines += [f"Across all four named cases, including the controls, the harness used **{ratio:.2f}×** the measured input-plus-output tokens: **{harness_usage['total_tokens']:,} versus {direct_usage['total_tokens']:,}**. Every call in both named-case groups has recorded usage. This is a token ratio, not a price ratio.", ""]
    lines += [
        "This fresh run compares the same Astra model on eight fixed historical cases from two event families. Four named cases are the primary analysis; four identity-masked derivatives are a separate sensitivity check. Evidence was available by **2023-12-31**. The held-out 2025 findings were scored only after inference.", "",
        "Both arms use GPT-6 Astra with medium reasoning. **Local means Codex CLI with hosted model inference**, not local model weights. The direct arm receives the entire allowed pool in one call; the updated treatment adds research stages before its formal double loop, with a 24-call shared cap and a ten-call formal cap. This is a new treatment on the old cases, not an exact rerun of the older ten-call double-loop-only harness.", ""]
    for variant, title in (("original", "Named primary cases"), ("blinded", "Masked sensitivity cases")):
        lines += [f"## {title}", "", "Each arm has two authenticity cases and two attribution controls. Authenticity outcomes below partition all two requested cases; failed or invalid runs receive no abstention or detection credit.", "",
            "| Workflow | Valid cutoff matches / 4 | Later-false: called false / 2 | Unresolved / 2 | Accepted / 2 | Conflict / 2 | Failed or invalid / 2 | Control matches / 2 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for arm in ARMS:
            v = summary["scores_by_variant"][variant][arm]
            lines.append(f"| {names[arm]} | {v['cutoff_matches']}/4 | {v['authenticity_called_false']}/2 | {v['authenticity_abstentions']}/2 | {v['authenticity_accepted']}/2 | {v['authenticity_conflicts']}/2 | {v['authenticity_failed_or_invalid']}/2 | {v['control_matches']}/2 |")
        lines.append("")
    lines += ["Calling a later-false authenticity claim false is a match to the eventual outcome, not proof of justified advance fraud detection. The registered cutoff answer for those claims is unresolved. Exact quotation checks do not establish that a quotation supports every part of a conclusion. Abstaining is not detecting fabrication.", "",
        "## Completion and formal-only diagnostic", "",
        "Primary scores require the complete research-and-verification pipeline to succeed. The inner formal check is shown separately; it does not rescue a failed primary run.", "",
        "| Workflow | Whole pipeline completed / 8 | Primary evidence-valid / 8 | Formal-only evidence-valid / 8 | Both loops executed / 8 |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        selected = [r for r in rows if r["condition"] == arm]
        lines.append(f"| {names[arm]} | {sum(r['pipeline_success'] for r in selected)}/8 | {sum(r['valid'] for r in selected)}/8 | {sum(r['formal_evidence_valid'] for r in selected)}/8 | {sum(r['mechanisms']['both_loops_executed'] for r in selected)}/8 |")
    lines += ["", "### Displayed provenance in the updated harness", "",
        "These counts use the active claim status after its observed-link check, not the nested trace's raw origin label. Located provenance remains a model-assisted source-path assessment; it does not authenticate experimental data.", "",
        "| Case set | Original located | Partial | Unresolved | Unavailable |", "| --- | ---: | ---: | ---: | ---: |"]
    for variant, title in (("original", "Named (4)"), ("blinded", "Masked (4)")):
        counts = Counter(r["displayed_provenance_status"] for r in rows if r["condition"] == "news_tracing" and r["variant"] == variant)
        lines.append(f"| {title} | {counts['original_material_located']} | {counts['partial']} | {counts['unresolved']} | {counts[None]} |")
    lines += ["", "## Model calls and tokens", "",
        "Every logical invocation, including research and failed calls, is retained. A total stays unknown if any invocation lacks usage; the known portion is shown as a lower bound. Cached input is already included in input tokens. Tokens are not monetary cost, and the arms are not compute-matched.", "",
        "| Scope | Workflow | Successful / all calls | Usage-known / all calls | Total tokens | Cached input tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: |"]
    for scope, key in (("All 8 cases", "all_calls"), ("Named 4 cases", "named_calls")):
        for arm in ARMS:
            value = accounting[key][arm]
            lines.append(f"| {scope} | {names[arm]} | {value['successful_calls']}/{value['attempts']} | {value['known_usage_calls']}/{value['attempts']} | {show_tokens(value)} | {show(value['cached_input_tokens'])} |")
    lines += ["", "### Phase usage", "", "| Workflow | Phase | Calls | Total tokens | Share of arm tokens |", "| --- | --- | ---: | ---: | ---: |"]
    for arm in ARMS:
        for phase in (("direct",) if arm == "direct" else ("research", "formal")):
            selected = [c for c in calls if c["condition"] == arm and ("formal" if c["stage"] in FORMAL else "direct" if c["stage"] == "direct" else "research") == phase]
            value, arm_total = stats(selected), accounting["all_calls"][arm]["total_tokens"]
            share = f"{100 * value['total_tokens'] / arm_total:.1f}%" if arm_total and value["total_tokens"] is not None else "unknown"
            lines.append(f"| {names[arm]} | {phase} | {value['attempts']} | {show_tokens(value)} | {share} |")
    lines += ["", "### Stage usage", "", "| Workflow | Stage | Calls | Known input | Known output | Total tokens |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for value in summary["stages"]:
        lines.append(f"| {names[value['condition']]} | {value['stage']} | {value['attempts']} | {show(value['known_input_tokens'])} | {show(value['known_output_tokens'])} | {show_tokens(value)} |")
    invalid = sum(not r["valid"] for r in rows)
    lines += ["", "## What still fails", ""]
    lines += [part for note in notes for part in (note, "")] if notes else [f"{invalid} of 16 requested outcomes failed primary validity checks. Specific failure causes require the retained local error audit; no software failure is counted as a successful abstention. The categorical rows preserve every outcome."]
    lines += ["", "## Interpretation and verification", "",
        "The research stages cannot add new raw evidence to the formal verifier in this experiment. Each pool contains a historical paper and an excerpt of that same paper, not independent corroboration. Research receives bounded prefixes and may collapse duplicate URLs; the direct arm receives the full pool. The installed model's prior knowledge is not erased, and masking does not prove temporal isolation of model weights.", "",
        "This is a development comparison on two event families, not a general accuracy estimate. Internal CLI network retries are not independently counted. The separate transport-readiness probe is excluded from these receipts and totals.", "",
        "The public check recomputes outcomes, denominators and token totals from categorical rows and receipts, verifies hashes, and checks the publication boundary. It cannot independently rescore private quotations or reproduce semantic judgments without the retained source packets and raw model outputs.", "",
        "```sh", "python3 experiments/historical-news-tracing-20260908/publish_report.py --verify --public-dir reports/historical-news-tracing-20260908", "```", "",
        "[Registered protocol](PROTOCOL.md) · [Summary and categorical rows](SUMMARY.json) · [Sanitized call receipts](SANITIZED_RECEIPTS.json) · [Registration](REGISTRATION.json) · [Hash manifest](MANIFEST.json)", ""]
    return "\n".join(lines)


def verify(public):
    public = Path(public)
    require(public.is_dir() and {p.name for p in public.iterdir()} == set(PUBLIC_FILES) | {"MANIFEST.json"}
            and all(p.is_file() and not p.is_symlink() for p in public.iterdir()), "Unlisted file or link in public bundle")
    manifest = read(public / "MANIFEST.json")
    keys(manifest, ("schema_version", "case_count", "run_count", "event_family_count", "receipt_count", "publisher_sha256",
        "source_bytes_bundled", "model_prose_bundled", "public_file_sha256", "scoring_commitments", "authored_failure_notes"), "Unexpected public manifest fields")
    require((manifest["schema_version"], manifest["case_count"], manifest["run_count"], manifest["event_family_count"]) == (1, 8, 16, 2)
            and manifest["source_bytes_bundled"] is False and manifest["model_prose_bundled"] is False, "Publication scope differs")
    require(manifest["publisher_sha256"] == digest(__file__), "Publisher source differs from manifest")
    keys(manifest["public_file_sha256"], PUBLIC_FILES, "Public inventory differs")
    for name, expected in manifest["public_file_sha256"].items():
        require(valid_hash(expected) and digest(public / name) == expected, "Public file hash mismatch")
        privacy_scan((public / name).read_text(encoding="utf-8"))
    summary, document = read(public / "SUMMARY.json"), read(public / "SANITIZED_RECEIPTS.json")
    accounting = validate_summary(summary, document)
    registration, prereg = read(public / "REGISTRATION.json"), read(public / "PREREGISTRATION_MANIFEST.json")
    keys(registration, (*PINS, "schema_version", "registered_at"), "Unexpected registration fields")
    keys(prereg, ("registered_at", "files", "unit_tests_passed", "transport_probe_outside_benchmark",
                  "historical_model_calls_before_registration"), "Unexpected preregistration fields")
    keys(prereg["files"], ("PREFLIGHT.json", "PROTOCOL.md", "REGISTRATION.json", "TRANSPORT_PREFLIGHT.json",
        "corpus.json", "driver.py", "gold.json", "gold_review.json", "helper.py", "input_review.json", "scorer.py"), "Unexpected preregistration artifacts")
    require(all(valid_hash(value) for value in prereg["files"].values()) and prereg["unit_tests_passed"] == 222,
            "Invalid preregistration artifact commitments")
    require(registration["schema_version"] == 1 and all(registration[key] == value for key, value in PINS.items()), "Registration commitments differ")
    require(digest(public / "REGISTRATION.json") == summary["registration_sha256"] == prereg["files"]["REGISTRATION.json"], "Registration hash mismatch")
    require(digest(public / "PROTOCOL.md") == prereg["files"]["PROTOCOL.md"] == PINNED_PROTOCOL, "Protocol differs from preregistration")
    require(prereg["registered_at"] == registration["registered_at"] and prereg["historical_model_calls_before_registration"] == 0
            and prereg["transport_probe_outside_benchmark"] is True, "Registration timing/scope differs")
    committed_names = {"corpus_sha256": "corpus.json", "gold_sha256": "gold.json", "helper_sha256": "helper.py",
        "input_review_sha256": "input_review.json", "gold_review_sha256": "gold_review.json", "driver_sha256": "driver.py", "scorer_sha256": "scorer.py"}
    require(all(prereg["files"][name] == PINS[key] for key, name in committed_names.items()), "Preregistration artifact hashes differ")
    commitments = {key: summary[key] for key in ("manifest_sha256", "registration_sha256", "corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256")}
    require(manifest["scoring_commitments"] == commitments and manifest["receipt_count"] == len(document["receipts"]), "Manifest accounting differs")
    require((public / "README.md").read_text(encoding="utf-8") == render_readme(summary, document, manifest["authored_failure_notes"]), "README accounting or authored notes differ")
    privacy_scan(json.dumps(manifest, ensure_ascii=False))
    return {"verified": True, **accounting, "source_bytes_bundled": False, "model_prose_bundled": False, "new_model_calls": 0}


def publish(results=HERE / "results", public=DEFAULT_PUBLIC, failure_notes=None):
    results, public = Path(results), Path(public)
    require(not public.exists(), "Use a fresh public directory; existing reports are never overwritten")
    require((results / "SUMMARY.json").is_file() and (results / "SANITIZED_RECEIPTS.json").is_file(), "Completed scored results are required")
    summary, document = read(results / "SUMMARY.json"), read(results / "SANITIZED_RECEIPTS.json")
    accounting = validate_summary(summary, document)
    inference = read(results / "manifest.json")
    require(inference.get("worker_exit_code") == 0 and inference.get("gold_loaded") is False
            and inference.get("test_stub") is False and all(v is True for v in inference["frozen_integrity"].values()), "Inference did not finish with intact commitments")
    require(digest(results / "manifest.json") == summary["manifest_sha256"] and digest(results / "registration.json") == summary["registration_sha256"], "Scored inference commitments changed")
    prereg = read(HERE / "PREREGISTRATION_MANIFEST.json")
    require(datetime.fromisoformat(prereg["registered_at"]) <= datetime.fromisoformat(inference["started_at"]), "Registration followed inference")
    notes = notes_checked(read(failure_notes) if failure_notes is not None else [])
    copies = {"SUMMARY.json": results / "SUMMARY.json", "SANITIZED_RECEIPTS.json": results / "SANITIZED_RECEIPTS.json",
              "REGISTRATION.json": results / "registration.json", "PREREGISTRATION_MANIFEST.json": HERE / "PREREGISTRATION_MANIFEST.json",
              "PROTOCOL.md": HERE / "private/registered-artifacts/PROTOCOL.md"}
    require(digest(copies["PROTOCOL.md"]) == PINNED_PROTOCOL and digest(copies["REGISTRATION.json"]) == prereg["files"]["REGISTRATION.json"], "Original preregistration changed")
    for path in copies.values():
        privacy_scan(path.read_text(encoding="utf-8"))
    readme = render_readme(summary, document, notes)
    privacy_scan(readme)
    public.mkdir(parents=True, exist_ok=False)
    for name, source in copies.items():
        shutil.copyfile(source, public / name)
    (public / "README.md").write_text(readme, encoding="utf-8")
    manifest = {"schema_version": 1, "case_count": 8, "run_count": 16, "event_family_count": 2,
        "receipt_count": len(document["receipts"]), "publisher_sha256": digest(__file__),
        "source_bytes_bundled": False, "model_prose_bundled": False,
        "public_file_sha256": {name: digest(public / name) for name in PUBLIC_FILES},
        "scoring_commitments": {key: summary[key] for key in ("manifest_sha256", "registration_sha256", "corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256")},
        "authored_failure_notes": notes}
    (public / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return verify(public)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=HERE / "results")
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--failure-notes", type=Path, help="JSON list of short, sanitized findings authored from the local error audit")
    parser.add_argument("--verify", action="store_true", help="Recompute public accounting, privacy and hashes without private archives")
    args = parser.parse_args()
    print(json.dumps(verify(args.public_dir) if args.verify else publish(args.results, args.public_dir, args.failure_notes), indent=2))
