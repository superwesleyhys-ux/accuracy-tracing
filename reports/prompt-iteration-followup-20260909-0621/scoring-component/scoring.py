"""Pure, offline scoring of declared audited outcomes; no evidence admission.

This module never reads sources, labels from disk, model output, or token usage.
The integration caller must independently establish every audit/admission claim.
"""
from __future__ import annotations

import re


VERDICTS = frozenset({"supported", "contradicted", "unresolved", "conflicting"})
CONDITIONS = ("direct", "news_tracing")
BATCH_STATUSES = frozenset({"completed", "fatal_worker_failure"})
_LABEL_FIELDS = frozenset({"case_id", "assertion_scope", "cutoff_expected",
                           "future_expected", "independently_adjudicated"})
_ROW_FIELDS = frozenset({"case_id", "condition", "execution_status", "audit_passed",
                         "pipeline_valid", "formal_valid", "observed_verdict", "formal_verdict"})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _object(value, fields, message):
    _require(type(value) is dict and set(value) == set(fields), message)


def _member(value, allowed):
    return type(value) is str and value in allowed


def _verdict(value):
    return value is None or _member(value, VERDICTS)


def validate_plan(plan):
    """Return the four prescribed row keys; labels never determine arm order."""
    _object(plan, {"schema_version", "case_ids", "conditions", "arm_order"},
            "Plan fields differ from the paired contract")
    _require(type(plan["schema_version"]) is int and plan["schema_version"] == 1,
             "Invalid plan schema version")
    ids = plan["case_ids"]
    _require(type(ids) is list and len(ids) == 2 and all(
        type(cid) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", cid)
        for cid in ids) and len(set(ids)) == 2, "Plan needs two distinct opaque case IDs")
    _require(type(plan["conditions"]) is list and plan["conditions"] == list(CONDITIONS),
             "Both conditions are required in the fixed order")
    _require(_member(plan["arm_order"], {"alternating"}), "Unsupported arm order")
    return [(cid, arm) for index, cid in enumerate(ids)
            for arm in (CONDITIONS if index % 2 == 0 else tuple(reversed(CONDITIONS)))]


def _labels(labels, case_ids):
    _object(labels, {"schema_version", "cases"}, "Label container fields differ")
    _require(type(labels["schema_version"]) is int and labels["schema_version"] == 1,
             "Invalid label schema version")
    rows = labels["cases"]
    _require(type(rows) is list and len(rows) == len(case_ids), "Label denominator differs")
    for row in rows:
        _object(row, _LABEL_FIELDS, "Unexpected or missing label fields")
        _require(type(row["case_id"]) is str, "Invalid label case ID")
        _require(_member(row["assertion_scope"], {"real_world", "attribution"}),
                 "Unknown assertion scope")
        _require(_member(row["cutoff_expected"], VERDICTS), "Unknown cutoff label")
        _require(_member(row["future_expected"], {"supported", "contradicted"}),
                 "A settled independently adjudicated future label is required")
        _require(row["independently_adjudicated"] is True,
                 "Independent adjudication declaration is required")
    _require([row["case_id"] for row in rows] == case_ids,
             "Label IDs must exactly match the ordered plan")
    return {row["case_id"]: row for row in rows}


def _validate_rows(outcomes, keys, batch_status):
    _require(type(outcomes) is list and len(outcomes) == len(keys),
             "All four planned outcome rows are required")
    for row in outcomes:
        _object(row, _ROW_FIELDS, "Unexpected or missing outcome fields")
        _require(type(row["case_id"]) is str and _member(row["condition"], CONDITIONS),
                 "Invalid outcome identity")
        _require(_member(row["execution_status"], {"completed", "failed", "unexecuted"}),
                 "Unknown execution status")
        _require(row["audit_passed"] is True, "A prior audit declaration is required")
        _require(type(row["pipeline_valid"]) is bool and type(row["formal_valid"]) is bool,
                 "Validity flags must be booleans")
        observed, formal = row["observed_verdict"], row["formal_verdict"]
        _require(_verdict(observed) and _verdict(formal), "Unknown or malformed verdict")
        _require(observed is None or formal is None or observed == formal,
                 "Observed and formal verdicts disagree")
        if row["formal_valid"]:
            _require(formal is not None, "A valid formal result requires a verdict")
        if row["pipeline_valid"]:
            _require(row["execution_status"] == "completed" and row["formal_valid"]
                     and observed is not None and observed == formal,
                     "Primary validity contradicts the retained execution/formal result")
        if row["execution_status"] == "unexecuted":
            _require(batch_status == "fatal_worker_failure", "Unexecuted rows require a fatal batch")
            _require(not row["pipeline_valid"] and not row["formal_valid"]
                     and observed is None and formal is None,
                     "An unexecuted row cannot contain a result or valid flags")
    _require([(row["case_id"], row["condition"]) for row in outcomes] == keys,
             "Outcome IDs/conditions are missing, duplicated or reordered")


def _stratum(label):
    if label["assertion_scope"] == "attribution":
        return "attribution"
    return "real_world_false" if label["future_expected"] == "contradicted" else "real_world_true"


