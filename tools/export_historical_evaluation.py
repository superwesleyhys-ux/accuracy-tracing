"""Export historical-cutoff metrics without source text or model prose.

Export requires the completed local SUMMARY.json and SANITIZED_RECEIPTS.json.
--verify-public needs only this script and the published report directory.
Neither mode invokes a model, network request, or original experiment runner.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments/historical-cutoff-20260908"
PUBLIC = ROOT / "reports/historical-evaluation-20260908"
CONDITIONS = ("direct", "double_loop")
VARIANTS = ("original", "blinded")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
PUBLIC_FILES = ("RESULTS.json", "RECEIPTS.json", "SOURCES.json", "README.md")
LOOP_FLAGS = ("accepted_revisit_executed", "reanalysis_executed",
              "verification_feedback_executed", "both_loops_executed", "recorded_analysis_changed")
SCORE_FLAGS = ("valid", "cutoff_match", "future_verdict_match", "abstained",
               "accepted_later_false_claim", "called_later_false_claim_false",
               "unwarranted_settled_cutoff_verdict", "unsupported_certainty", "unsupported_conflict")
USAGE_FIELDS = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_output_tokens")
CASE_METADATA = {
    f"h{number:02d}": {
        "id": f"h{number:02d}",
        "event_family": "osaka-dat-2023" if number <= 4 else "hargreaves-metals-2017",
        "role": "authenticity" if number % 2 else "attribution_control",
        "variant": "original" if number in {1, 2, 5, 6} else "blinded",
        "cutoff_expected": "unresolved" if number % 2 else "supported",
        "future_expected": "contradicted" if number % 2 else "supported",
    } for number in range(1, 9)
}
SAFE_URLS = {
    "https://doi.org/10.1073/pnas.2308260120",
    "https://doi.org/10.1016/j.chemosphere.2017.02.034",
    "https://www.osaka-u.ac.jp/en/news/topics/2025/02/07001",
    "https://www.osaka-u.ac.jp/ja/news/topics/2025/02/files/4h3a9t/@@download/file",
    "https://doi.org/10.1073/pnas.2501149122",
    "https://www.sciencedirect.com/science/article/abs/pii/S0045653517302126",
    "https://dspace.lib.cranfield.ac.uk/handle/1826/11505",
    "https://doi.org/10.1016/j.chemosphere.2025.144440",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    def reject(value):
        raise ValueError("Nonfinite JSON value")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def count(value):
    return type(value) is int and value >= 0


def finite(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def exact_keys(value, keys, message):
    require(isinstance(value, dict) and set(value) == set(keys), message)


def canonical_url(value):
    require(isinstance(value, str) and value in SAFE_URLS, "Source URL is outside the public canonical allowlist")
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and not parsed.query and not parsed.fragment
            and not parsed.username and not parsed.password and ";" not in parsed.path,
            "Session-bearing or noncanonical URL")
    return value


def token_stats(receipts):
    """Independent equivalent of registered token accounting, retaining failures."""
    known, cached, reasoning = [], [], []
    for call in receipts:
        usage = call["usage"]
        if not count(usage.get("input_tokens")) or not count(usage.get("output_tokens")):
            continue
        total = usage.get("total_tokens")
        if total is not None and (not count(total) or total != usage["input_tokens"] + usage["output_tokens"]):
            continue
        known.append(usage)
        if count(usage.get("cached_input_tokens")) and usage["cached_input_tokens"] <= usage["input_tokens"]:
            cached.append(usage["cached_input_tokens"])
        if count(usage.get("reasoning_output_tokens")):
            reasoning.append(usage["reasoning_output_tokens"])
    inputs = sum(u["input_tokens"] for u in known)
    outputs = sum(u["output_tokens"] for u in known)
    attempts = len(receipts)
    return {"attempts": attempts, "successful_calls": sum(r["success"] for r in receipts),
            "known_usage_calls": len(known), "known_input_tokens": inputs, "known_output_tokens": outputs,
            "known_total_tokens": inputs + outputs,
            "total_tokens": inputs + outputs if attempts and len(known) == attempts else None,
            "known_cached_usage_calls": len(cached), "known_cached_input_tokens": sum(cached),
            "cached_input_tokens": sum(cached) if attempts and len(cached) == attempts else None,
            "known_reasoning_usage_calls": len(reasoning), "known_reasoning_output_tokens": sum(reasoning),
            "reasoning_output_tokens": sum(reasoning) if attempts and len(reasoning) == attempts else None}


def score_flags(run, case):
    valid = run["pipeline_success"] and run["citation_integrity"]
    verdict = run["observed"]
    authenticity = case["role"] == "authenticity"
    unsettled = valid and case["cutoff_expected"] == "unresolved"
    return {"valid": valid,
            "cutoff_match": bool(valid and verdict == case["cutoff_expected"]),
            "future_verdict_match": bool(valid and verdict == case["future_expected"]),
            "abstained": bool(valid and verdict == "unresolved"),
            "accepted_later_false_claim": bool(valid and authenticity and verdict == "supported"),
            "called_later_false_claim_false": bool(valid and authenticity and verdict == "contradicted"),
            "unwarranted_settled_cutoff_verdict": bool(unsettled and verdict != "unresolved"),
            "unsupported_certainty": bool(unsettled and verdict in {"supported", "contradicted"}),
            "unsupported_conflict": bool(unsettled and verdict == "conflicting")}


def accounting(runs, receipts):
    result = {"scores_by_variant": {}, "conditions": {}, "stages": []}
    for variant in VARIANTS:
        result["scores_by_variant"][variant] = {}
        for arm in CONDITIONS:
            selected = [r for r in runs if r["variant"] == variant and r["condition"] == arm]
            authentic = [r for r in selected if r["role"] == "authenticity"]
            controls = [r for r in selected if r["role"] == "attribution_control"]
            calls = [c for c in receipts if c["condition"] == arm and CASE_METADATA[c["case_id"]]["variant"] == variant]
            result["scores_by_variant"][variant][arm] = {
                "cases": len(selected), "completed": sum(r["pipeline_success"] for r in selected),
                "evidence_valid": sum(r["valid"] for r in selected),
                "failed_or_invalid": sum(not r["valid"] for r in selected),
                "cutoff_matches": sum(r["cutoff_match"] for r in selected),
                "future_verdict_matches": sum(r["future_verdict_match"] for r in selected),
                "authenticity_cases": len(authentic),
                "authenticity_failed_or_invalid": sum(not r["valid"] for r in authentic),
                "accepted_later_false_claims": sum(r["accepted_later_false_claim"] for r in authentic),
                "called_later_false_claims_false": sum(r["called_later_false_claim_false"] for r in authentic),
                "authenticity_abstentions": sum(r["abstained"] for r in authentic),
                "unwarranted_settled_cutoff_verdicts": sum(r["unwarranted_settled_cutoff_verdict"] for r in authentic),
                "unsupported_certainty": sum(r["unsupported_certainty"] for r in authentic),
                "unsupported_conflict": sum(r["unsupported_conflict"] for r in authentic),
                "controls": len(controls), "control_matches": sum(r["cutoff_match"] for r in controls),
                "run_errors": sum(r["error_count"] for r in selected),
                "timeout_errors": sum(r.get("timeout_error_count", 0) for r in selected),
                "clock_discrepancies": sum(r["clock_discrepancy"] for r in selected),
                "both_loop_cases": sum(r["loop_flags"]["both_loops_executed"] for r in selected),
                **token_stats(calls)}
    for arm in CONDITIONS:
        result["conditions"][arm] = token_stats([c for c in receipts if c["condition"] == arm])
    groups = defaultdict(list)
    for call in receipts:
        groups[call["condition"], call["stage"]].append(call)
    result["stages"] = [{"condition": arm, "stage": stage, **token_stats(calls)}
                        for (arm, stage), calls in sorted(groups.items())]
    return result


def shape_valid(output, arm):
    if not isinstance(output, dict):
        return False
    fields = {"verdict", "basis", "rationale"} | ({"round", "gaps", "resolutions"} if arm == "double_loop" else set())
    if set(output) != fields or not isinstance(output.get("verdict"), str) or output["verdict"] not in VERDICTS or not isinstance(output.get("rationale"), str) or not isinstance(output.get("basis"), list):
        return False
    if arm == "double_loop" and (not count(output["round"]) or not isinstance(output["gaps"], list) or not isinstance(output["resolutions"], list)):
        return False
    return all(isinstance(s, dict) and {"version_id", "quote"} <= set(s) <= {"version_id", "quote", "start", "end"}
               and isinstance(s["version_id"], str) and isinstance(s["quote"], str) for s in output["basis"])


def offset_only_year_flags(output, screened):
    """Post-run clarification; preserve the registered broad year screen itself."""
    if not isinstance(output, dict):
        return []
    textual = set()
    def walk(value):
        if isinstance(value, str):
            textual.update(re.findall(r"\b20(?:2[4-9]|[3-9]\d)\b", value))
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(output)
    offsets = {str(span[key]) for span in output.get("basis", []) if isinstance(span, dict)
               for key in ("start", "end") if type(span.get(key)) is int and 2024 <= span[key] <= 2099}
    return sorted(set(screened) & offsets - textual)


def sanitize_receipt(raw):
    fields = ("id", "case_id", "condition", "ordinal", "stage", "model", "reasoning_effort", "tunnel",
              "success", "status", "wall_seconds", "local_skills_disabled", "input_sha256",
              "response_sha256", "original_receipt_sha256")
    result = {k: raw[k] for k in fields}
    usage = raw.get("usage") or {}
    require(isinstance(usage, dict), "Invalid receipt usage object")
    result["usage"] = {k: usage.get(k) for k in USAGE_FIELDS}
    if result["usage"]["cached_input_tokens"] is None and isinstance(usage.get("input_tokens_details"), dict):
        result["usage"]["cached_input_tokens"] = usage["input_tokens_details"].get("cached_tokens")
    if result["usage"]["reasoning_output_tokens"] is None and isinstance(usage.get("output_tokens_details"), dict):
        result["usage"]["reasoning_output_tokens"] = usage["output_tokens_details"].get("reasoning_tokens")
    return result


def build_results(summary, receipt_document):
    require(summary.get("frozen_input_checks_passed") is True and summary["cases"] == 8
            and summary["runs"] == 16 and summary["event_families"] == 2, "Completed eight-case scored batch required")
    require((summary["model"], summary["reasoning_effort"], summary["tunnel"], summary["cutoff"])
            == ("gpt-6-astra", "medium", "local", "2023-12-31T23:59:59Z"), "Unexpected historical settings")
    receipts = [sanitize_receipt(r) for r in receipt_document["receipts"]]
    runs = []
    for raw in summary["rows"]:
        cid, arm = raw["id"], raw["condition"]
        require(cid in CASE_METADATA and arm in CONDITIONS, "Unexpected case or condition")
        case = CASE_METADATA[cid]
        require(all(raw[k] == case[k] for k in case if k != "id"), "Registered case metadata changed")
        errors = raw["errors"]
        require(isinstance(errors, list), "Run errors must be a list")
        error_types = [e.get("type") if isinstance(e, dict) and isinstance(e.get("type"), str)
                       and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", e["type"]) else "unspecified" for e in errors]
        mechanisms = raw.get("mechanisms") or {}
        run = {**case, "case_id": cid, "condition": arm,
               **{k: raw[k] for k in ("observed", "raw_verdict", "pipeline_success", "citation_integrity", "timer_seconds", "clock_discrepancy")},
               "locally_audited_output_shape": shape_valid(raw.get("final_output"), arm),
               "error_count": len(errors), "error_types": error_types,
               "timeout_error_count": sum(isinstance(e, dict) and isinstance(e.get("message"), str)
                   and bool(re.search(r"timed out|timeout|deadline exceeded", e["message"], re.I)) for e in errors),
               "logical_calls": raw["logical_calls"],
               "receipt_ids": [r["id"] for r in receipts if (r["case_id"], r["condition"]) == (cid, arm)],
               "failed_calls": [{"ordinal": r["ordinal"], "stage": r["stage"]} for r in receipts
                   if (r["case_id"], r["condition"]) == (cid, arm) and not r["success"]],
               "loop_flags": {k: mechanisms.get(k, False) for k in LOOP_FLAGS},
               "explicit_future_years": raw["explicit_future_years_in_final_output"],
               "locally_audited_offset_only_year_flags": offset_only_year_flags(raw.get("final_output"), raw["explicit_future_years_in_final_output"])}
        if not isinstance(run["raw_verdict"], str) or run["raw_verdict"] not in VERDICTS:
            run["raw_verdict"] = None
        del run["id"]
        run.update(score_flags(run, case))
        require(all(run[k] is raw[k] for k in SCORE_FLAGS if k in raw), "Public score flags differ from registered scorer")
        require(token_stats([r for r in receipts if r["id"] in run["receipt_ids"]]).items() >= raw["usage"].items(),
                "Run usage differs from registered scorer")
        runs.append(run)
    results = {"schema_version": 1, "configuration": {
        "model": "gpt-6-astra", "reasoning_effort": "medium", "tunnel": "local", "cutoff": summary["cutoff"],
        "timeout_seconds_per_call": 90, "max_calls_per_direct_case": 1, "max_calls_per_harness_case": 10,
        "equal_token_budget": False, "orchestration_retries": 0, "api_fallback": False,
        "local_means_offline_weights": False},
        "event_family_count": 2, "case_count": 8, "named_primary_case_count": 4,
        "masked_sensitivity_case_count": 4, "cases": list(CASE_METADATA.values()), "runs": runs,
        "accounting": accounting(runs, receipts),
        "local_scoring_commitments": {k: summary[k] for k in ("manifest_sha256", "gold_sha256", "scorer_sha256", "helper_sha256")},
        "local_audit_scope": {"frozen_input_checks_passed": True,
            "quote_integrity_reproducible_without_sources": False, "loop_execution_reproducible_without_histories": False,
            "future_year_screen_proves_no_model_memory": False, "labels_independently_human_adjudicated": False}}
    recomputed = results["accounting"]
    for variant in VARIANTS:
        for arm in CONDITIONS:
            require(recomputed["scores_by_variant"][variant][arm].items() >= summary["scores_by_variant"][variant][arm].items(), "Variant denominator or score differs")
    for arm in CONDITIONS:
        require(recomputed["conditions"][arm].items() >= summary["conditions"][arm].items(), "Condition usage differs")
    require([{k: v for k, v in row.items() if not k.startswith("known_reasoning") and k != "reasoning_output_tokens"}
             for row in recomputed["stages"]] == summary["stages"], "Stage usage differs")
    return results, {"schema_version": 1, "receipts": receipts}


def source_rows(archive=ARCHIVE):
    archive = Path(archive)
    candidates = read(archive / "private/candidates-primary.json")
    families = {f["family_id"]: f for f in candidates["families"]}
    require(set(families) == {"osaka-dat", "hargreaves-wastewater"}, "Unexpected source families")
    definitions = [
        ("osaka-dat", "osaka-original-source.json", "osaka-2023-original.pdf", "osaka-dat-2023", 2023,
         "https://doi.org/10.1073/pnas.2308260120", "2023-12-06T11:59:59Z",
         "Publisher body states publication 2023-09-25; download footers identify 2023-11-30; repository availability is 2023-12-05. Availability is a conservative end-of-date upper bound, not a known publication clocktime. The current repository cover was excluded."),
        ("hargreaves-wastewater", "hargreaves-original-source.json", "hargreaves-2017-original.pdf", "hargreaves-metals-2017", 2017,
         "https://doi.org/10.1016/j.chemosphere.2017.02.034", "2020-03-09T04:28:50Z",
         "All extracted text from the retained 18-page accepted-manuscript PDF captured by the Internet Archive at 2020-03-09 04:28:50 UTC; Memento-Datetime and original response date corroborate the capture. The PDF identifies the May 2017 issue and ends in references. Referenced table and figure sheets are absent from the text packet. The archived PDF URL containing a historical session parameter is deliberately not published."),
    ]
    sources = []
    for family, meta_name, raw_name, event, year, url, available, evidence in definitions:
        expected = f"experiments/historical-cutoff-20260908/private/sources/{meta_name}"
        require(families[family]["original_source_metadata"] == expected and families[family]["source_ready"] is True, "Original source metadata mapping differs")
        meta = read(archive / "private/sources" / meta_name)
        raw_hash = digest(archive / "private/sources" / raw_name)
        require(raw_hash == meta["sha256"] and meta["doi"] == url.removeprefix("https://doi.org/"), "Original source hash or DOI differs")
        sources.append({"id": event + ":original", "event_family": event, "role": "eligible_original",
            "title": meta["title"], "canonical_url": canonical_url(url), "publication_year": year,
            "available_at": available, "availability_evidence": evidence, "raw_sha256": raw_hash,
            "capture_kind": "original_pdf", "source_bytes_bundled": False})
    later = [
        ("osaka-dat", 0, "osaka-dat-2023", "Institutional announcement of research misconduct findings", "institutional_html", None),
        ("osaka-dat", 1, "osaka-dat-2023", "Institutional investigation report on research misconduct", "institutional_pdf", None),
        ("osaka-dat", 2, "osaka-dat-2023", "Retraction of the 2023 DAT study", "publisher_xml", None),
        ("hargreaves-wastewater", 0, "hargreaves-metals-2017", "Publisher notice for the retracted 2017 trace-metal study", "publisher_text_capture", None),
        ("hargreaves-wastewater", 1, "hargreaves-metals-2017", "Institutional repository record for the withdrawn trace-metal study", "repository_json", "https://dspace.lib.cranfield.ac.uk/handle/1826/11505"),
        ("hargreaves-wastewater", 2, "hargreaves-metals-2017", "Retraction notice for the 2017 trace-metal study", "publisher_xml", "https://doi.org/10.1016/j.chemosphere.2025.144440"),
    ]
    for family, position, event, title, capture, override_url in later:
        item = families[family]["held_out_sources"][position]
        path = Path(item["path"])
        prefix = Path("experiments/historical-cutoff-20260908/private/sources")
        require(path.parent == prefix and path.name not in {".", ".."}, "Unsafe retained source location")
        sources.append({"id": event + f":later:{position + 1}", "event_family": event,
            "role": "held_out_later_finding", "title": title,
            "canonical_url": canonical_url(override_url or item["url"]), "publication_year": 2025,
            "available_at": None,
            "availability_evidence": ("Public institutional announcement and paper retraction in February 2025; the retained investigation report may include later November 2025 revisions. Private investigation began in 2024."
                                      if family == "osaka-dat" else
                                      "Publisher and university identify a 2025 fabrication finding. The separate notice has an August 2025 issue date; the exact earliest public disclosure and private admission dates are not established."),
            "raw_sha256": digest(archive / "private/sources" / path.name), "capture_kind": capture,
            "source_bytes_bundled": False})
    return {"schema_version": 1, "sources": sources,
            "hash_scope": "Hashes identify retained original local captures; a web-tool text capture hash is not a raw HTTP response hash. No publisher text, figure, quotation or response header is redistributed."}


def verify_data(results, receipt_document, sources):
    exact_keys(results, ("schema_version", "configuration", "event_family_count", "case_count", "named_primary_case_count",
        "masked_sensitivity_case_count", "cases", "runs", "accounting", "local_scoring_commitments", "local_audit_scope"), "Unexpected results fields")
    exact_keys(receipt_document, ("schema_version", "receipts"), "Unexpected receipt document fields")
    exact_keys(sources, ("schema_version", "sources", "hash_scope"), "Unexpected sources fields")
    require(results["schema_version"] == receipt_document["schema_version"] == sources["schema_version"] == 1, "Unknown public schema")
    require(results["cases"] == list(CASE_METADATA.values()), "Case metadata or registered labels changed")
    require(results["configuration"] == {"model": "gpt-6-astra", "reasoning_effort": "medium", "tunnel": "local",
            "cutoff": "2023-12-31T23:59:59Z", "timeout_seconds_per_call": 90,
            "max_calls_per_direct_case": 1, "max_calls_per_harness_case": 10,
            "equal_token_budget": False, "orchestration_retries": 0, "api_fallback": False,
            "local_means_offline_weights": False}, "Public configuration differs from the registered comparison")
    require(results["local_audit_scope"] == {"frozen_input_checks_passed": True,
            "quote_integrity_reproducible_without_sources": False, "loop_execution_reproducible_without_histories": False,
            "future_year_screen_proves_no_model_memory": False, "labels_independently_human_adjudicated": False}, "Public audit scope changed")
    require((results["case_count"], results["event_family_count"], results["named_primary_case_count"], results["masked_sensitivity_case_count"]) == (8, 2, 4, 4), "Case/event denominator differs")
    receipts, runs = receipt_document["receipts"], results["runs"]
    require(isinstance(receipts, list) and isinstance(runs, list), "Expected row arrays")
    require(len(runs) == 16 and {(r["case_id"], r["condition"]) for r in runs} == {(c, a) for c in CASE_METADATA for a in CONDITIONS}, "Missing or duplicate scheduled run")
    index = {r["id"]: r for r in receipts}
    require(len(index) == len(receipts), "Duplicate call receipt")
    receipt_fields = {"id", "case_id", "condition", "ordinal", "stage", "model", "reasoning_effort", "tunnel",
                      "success", "status", "wall_seconds", "local_skills_disabled", "input_sha256",
                      "response_sha256", "original_receipt_sha256", "usage"}
    for call in receipts:
        exact_keys(call, receipt_fields, "Unexpected public receipt fields")
        require(call["case_id"] in CASE_METADATA and call["condition"] in CONDITIONS and count(call["ordinal"]) and call["ordinal"] > 0, "Invalid receipt identity")
        require(call["id"] == f"{call['case_id']}:{call['condition']}:{call['ordinal']:02d}", "Receipt ID differs")
        require((call["model"], call["reasoning_effort"], call["tunnel"]) == ("gpt-6-astra", "medium", "local"), "Model settings differ")
        require(call["stage"] in ({"direct"} if call["condition"] == "direct" else {"decompose", "select", "verify"}), "Invalid stage")
        require(type(call["success"]) is bool and call["status"] in {"completed", "failed", "running"}
                and call["success"] is (call["status"] == "completed"), "Call status differs")
        require(finite(call["wall_seconds"]) and (call["local_skills_disabled"] is None or count(call["local_skills_disabled"])), "Invalid timing or isolation receipt")
        require(all(valid_hash(call[k]) for k in ("input_sha256", "original_receipt_sha256"))
                and (valid_hash(call["response_sha256"]) or (call["response_sha256"] is None and not call["success"])), "Invalid original artifact commitment")
        exact_keys(call["usage"], USAGE_FIELDS, "Unexpected usage fields")
        require(all(value is None or count(value) for value in call["usage"].values()), "Invalid token value")
        if count(call["usage"]["reasoning_output_tokens"]) and count(call["usage"]["output_tokens"]):
            require(call["usage"]["reasoning_output_tokens"] <= call["usage"]["output_tokens"], "Reasoning tokens exceed total output tokens")
    run_fields = (set(next(iter(CASE_METADATA.values()))) - {"id"}) | {"case_id", "condition", "observed", "raw_verdict", "pipeline_success", "citation_integrity", "timer_seconds", "clock_discrepancy", "locally_audited_output_shape", "error_count", "error_types", "timeout_error_count", "logical_calls", "receipt_ids", "failed_calls", "loop_flags", "explicit_future_years", "locally_audited_offset_only_year_flags"} | set(SCORE_FLAGS)
    used = []
    for run in runs:
        exact_keys(run, run_fields, "Unexpected public run fields")
        case = CASE_METADATA[run["case_id"]]
        require(all(run[k] == v for k, v in case.items() if k != "id"), "Run metadata differs")
        require(run["observed"] in VERDICTS | {"execution_failed"} and run["raw_verdict"] in VERDICTS | {None}, "Invalid verdict category")
        require(count(run["error_count"]) and run["error_count"] == len(run["error_types"])
                and all(isinstance(e, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", e) for e in run["error_types"]), "Invalid error accounting")
        require(count(run["timeout_error_count"]) and run["timeout_error_count"] <= run["error_count"], "Invalid timeout count")
        require(finite(run["timer_seconds"]), "Invalid elapsed time")
        require(all(type(run[k]) is bool for k in SCORE_FLAGS + ("pipeline_success", "citation_integrity", "clock_discrepancy", "locally_audited_output_shape")), "Invalid boolean audit flag")
        require(count(run["logical_calls"]) and len(run["receipt_ids"]) == run["logical_calls"] <= (1 if run["condition"] == "direct" else 10), "Logical call denominator differs")
        own = [index[rid] for rid in run["receipt_ids"]]
        require([c["ordinal"] for c in own] == list(range(1, len(own) + 1))
                and all((c["case_id"], c["condition"]) == (run["case_id"], run["condition"]) for c in own), "Misassigned or reordered receipt")
        require(run["failed_calls"] == [{"ordinal": c["ordinal"], "stage": c["stage"]} for c in own if not c["success"]], "Failed-call detail differs from receipts")
        completed = bool(run["locally_audited_output_shape"] and own and not run["error_count"]
                         and run["observed"] in VERDICTS and all(c["success"] for c in own)
                         and (run["condition"] != "direct" or run["observed"] == run["raw_verdict"]))
        require(run["pipeline_success"] is completed, "Run completion differs from receipts and shape audit")
        require(all(run[k] is v for k, v in score_flags(run, case).items()), "Cutoff/future/abstention flag differs")
        exact_keys(run["loop_flags"], LOOP_FLAGS, "Unexpected loop fields")
        require(all(type(v) is bool for v in run["loop_flags"].values()), "Invalid loop flag")
        require(run["loop_flags"]["both_loops_executed"] is (run["loop_flags"]["reanalysis_executed"] and run["loop_flags"]["verification_feedback_executed"]), "Both-loop flag differs")
        if run["condition"] == "direct":
            require(not any(run["loop_flags"].values()), "Direct run claims a harness loop")
        require(isinstance(run["explicit_future_years"], list) and len(set(run["explicit_future_years"])) == len(run["explicit_future_years"])
                and all(isinstance(y, str) and re.fullmatch(r"20(?:2[4-9]|[3-9]\d)", y) for y in run["explicit_future_years"]), "Invalid later-year screening")
        require(isinstance(run["locally_audited_offset_only_year_flags"], list)
                and run["locally_audited_offset_only_year_flags"] == sorted(set(run["locally_audited_offset_only_year_flags"]))
                and set(run["locally_audited_offset_only_year_flags"]) <= set(run["explicit_future_years"]), "Offset annotation differs from retained screening flags")
        used.extend(run["receipt_ids"])
    require(len(used) == len(set(used)) == len(receipts) and set(used) == set(index), "Omitted or extra attempt receipts")
    require(accounting(runs, receipts) == results["accounting"], "Published totals/denominators differ from rows and receipts")
    exact_keys(results["local_scoring_commitments"], ("manifest_sha256", "gold_sha256", "scorer_sha256", "helper_sha256"), "Unexpected scoring commitment fields")
    require(all(valid_hash(v) for v in results["local_scoring_commitments"].values()), "Invalid scoring hash")
    require(len(sources["sources"]) == 8 and len({s["id"] for s in sources["sources"]}) == 8, "Source metadata denominator differs")
    for source in sources["sources"]:
        exact_keys(source, ("id", "event_family", "role", "title", "canonical_url", "publication_year", "available_at", "availability_evidence", "raw_sha256", "capture_kind", "source_bytes_bundled"), "Unexpected source fields")
        canonical_url(source["canonical_url"])
        require(valid_hash(source["raw_sha256"]) and source["source_bytes_bundled"] is False, "Invalid source metadata hash/scope")
        require(source["event_family"] in {"osaka-dat-2023", "hargreaves-metals-2017"}
                and source["role"] in {"eligible_original", "held_out_later_finding"}
                and source["publication_year"] in {2017, 2023, 2025}, "Invalid source scope")
        require(isinstance(source["title"], str) and 1 <= len(source["title"]) <= 300
                and isinstance(source["availability_evidence"], str) and len(source["availability_evidence"]) <= 600,
                "Source metadata text is malformed or too long")
    return {"passed": True, "cases": 8, "runs": 16, "event_families": 2, "public_receipts": len(receipts),
            "scores_by_variant": results["accounting"]["scores_by_variant"], "no_model_calls": True,
            "verification_scope": "Public hashes, complete scheduled denominators, flags and all-attempt usage; original source semantics and local loop histories are not reproduced."}


def render_readme(results):
    primary = results["accounting"]["scores_by_variant"]["original"]
    direct, harness = (primary[arm] for arm in CONDITIONS)
    lines = ["# Historical evidence test: Astra and the harness", "",
        f"Of the **two named authenticity claims later shown to involve fabrication**, Astra alone called {direct['called_later_false_claims_false']} false, abstained on {direct['authenticity_abstentions']}, and accepted {direct['accepted_later_false_claims']} as true. Astra with the harness called {harness['called_later_false_claims_false']} false, abstained on {harness['authenticity_abstentions']}, and accepted {harness['accepted_later_false_claims']} as true. Conflicts and failed or invalid outcomes are retained separately below.", "",
        "**Refusing to endorse a claim is not detecting fabrication in advance.** The pre-2024 packets lack independent laboratory records. A rejection that matches later findings can also lack support at the historical cutoff.", "",
        "Eight cases cover two real research events. Four named cases are the primary comparison; four identity-masked derivatives are a separate sensitivity check. Both arms use the same Astra model through local Codex login, with medium reasoning. Local refers to the CLI route: model inference remains remote. Installed skill catalogs are disabled in both arms; normal Codex instructions remain.", ""]
    if direct["total_tokens"] and harness["total_tokens"] is not None:
        ratio = harness["total_tokens"] / direct["total_tokens"]
        no_detection_gain = direct["called_later_false_claims_false"] == harness["called_later_false_claims_false"] == 0
        lines += [f"For the fully measured four named cases, Astra alone used **{direct['total_tokens']:,} tokens** and the harness used **{harness['total_tokens']:,} tokens — {ratio:.2f}× as many**. "
                  + ("No additional fabrication-detection benefit was observed in these named cases." if no_detection_gain else "This cost comparison applies only to the named cases."), ""]
    for variant, title in (("original", "Named cases: primary analysis"), ("blinded", "Masked cases: sensitivity analysis")):
        a, b = (results["accounting"]["scores_by_variant"][variant][arm] for arm in CONDITIONS)
        lines += [f"## {title}", "", "| Measure | Astra alone | Astra + harness |", "|---|---:|---:|"]
        for label, key, denominator in [
            ("Later-false authenticity claims called false", "called_later_false_claims_false", "authenticity_cases"),
            ("Authenticity claims left unresolved", "authenticity_abstentions", "authenticity_cases"),
            ("Later-false authenticity claims accepted", "accepted_later_false_claims", "authenticity_cases"),
            ("Unsupported supported/contradicted answers", "unsupported_certainty", "authenticity_cases"),
            ("Unsupported conflict answers", "unsupported_conflict", "authenticity_cases"),
            ("Authenticity outcomes failed or invalid", "authenticity_failed_or_invalid", "authenticity_cases"),
            ("Completed runs", "completed", "cases"), ("Evidence-valid runs", "evidence_valid", "cases"),
            ("Failed or invalid outcomes", "failed_or_invalid", "cases"),
            ("Matches to cutoff-evidence labels", "cutoff_matches", "cases"),
            ("True attribution controls matched", "control_matches", "controls"),
            ("Both loops executed, local audit", "both_loop_cases", "cases")]:
            lines.append(f"| {label} | {a[key]}/{a[denominator]} | {b[key]}/{b[denominator]} |")
        for label, key in (("Logical attempts, including failures", "attempts"), ("Known total tokens", "known_total_tokens"),
                           ("Calls with known input/output usage", "known_usage_calls"), ("Run errors", "run_errors"),
                           ("Timeout errors", "timeout_errors"), ("Timing discrepancy flags", "clock_discrepancies")):
            lines.append(f"| {label} | {a[key]} | {b[key]} |")
        lines += [""]
    timeout_runs = [r for r in results["runs"] if r["timeout_error_count"]]
    if timeout_runs:
        details = "; ".join(f"{r['case_id']} / {'Astra alone' if r['condition'] == 'direct' else 'Astra + harness'} (failed "
                            + ", ".join(f"{c['stage']} call {c['ordinal']}" for c in r['failed_calls']) + ")" for r in timeout_runs)
        lines += [f"The batch retained **{sum(r['timeout_error_count'] for r in timeout_runs)} timeout errors**: {details}. The failed harness result's visible unresolved status is not counted as a successful abstention.", ""]
    all_usage = results["accounting"]["conditions"]
    if any(all_usage[arm]["total_tokens"] is None for arm in CONDITIONS):
        lines += [f"Across all eight cases, known usage is **{all_usage['direct']['known_total_tokens']:,} tokens for Astra alone** and **{all_usage['double_loop']['known_total_tokens']:,} for the harness**. These are lower bounds: timed-out calls have unknown usage, so both aggregate total-token fields remain null. No all-case token ratio is reported; the comparison above uses the fully known named-case totals.", ""]
    discrepancies = [r for r in results["runs"] if r["clock_discrepancy"]]
    if discrepancies:
        lines += [f"The timing audit flags wall-clock/monotonic discrepancies in {len(discrepancies)} runs. Those flags are retained; no end-to-end latency advantage is inferred from these measurements.", ""]
    for run in results["runs"]:
        if run["locally_audited_offset_only_year_flags"]:
            numbers = ", ".join(run["locally_audited_offset_only_year_flags"])
            lines += [f"The registered broad year screen for {run['case_id']} / {run['condition']} flagged {numbers}. Local inspection identifies this as a citation offset rather than later-year prose. The raw screen flag remains unchanged; this annotation is a post-run clarification, not proof that learned knowledge was absent.", ""]
    lines += ["## What the cases test", "",
        "The Osaka authenticity target asks whether the immunoblots in Figures 5B–5D came from the samples and experimental conditions stated in the caption. Its control asks whether that caption describes the blots as representing two independent experiments. The [2023 article](https://doi.org/10.1073/pnas.2308260120) supplies the historical text. The [2025 institutional investigation](https://www.osaka-u.ac.jp/ja/news/topics/2025/02/files/4h3a9t/@@download/file) identifies those panels as fabricated using different samples; the [paper retraction](https://doi.org/10.1073/pnas.2501149122) is additional later evidence. This does not establish that the biological mechanism itself is false.", "",
        "The wastewater authenticity target asks whether all reported measurements came from the study's stated sampling and analysis procedures. Its control asks whether the abstract reports final-effluent colloidal fractions of 52% Cu, 32% Pb, 44% Ni and 68% Zn. The [2017 article](https://doi.org/10.1016/j.chemosphere.2017.02.034) supplies the historical text. The [publisher notice](https://www.sciencedirect.com/science/article/abs/pii/S0045653517302126) records the first author's fabrication admission, with a [separate 2025 retraction notice](https://doi.org/10.1016/j.chemosphere.2025.144440). This contradicts the universal authenticity claim, without establishing that every value or environmental conclusion is false.", "",
        "## Tokens by recorded stage", "",
        "| Arm | Stage | Attempts | Calls with known usage | Known input tokens | Known output tokens | Known total tokens |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for stage in results["accounting"]["stages"]:
        arm = "Astra alone" if stage["condition"] == "direct" else "Astra + harness"
        lines.append(f"| {arm} | {stage['stage']} | {stage['attempts']} | {stage['known_usage_calls']} | {stage['known_input_tokens']} | {stage['known_output_tokens']} | {stage['known_total_tokens']} |")
    lines += ["", "Stage accounting includes all eight cases and every recorded attempt. Decomposition and verification stages are shown separately; a stage's token cost does not establish the benefit of a loop. The loop counts above come from the local operation-history audit, which cannot be reproduced from source-free receipts alone.", ""]
    lines += [
        "A cutoff match answers what the supplied evidence established by 2023-12-31. Later-world agreement is a separate descriptive measure. **Abstention is not preemptive detection of fabrication.** A later-correct rejection can still be unsupported by the historical packet. Failed or invalid runs receive no successful-abstention credit and remain in every scheduled denominator.", "",
        "The authenticity targets are curator formulations of implied data-authenticity claims. The controls ask what the papers reported; they are not controls establishing genuine experimental data. Both event families were selected using later fabrication findings. Two correlated event families cannot establish general accuracy or fraud-detection superiority.", "",
        "Each finite source pool consists of extracted text from a retained historical PDF and an excerpt from that same text, not two independent sources. Astra alone receives the entire allowed pool immediately; the harness starts from the excerpt and retrieves from that pool. The wastewater packet contains all extracted text from the retained 18-page accepted-manuscript PDF, which ends in references; referenced table and figure sheets are absent from the text packet. This limitation is retained with the registered results, without rerunning or changing their labels. Calls and tokens are not equalized. Every logical attempt, including failed calls and available usage, is retained; internal CLI transport retries are not separately counted.", "",
        "This text-only test does not assess image forensics. Identity masking cannot erase learned knowledge; absence of an explicit future-year reference cannot prove that pretrained knowledge was unused. The primary metadata and held-out 2025 findings are listed in [SOURCES.json](SOURCES.json). Exact earliest public disclosure for the wastewater finding is uncertain, and the Osaka investigation began privately in 2024.", "",
        "[RESULTS.json](RESULTS.json) contains the sixteen categorical/numeric run rows and scores. [RECEIPTS.json](RECEIPTS.json) preserves all call accounting. [MANIFEST.json](MANIFEST.json) binds the public files and source archive hashes. No source passages, model rationale, prompts, raw responses or local/session identifiers are included. Source and response hashes cannot independently establish semantic entailment or the locally audited quote/loop claims.", "",
        "From a fresh public checkout:", "", "```sh", "python3 tools/export_historical_evaluation.py --verify-public", "```", "",
        "This verifies hashes, all eight-by-two scheduled outcomes, row flags, error/call denominators and token totals without private artifacts or model calls. It does not rerun inference or independently verify the omitted source text.", ""]
    return "\n".join(lines)


def privacy_scan(text):
    require(not re.search(r'/Users/|/private/var/|/home/|jsessionid|"(?:session_id|thread_id|conversation_id|rationale|quote|prompt|final_output|packet)"|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', text, re.I), "Excluded private/source/model content in export")


def export(archive=ARCHIVE, public=PUBLIC):
    archive, public = Path(archive), Path(public)
    folder = archive / "results"
    require((folder / "SUMMARY.json").is_file() and (folder / "SANITIZED_RECEIPTS.json").is_file(), "Finished scoring artifacts are required; no provisional or guessed outputs are exported")
    summary, raw_receipts = read(folder / "SUMMARY.json"), read(folder / "SANITIZED_RECEIPTS.json")
    results, receipts = build_results(summary, raw_receipts)
    sources = source_rows(archive)
    verify_data(results, receipts, sources)
    documents = {"RESULTS.json": results, "RECEIPTS.json": receipts, "SOURCES.json": sources,
                 "README.md": render_readme(results)}
    for value in documents.values():
        privacy_scan(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    public.mkdir(parents=True, exist_ok=True)
    for name, value in documents.items():
        write(public / name, value)
    manifest = {"schema_version": 1, "case_count": 8, "run_count": 16, "event_family_count": 2,
                "public_receipt_count": len(receipts["receipts"]), "source_metadata_count": 8,
                "raw_sources_bundled": False, "model_prose_or_prompts_bundled": False,
                "exporter_sha256": digest(Path(__file__)),
                "local_archive_sha256": {"summary": digest(folder / "SUMMARY.json"),
                    "sanitized_receipts": digest(folder / "SANITIZED_RECEIPTS.json"),
                    "source_candidates": digest(archive / "private/candidates-primary.json")},
                "public_file_sha256": {name: digest(public / name) for name in PUBLIC_FILES}}
    write(public / "MANIFEST.json", manifest)
    return verify_public(public)


def verify_public(public=PUBLIC):
    public = Path(public)
    manifest = read(public / "MANIFEST.json")
    exact_keys(manifest, ("schema_version", "case_count", "run_count", "event_family_count", "public_receipt_count", "source_metadata_count", "raw_sources_bundled", "model_prose_or_prompts_bundled", "exporter_sha256", "local_archive_sha256", "public_file_sha256"), "Unexpected manifest fields")
    require(manifest["schema_version"] == 1 and manifest["raw_sources_bundled"] is False and manifest["model_prose_or_prompts_bundled"] is False, "Public export scope differs")
    exact_keys(manifest["public_file_sha256"], PUBLIC_FILES, "Public file inventory differs")
    exact_keys(manifest["local_archive_sha256"], ("summary", "sanitized_receipts", "source_candidates"), "Unexpected local archive hash fields")
    require(all(valid_hash(h) for h in manifest["local_archive_sha256"].values()), "Invalid local archive hash")
    require(digest(Path(__file__)) == manifest["exporter_sha256"], "Exporter differs from manifest")
    for name, expected in manifest["public_file_sha256"].items():
        require(valid_hash(expected) and digest(public / name) == expected, "Public artifact hash differs")
        privacy_scan((public / name).read_text())
    privacy_scan(json.dumps(manifest))
    results, receipts, sources = (read(public / name) for name in ("RESULTS.json", "RECEIPTS.json", "SOURCES.json"))
    verified = verify_data(results, receipts, sources)
    require((manifest["case_count"], manifest["run_count"], manifest["event_family_count"], manifest["source_metadata_count"])
            == (8, 16, 2, 8) and manifest["public_receipt_count"] == len(receipts["receipts"]), "Manifest denominators differ")
    require((public / "README.md").read_text() == render_readme(results), "README accounting differs from published rows")
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-public", action="store_true")
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--public-dir", type=Path, default=PUBLIC)
    args = parser.parse_args()
    result = verify_public(args.public_dir) if args.verify_public else export(args.archive, args.public_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
