"""Publish a source-free DEV comparison from completed, audited round summaries.

This script reads SUMMARY.json only. It never opens model responses, prompts,
source packets or private gold. Run it after scoring, with every completed round.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_OUTPUT = ROOT / "reports/harness-optimization-20260909/README.md"
SCREENING_PATH = ROOT / "experiments/tracing-evaluation-design-20260908/SCREENING_TOTALS.json"
SCREENING_SHA256 = "821d40397ef1171a59070511a409f233d6e3447b07272d0626521c743557ba62"
ARMS = ("direct", "news_tracing")
ARM_NAMES = {"direct": "Astra alone", "news_tracing": "Harness"}
SET_NAMES = {"original": "Named DEV", "blinded": "Masked sensitivity"}
FORMAL = {"decompose", "select", "verify"}
RESEARCH = {"deconstruct", "search_plan", "source_trace", "source_verify", "causal_dig",
            "grounding_check", "timeline_build", "perspective", "direct_response", "synthesis"}
HASH_KEYS = ("registration_sha256", "plan_sha256", "protocol_sha256", "code_manifest_sha256",
             "corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved", "execution_failed"}


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def validate_usage(value):
    require(isinstance(value, dict), "Missing usage metadata")
    for key in ("attempts", "successful_calls", "known_usage_calls", "known_input_tokens", "known_output_tokens", "known_total_tokens"):
        require(integer(value.get(key)), "Invalid usage count")
    require(value["successful_calls"] <= value["attempts"] and value["known_usage_calls"] <= value["attempts"], "Usage denominator differs")
    complete = value["attempts"] > 0 and value["known_usage_calls"] == value["attempts"]
    require(type(value.get("usage_complete")) is bool and value["usage_complete"] == complete, "Usage completeness differs")
    require(value["known_total_tokens"] == value["known_input_tokens"] + value["known_output_tokens"], "Known token total differs")
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        require(value.get(key) == (value["known_" + key] if complete else None), "Unknown usage was converted to an exact total")
    for key in ("cached_input_tokens", "reasoning_output_tokens"):
        require(integer(value.get("known_" + key)) and integer(value.get("known_" + key + "_calls"))
                and value["known_" + key + "_calls"] <= value["known_usage_calls"], "Invalid optional token metadata")
        expected = value["known_" + key] if value["attempts"] and value["known_" + key + "_calls"] == value["attempts"] else None
        require(value.get(key) == expected, "Optional token completeness differs")
    require(value["known_cached_input_tokens"] <= value["known_input_tokens"]
            and value["known_reasoning_output_tokens"] <= value["known_output_tokens"], "Token subset exceeds its parent total")
    return value


def combine_usage(values):
    values = [validate_usage(value) for value in values]
    keys = ("attempts", "successful_calls", "known_usage_calls", "known_input_tokens", "known_output_tokens",
            "known_total_tokens", "known_cached_input_tokens", "known_cached_input_tokens_calls",
            "known_reasoning_output_tokens", "known_reasoning_output_tokens_calls")
    result = {key: sum(value[key] for value in values) for key in keys}
    result["usage_complete"] = bool(result["attempts"] and result["known_usage_calls"] == result["attempts"])
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        result[key] = result["known_" + key] if result["usage_complete"] else None
    for key in ("cached_input_tokens", "reasoning_output_tokens"):
        result[key] = result["known_" + key] if result["attempts"] and result["known_" + key + "_calls"] == result["attempts"] else None
    return result


def counts(rows):
    authentic = [r for r in rows if r["role"] == "authenticity"]
    controls = [r for r in rows if r["role"] == "attribution_control"]
    outcomes = Counter(r["observed"] if r["valid"] else "failed_or_invalid" for r in authentic)
    return {"cases": len(rows), "completed": sum(r["pipeline_success"] for r in rows),
            "valid": sum(r["valid"] for r in rows), "cutoff": sum(r["cutoff_match"] for r in rows),
            "formal_cutoff": sum(r["formal_cutoff_match"] for r in rows),
            "failed": sum(not r["valid"] for r in rows),
            "unsupported": sum(r["unwarranted_settled_cutoff_verdict"] for r in rows),
            "authenticity": len(authentic), "false": outcomes["contradicted"], "abstained": outcomes["unresolved"],
            "accepted": outcomes["supported"], "conflicting": outcomes["conflicting"],
            "authenticity_failed": outcomes["failed_or_invalid"],
            "control_cases": len(controls), "control_matches": sum(r["cutoff_match"] for r in controls)}


def validate_summary(value):
    require(isinstance(value, dict) and type(value.get("schema_version")) is int and value["schema_version"] == 1 and value.get("frozen_input_checks_passed") is True, "Only completed audited summaries may publish")
    require((value.get("model"), value.get("reasoning_effort"), value.get("tunnel")) == ("gpt-6-astra", "medium", "local"), "Model settings differ")
    require(value.get("event_families") == 2 and value.get("cutoff") == "2023-12-31T23:59:59Z", "Historical scope differs")
    require(value.get("research_mode", "full") in {"full", "claim"}, "Unknown research workflow")
    number = value.get("development_round")
    require(type(number) is int and 1 <= number <= 3 and value.get("phase") in {"development", "confirmation"}, "Unknown round")
    require(value.get("round_id") == (f"round-{number}" if value["phase"] == "development" else "confirmation"), "Round identity differs")
    case_ids = {"h01", "h02", "h05", "h06"} if value["phase"] == "development" else {f"h{i:02d}" for i in range(1, 9)}
    require(value.get("cases") == len(case_ids) and value.get("runs") == len(case_ids) * 2, "Round denominator differs")
    require(all(isinstance(value.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", value[key]) for key in HASH_KEYS), "Missing round commitment")
    rows = value.get("rows")
    require(isinstance(rows, list) and len(rows) == value["runs"], "Missing outcome rows")
    require(all(isinstance(r, dict) and isinstance(r.get("id"), str) and r.get("condition") in ARMS for r in rows), "Invalid outcome identity")
    require({(r["id"], r["condition"]) for r in rows} == {(cid, arm) for cid in case_ids for arm in ARMS}, "Missing or duplicate paired outcomes")
    for row in rows:
        require(row.get("role") in {"authenticity", "attribution_control"} and row.get("variant") in SET_NAMES
                and row.get("observed") in VERDICTS and isinstance(row.get("event_family"), str), "Invalid outcome metadata")
        require((row.get("cutoff_expected"), row.get("future_expected")) ==
                (("unresolved", "contradicted") if row["role"] == "authenticity" else ("supported", "supported")), "Registered label scope differs")
        for flag in ("pipeline_success", "valid", "formal_evidence_valid", "cutoff_match", "formal_cutoff_match", "abstained",
                     "called_later_false_claim_false", "accepted_later_false_claim", "unwarranted_settled_cutoff_verdict",
                     "citation_integrity", "shape_valid"):
            require(type(row.get(flag)) is bool, "Outcome flag must be boolean")
        require(not row["valid"] or (row["pipeline_success"] and row["formal_evidence_valid"] and row["citation_integrity"] and row["shape_valid"]), "Evidence validity exceeds completion or citation checks")
        require(row["cutoff_match"] == bool(row["valid"] and row["observed"] == row.get("cutoff_expected"))
                and row["formal_cutoff_match"] == bool(row["formal_evidence_valid"] and row["observed"] == row.get("cutoff_expected")), "Cutoff flag differs")
        require(row["abstained"] == bool(row["valid"] and row["observed"] == "unresolved")
                and row["called_later_false_claim_false"] == bool(row["valid"] and row["role"] == "authenticity" and row["observed"] == "contradicted")
                and row["accepted_later_false_claim"] == bool(row["valid"] and row["role"] == "authenticity" and row["observed"] == "supported")
                and row["unwarranted_settled_cutoff_verdict"] == bool(row["valid"] and row.get("cutoff_expected") == "unresolved" and row["observed"] != "unresolved"), "Outcome screening flag differs")
        require(integer(row.get("logical_calls")) and row["logical_calls"] <= (1 if row["condition"] == "direct" else 24), "Call budget differs")
        require(validate_usage(row.get("usage"))["attempts"] == row["logical_calls"], "Row call denominator differs")
    variants = {"original"} if value["phase"] == "development" else {"original", "blinded"}
    require(set(r["variant"] for r in rows) == variants, "Variant denominator differs")
    require(len({r["event_family"] for r in rows}) == 2, "Independent event-family denominator differs")
    for variant in variants:
        for arm in ARMS:
            group = [r for r in rows if r["variant"] == variant and r["condition"] == arm]
            require(len(group) == 4 and Counter(r["role"] for r in group) == {"authenticity": 2, "attribution_control": 2}, "Role denominator differs")
    stages = value.get("stages")
    require(isinstance(stages, list) and all(isinstance(stage, dict) for stage in stages), "Missing phase accounting")
    identities = []
    for stage in stages:
        arm, name = stage.get("condition"), stage.get("stage")
        require(arm in ARMS and name in ({"direct"} if arm == "direct" else FORMAL | RESEARCH), "Unknown stage")
        require(stage.get("phase") == ("formal" if name in FORMAL else "direct" if name == "direct" else "research"), "Stage phase differs")
        validate_usage(stage)
        identities.append((arm, name))
    require(len(set(identities)) == len(identities), "Duplicate stage accounting")
    for arm in ARMS:
        group = [r for r in rows if r["condition"] == arm]
        usage = combine_usage(r["usage"] for r in group)
        require(usage == combine_usage(s for s in stages if s["condition"] == arm), "Stage usage differs from all outcome rows")
        condition = value.get("conditions", {}).get(arm)
        require(isinstance(condition, dict) and all(condition.get(k) == v for k, v in usage.items()), "Condition usage differs")
        total = counts(group)
        require(condition.get("cases") == total["cases"] and condition.get("pipeline_completed") == total["completed"]
                and condition.get("evidence_valid") == total["valid"] and condition.get("failed_or_invalid") == total["failed"], "Condition outcome totals differ")
    return value


def total_text(usage):
    return f"{usage['total_tokens']:,}" if usage["usage_complete"] else f"Unknown; ≥{usage['known_total_tokens']:,} known"


def rate(numerator, denominator):
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.0f}%)"


def meets_efficiency_threshold(rows, planned_cases):
    """A cost win must preserve every planned cutoff-correct outcome."""
    arms = {arm: [row for row in rows if row["condition"] == arm] for arm in ARMS}
    if any(len(group) != planned_cases or sum(row["cutoff_match"] for row in group) != planned_cases
           for group in arms.values()):
        return False
    usage = {arm: combine_usage(row["usage"] for row in group) for arm, group in arms.items()}
    if not all(u["usage_complete"] for u in usage.values()) or usage["direct"]["total_tokens"] <= 0:
        return False
    return usage["news_tracing"]["total_tokens"] <= 0.8 * usage["direct"]["total_tokens"]


def round_label(summary):
    # Candidate1's immutable v1 summary predates the explicit mode field.
    return f"{summary['round_id']} ({summary.get('research_mode', 'full')})"


def render(rounds, screening=None):
    require(rounds, "No completed scored rounds supplied")
    rounds = [validate_summary(value) for value in rounds]
    rounds.sort(key=lambda s: (s["phase"] == "confirmation", s["development_round"]))
    require(len({r["round_id"] for r in rounds}) == len(rounds), "Duplicate round summaries")
    development = [r["development_round"] for r in rounds if r["phase"] == "development"]
    require(development == list(range(1, max(development, default=0) + 1)), "Include every completed preceding development round")
    for value in rounds:
        if value["phase"] == "confirmation":
            require(value["development_round"] in development, "Confirmation requires its selected development round")
    latest = rounds[-1]
    primary = {arm: counts([r for r in latest["rows"] if r["condition"] == arm and r["variant"] == "original"]) for arm in ARMS}
    text = ["# Harness optimization: development results", "",
        "These are repeated tests on previously inspected cases from **two event families**, not an unseen accuracy test. "
        "Masked variants are correlated sensitivity checks. [Registered protocol](../../experiments/harness-optimization-20260909/PROTOCOL.md).", "",
        f"Latest scored batch, {round_label(latest)}: on the four named cases, Astra alone had {rate(primary['direct']['cutoff'], 4)} valid cutoff-correct answers; "
        f"the harness had {rate(primary['news_tracing']['cutoff'], 4)}. "
        f"Of the two named claims later established as fabricated, Astra called {primary['direct']['false']} false and abstained on {primary['direct']['abstained']}; "
        f"the harness called {primary['news_tracing']['false']} false and abstained on {primary['news_tracing']['abstained']}. "
        f"Failed/invalid authenticity outcomes were {primary['direct']['authenticity_failed']} and {primary['news_tracing']['authenticity_failed']}, respectively.", "",
        "Abstention is not advance fabrication detection. A false verdict unsupported by the supplied cutoff evidence is not justified detection either. "
        "The original Astra comparison already scored 8/8; this development set cannot establish an accuracy improvement over that result.", "",
        "## Paired outcomes", "",
        "Workflow labels describe the harness arm; the direct Astra setup stays fixed. **Full** enables the broader research workflow; **claim** focuses on the one explicit claim and intentionally omits causal expansion, causal grounding review, timeline, perspective analysis and the separate narrative response. "
        "Claim mode retains decomposition, targeted source research, synthesis and formal evidence verification. Comparisons across rounds reflect these workflow changes, not identical harness settings.", "",
        "Valid cutoff agreement requires the complete research/formal pipeline and exact-source evidence checks. "
        "Formal-only agreement is diagnostic and cannot rescue a failed whole pipeline.", "",
        "| Round | Arm | Set | Valid cutoff agreement | Pipeline completed | Evidence valid | Failed/invalid | Unsupported definite | Formal-only agreement | True controls correct |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    groups = []
    for summary in rounds:
        for variant in SET_NAMES:
            for arm in ARMS:
                rows = [r for r in summary["rows"] if r["variant"] == variant and r["condition"] == arm]
                if not rows:
                    continue
                group, usage = counts(rows), combine_usage(r["usage"] for r in rows)
                groups.append((summary, variant, arm, group, usage))
                text.append(f"| {round_label(summary)} | {ARM_NAMES[arm]} | {SET_NAMES[variant]} | {rate(group['cutoff'], group['cases'])} | {group['completed']}/{group['cases']} | {group['valid']}/{group['cases']} | {group['failed']} | {group['unsupported']} | {group['formal_cutoff']}/{group['cases']} | {group['control_matches']}/{group['control_cases']} |")
    text += ["", "## Later-false claims: separate outcomes", "",
        "Only valid outcomes enter the first four categories; failures remain in the denominator. The two named targets concern reported measurement/data authenticity, not whether every scientific hypothesis is false.", "",
        "| Round | Arm | Set | Claims | Called false | Abstained | Accepted | Conflicting | Failed/invalid |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for summary, variant, arm, group, usage in groups:
        text.append(f"| {round_label(summary)} | {ARM_NAMES[arm]} | {SET_NAMES[variant]} | {group['authenticity']} | {group['false']} | {group['abstained']} | {group['accepted']} | {group['conflicting']} | {group['authenticity_failed']} |")
    text += ["", "## Tokens and calls", "",
        "All attempted calls, including failures, are counted. Unknown totals stay unknown; known counts are lower bounds when any usage is missing. "
        "Cached input is already included in input tokens, not added again. These figures cover recorded benchmark target-model invocations only. "
        "They exclude this Codex task's orchestration, audit and research-agent usage, which is not measured here; they are not total account usage or spend.", "",
        "| Round | Arm | Set | Calls | Known input | Known output | Known cached input | Total tokens | Calls with unknown usage |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for summary, variant, arm, group, usage in groups:
        text.append(f"| {round_label(summary)} | {ARM_NAMES[arm]} | {SET_NAMES[variant]} | {usage['attempts']} | {usage['known_input_tokens']:,} | {usage['known_output_tokens']:,} | {usage['known_cached_input_tokens']:,} | {total_text(usage)} | {usage['attempts'] - usage['known_usage_calls']} |")
    text += ["", "The efficiency threshold preserves baseline accuracy: both arms must have valid cutoff-correct answers for every planned case (4/4 in DEV; 8/8 in confirmation), and the harness must use at least 20% fewer fully accounted tokens. Equal reduced scores or matching failures cannot meet it. Missing usage cannot establish this advantage.", ""]
    for summary in rounds:
        chosen = {arm: next((g, u) for s, v, a, g, u in groups if s is summary and v == "original" and a == arm) for arm in ARMS}
        direct, harness = chosen["direct"], chosen["news_tracing"]
        if direct[1]["usage_complete"] and harness[1]["usage_complete"] and direct[1]["total_tokens"] > 0:
            ratio = harness[1]["total_tokens"] / direct[1]["total_tokens"]
            met = meets_efficiency_threshold(summary["rows"], summary["cases"])
            text.append(f"- {round_label(summary)}, named cases: harness/Astra token ratio **{ratio:.2f}×**. "
                        + (f"DEV efficiency threshold: {'met' if met else 'not met'}." if summary["phase"] == "development" else "This is a repeated-case confirmation ratio, not independent validation."))
        else:
            text.append(f"- {round_label(summary)}, named cases: exact cost ratio and efficiency advantage cannot be established from the recorded usage.")
        if summary["phase"] == "confirmation":
            all_usage = {arm: combine_usage(r["usage"] for r in summary["rows"] if r["condition"] == arm) for arm in ARMS}
            if all(u["usage_complete"] for u in all_usage.values()) and all_usage["direct"]["total_tokens"] > 0:
                ratio = all_usage["news_tracing"]["total_tokens"] / all_usage["direct"]["total_tokens"]
                met = meets_efficiency_threshold(summary["rows"], summary["cases"])
                text.append(f"- confirmation, all eight planned cases: harness/Astra token ratio **{ratio:.2f}×**; full-accuracy efficiency threshold {'met' if met else 'not met'}. This remains a development-data result.")
            else:
                text.append("- confirmation, all eight planned cases: incomplete usage prevents an exact cost comparison or efficiency-improvement claim.")
    developments = [s for s in rounds if s["phase"] == "development"]
    if len(developments) > 1:
        first, last = developments[0], developments[-1]
        earlier = next((g, u) for s, v, a, g, u in groups if s is first and v == "original" and a == "news_tracing")
        later = next((g, u) for s, v, a, g, u in groups if s is last and v == "original" and a == "news_tracing")
        if earlier[1]["usage_complete"] and later[1]["usage_complete"] and earlier[1]["total_tokens"] > 0:
            change = 100 * (later[1]["total_tokens"] / earlier[1]["total_tokens"] - 1)
            direction = "fewer" if change < 0 else "more"
            text += ["", f"Harness development change from {round_label(first)} to {round_label(last)}: "
                f"valid cutoff-correct outcomes were {earlier[0]['cutoff']}/4 and {later[0]['cutoff']}/4; "
                f"fully accounted tokens changed from {earlier[1]['total_tokens']:,} to {later[1]['total_tokens']:,} "
                f"(**{abs(change):.2f}% {direction}**). "
                "This compares two harness workflows on DEV. It does not establish an efficiency win over Astra or advance fabrication detection."]
    text += ["", "## Research versus formal phases", "",
        "Phase totals cover all cases in that batch (four named cases in development; eight named/masked cases in confirmation). "
        "They count actual invocations; deterministic source selection requires no model call. Successful calls mean transport completion; their outputs can still fail validation.", "",
        "| Round | Arm | Phase | Calls | Successful calls | Known input | Known output | Total tokens | Unknown-usage calls |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for summary in rounds:
        phases = defaultdict(list)
        for stage in summary["stages"]:
            phases[stage["condition"], stage["phase"]].append(stage)
        for (arm, phase), stages in sorted(phases.items()):
            usage = combine_usage(stages)
            text.append(f"| {round_label(summary)} | {ARM_NAMES[arm]} | {phase} | {usage['attempts']} | {usage['successful_calls']} | {usage['known_input_tokens']:,} | {usage['known_output_tokens']:,} | {total_text(usage)} | {usage['attempts'] - usage['known_usage_calls']} |")
    text += ["", "## Earlier integrated-harness baseline", "",
        "Before these optimization rounds, the four named cases had 4/4 valid cutoff-correct outcomes for Astra alone and 1/4 for the integrated harness. "
        "The harness recorded at least 805,794 tokens; one invocation had unknown usage, so its exact total and an exact cost ratio are unavailable. "
        "[Preserved earlier report](../historical-news-tracing-20260908/README.md)."]
    if screening is not None:
        text += ["", "## Screening for unseen cases", "",
            f"Screening covered **{screening['deduplicated_families_screened']} deduplicated event families**. "
            f"It produced **{screening['ready_new_holdout_families']} ready new families and {screening['ready_new_holdout_cases']} ready new cases**, "
            f"with **{screening['pending_followup_families']} active follow-ups pending**. "
            "No held-out dataset was created and no held-out model evaluation was conducted. "
            "Zero pending means no queued follow-ups; earlier uncertain leads remain unapproved.", "",
            "This was bounded screening under the required historical-evidence and first-public-finding dates, not proof that no eligible families exist. "
            "[Verified metadata-only screening totals](SCREENING_TOTALS.json)."]
    text += ["", "## Scope and audit commitments", "",
        "Both arms use gpt-6-astra at medium reasoning through the local Codex-login HTTP route; inference is hosted. "
        "Direct gets one call, the harness at most 24 calls including at most 10 formal calls, each capped at 90 seconds. "
        "Only supplied versions available by the end of 2023 are eligible; no live source search is used. Later labels are scored after the batch. "
        "Research advice remains untrusted and cannot establish evidence or source originality. Original publication is not proof of authentic measurements.", "",
        "The evidence pool is finite. One historical accepted-manuscript text packet lacks its referenced table/figure sheets; this is text-only evaluation, not visual or laboratory forensics. "
        "A present-day model's learned knowledge cannot be erased. Repeated cases and masked identities do not provide independent generalization evidence. "
        "No latency advantage is inferred from potentially inconsistent clocks. Only completed, scored batches supplied to this exporter are included; partial attempts require separate reporting and cannot be silently replaced.", "",
        "The tables are reconstructed from outcome rows and checked against condition and stage totals. The exporter emits no source text, model prose, prompts or personal paths.", "",
        "| Round | Registration SHA256 | Candidate inventory SHA256 | Scorer SHA256 |",
        "|---|---|---|---|"]
    for summary in rounds:
        text.append(f"| {round_label(summary)} | `{summary['registration_sha256']}` | `{summary['code_manifest_sha256']}` | `{summary['scorer_sha256']}` |")
    rendered = "\n".join(text) + "\n"
    require(not re.search(r"/Users/|/private/var/|/home/|jsessionid|session_id|thread_id", rendered, re.I), "Private identifier entered the public report")
    return rendered


def load_screening():
    raw = SCREENING_PATH.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCREENING_SHA256, "Screening totals differ from the verified artifact")
    value = json.loads(raw)
    require(value.get("kind") == "metadata_only_holdout_screening_totals" and value.get("screening_closed") is True
            and value.get("holdout_created") is False and value.get("candidate_identities_released_to_tuning") is False
            and value.get("later_outcomes_released_to_tuning") is False, "Screening scope differs")
    require((value.get("deduplicated_families_screened"), value.get("ready_new_holdout_families"),
             value.get("ready_new_holdout_cases"), value.get("pending_followup_families")) == (19, 0, 0, 0), "Screening counts differ")
    return value, raw


def publish(paths, output=DEFAULT_OUTPUT):
    require(paths, "Supply at least one completed SUMMARY.json")
    summaries = []
    for path in paths:
        path = Path(path)
        require(path.name == "SUMMARY.json" and path.stat().st_size <= 20_000_000, "Expected a bounded completed SUMMARY.json")
        summaries.append(json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite summary JSON"))))
    screening, raw_screening = load_screening()
    rendered = render(summaries, screening)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    screening_output = output.parent / "SCREENING_TOTALS.json"
    screening_output.write_bytes(raw_screening)
    require(hashlib.sha256(screening_output.read_bytes()).hexdigest() == SCREENING_SHA256, "Public screening copy changed")
    output.write_text(rendered, encoding="utf-8")
    return {"rounds": len(summaries), "report_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "screening_sha256": SCREENING_SHA256}


def self_test():
    """Synthetic regression for matching failures and incomplete token usage."""
    from copy import deepcopy
    def usage(tokens):
        value = {"attempts": 1, "successful_calls": 1, "known_usage_calls": 1, "usage_complete": True,
                 "input_tokens": tokens, "output_tokens": 0, "total_tokens": tokens,
                 "known_input_tokens": tokens, "known_output_tokens": 0, "known_total_tokens": tokens,
                 "cached_input_tokens": None, "reasoning_output_tokens": None,
                 "known_cached_input_tokens": 0, "known_cached_input_tokens_calls": 0,
                 "known_reasoning_output_tokens": 0, "known_reasoning_output_tokens_calls": 0}
        return value
    for size in (4, 8):
        rows = [{"condition": arm, "cutoff_match": True, "usage": usage(100 if arm == "direct" else 10)}
                for arm in ARMS for _ in range(size)]
        require(meets_efficiency_threshold(rows, size), "Complete accurate inexpensive fixture should meet the threshold")
        failed = deepcopy(rows)
        for arm in ARMS:
            for row in [r for r in failed if r["condition"] == arm][:2]:
                row["cutoff_match"] = False
        require(not meets_efficiency_threshold(failed, size), "Matching failures must never yield an efficiency improvement")
        missing = deepcopy(rows)
        item = missing[-1]["usage"]
        item.update(successful_calls=0, known_usage_calls=0, usage_complete=False,
                    input_tokens=None, output_tokens=None, total_tokens=None,
                    known_input_tokens=0, known_output_tokens=0, known_total_tokens=0)
        require(not meets_efficiency_threshold(missing, size), "Unknown usage must not establish an efficiency improvement")
    return {"self_test": "passed", "synthetic_only": True, "matching_failure_cases": [4, 8], "reports_written": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summaries", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    print(json.dumps(self_test() if args.self_test else publish(args.summaries, args.output)))