def _counts(rows):
    return {key: sum(row["classification"] == key for row in rows)
            for key in ("supported", "contradicted", "unresolved", "conflicting", "failed_or_invalid")}


def _primary(rows, available):
    count = len(rows)
    cutoff = sum(row["row_cutoff_match"] for row in rows)
    future = sum(row["row_future_match"] for row in rows)
    return {"available": available, "denominator": count,
            "cutoff_matches": cutoff if available else None,
            "future_matches": future if available else None,
            "cutoff_match_rate": cutoff / count if available and count else None,
            "future_match_rate": future / count if available and count else None}


def score(plan, outcomes, labels, *, batch_status):
    """Score two paired cases from declarations supplied by a trusted caller.

    ``completed`` means the batch finished, including ordinary recorded failures.
    ``fatal_worker_failure`` suppresses all primary aggregates/rates while keeping
    the entire planned denominator and recorded row/formal diagnostics. It may
    contain explicit unexecuted rows, with null verdicts and false validity flags.
    None of these flags proves source admission, isolation or request integrity.
    """
    _require(_member(batch_status, BATCH_STATUSES), "Unknown batch status")
    keys = validate_plan(plan)
    label_map = _labels(labels, plan["case_ids"])
    _validate_rows(outcomes, keys, batch_status)
    available = batch_status == "completed"
    rows = []
    for outcome in outcomes:
        label = label_map[outcome["case_id"]]
        valid, formal_valid = outcome["pipeline_valid"], outcome["formal_valid"]
        observed, formal = outcome["observed_verdict"], outcome["formal_verdict"]
        false_claim = _stratum(label) == "real_world_false"
        called_false = bool(valid and false_claim and observed == "contradicted")
        rows.append({**outcome, "assertion_scope": label["assertion_scope"],
            "truth_stratum": _stratum(label), "cutoff_expected": label["cutoff_expected"],
            "future_expected": label["future_expected"],
            "classification": observed if valid else "failed_or_invalid",
            "row_cutoff_match": bool(valid and observed == label["cutoff_expected"]),
            "row_future_match": bool(valid and observed == label["future_expected"]),
            "row_settled_cutoff_mismatch": bool(valid and observed in {"supported", "contradicted"}
                                                 and observed != label["cutoff_expected"]),
            "formal_cutoff_match": bool(formal_valid and formal == label["cutoff_expected"]),
            "formal_future_match": bool(formal_valid and formal == label["future_expected"]),
            "row_called_later_false_claim_false": called_false,
            "row_cutoff_grounded_false_call": bool(called_false and label["cutoff_expected"] == "contradicted"),
            "row_false_acceptance": bool(valid and false_claim and observed == "supported"),
            "row_true_control_false_accusation": bool(valid and _stratum(label) == "real_world_true"
                                                       and observed == "contradicted")})
    conditions = {}
    for arm in CONDITIONS:
        selected = [row for row in rows if row["condition"] == arm]
        strata = {}
        for name in ("real_world_false", "real_world_true", "attribution"):
            members = [row for row in selected if row["truth_stratum"] == name]
            counts = _counts(members)
            metrics = {"abstentions": counts["unresolved"], "conflicts": counts["conflicting"],
                       "failed_or_invalid": counts["failed_or_invalid"]}
            if name == "real_world_false":
                metrics.update(called_false=counts["contradicted"], false_acceptances=counts["supported"],
                    cutoff_grounded_false_calls=sum(row["row_cutoff_grounded_false_call"] for row in members))
            elif name == "real_world_true":
                metrics.update(true_acceptances=counts["supported"], false_accusations=counts["contradicted"])
            else:
                metrics.update(supported=counts["supported"], contradicted=counts["contradicted"])
            strata[name] = {"cases": len(members), "primary": _primary(members, available),
                "metrics_available": available,
                "metrics": {key: value if available else None for key, value in metrics.items()},
                "recorded_settled_cutoff_mismatches": sum(row["row_settled_cutoff_mismatch"] for row in members),
                "recorded_outcome_diagnostics": counts}
        conditions[arm] = {"planned_rows": len(selected), "primary": _primary(selected, available),
            "execution_status_counts": {status: sum(row["execution_status"] == status for row in selected)
                                        for status in ("completed", "failed", "unexecuted")},
            "recorded_outcome_diagnostics": _counts(selected),
            "recorded_settled_cutoff_mismatches": sum(row["row_settled_cutoff_mismatch"] for row in selected),
            "formal_diagnostic": {"denominator": len(selected),
                "valid_rows": sum(row["formal_valid"] for row in selected),
                "cutoff_matches": sum(row["formal_cutoff_match"] for row in selected),
                "future_matches": sum(row["formal_future_match"] for row in selected)},
            "truth_strata": strata}
    return {"schema_version": 1, "batch_status": batch_status,
        "primary_comparison_available": available, "case_count": len(plan["case_ids"]),
        "planned_rows": len(keys), "conditions": conditions, "rows": rows,
        "scope": {"offline_component_only": True, "admission_or_request_audit_proved": False,
                  "row_flags_are_diagnostics_when_batch_is_fatal": True,
                  "token_accounting_included": False, "superiority_established": False}}
