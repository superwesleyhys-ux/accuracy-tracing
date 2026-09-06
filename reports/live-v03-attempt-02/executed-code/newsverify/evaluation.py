"""Fixed-target evaluation against separately supplied, adjudicated gold labels.

This module measures predictions. It does not generate truth/source labels, run
a model, or turn synthetic arithmetic checks into real-world accuracy claims.
"""
from __future__ import annotations

import math
from collections import Counter
from itertools import combinations
from typing import Any

from .core import _timestamp

LABELS = ("true", "false", "disputed", "unverifiable")
STANCES = {"supports", "contradicts", "neutral"}
RELATIONS = {"cites", "quotes", "derived_from", "translated_from", "revised_from"}
WEIGHTS = {"VP": .25, "FR": .20, "TR": .15, "SR": .15, "EN": .15, "CA": .10}


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _list(value: Any, name: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _index(items: Any, name: str) -> dict[str, dict]:
    result = {}
    for item in _list(items, name):
        if not isinstance(item, dict):
            raise ValueError(f"{name} entries must be dictionaries")
        key = _text(item.get("id"), f"{name}.id")
        if key in result:
            raise ValueError(f"duplicate {name} id: {key}")
        result[key] = item
    return result


def _edges(value: Any, name: str) -> set[tuple[str, str, str]]:
    edges = set()
    for edge in _list(value, name):
        if not isinstance(edge, dict):
            raise ValueError(f"{name} entries must be dictionaries")
        key = tuple(_text(edge.get(k), f"{name}.{k}") for k in ("from", "to", "relation"))
        if key[2] not in RELATIONS:
            raise ValueError(f"{name}: unsupported provenance relation {key[2]}")
        if key in edges:
            raise ValueError(f"{name}: duplicate edge")
        edges.add(key)
    return edges


def _roots(value: Any, name: str) -> frozenset[str]:
    items = [_text(x, name) for x in _list(value, name)]
    if len(items) != len(set(items)):
        raise ValueError(f"{name}: duplicate root")
    return frozenset(items)


def _reachable(start: str, edges: set[tuple[str, str, str]]) -> set[str]:
    seen, frontier = {start}, [start]
    while frontier:
        node = frontier.pop()
        for origin, destination, _ in edges:
            if origin == node and destination not in seen:
                seen.add(destination)
                frontier.append(destination)
    return seen


def ratio(successes: int, total: int) -> dict:
    """Binomial ratio with a 95% Wilson reference interval; zero denominator is N/A."""
    if type(successes) is not int or type(total) is not int or not 0 <= successes <= total:
        raise ValueError("ratio requires integer counts with 0 <= successes <= total")
    if total == 0:
        return {"value": None, "numerator": successes, "denominator": 0, "wilson95": None}
    p, z = successes / total, 1.959963984540054
    div = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / div
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / div
    return {"value": p, "numerator": successes, "denominator": total,
            "wilson95": [max(0., centre - radius), min(1., centre + radius)]}


def _probabilities(raw: Any) -> dict[str, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != set(LABELS):
        raise ValueError("probabilities require exactly the four truth labels")
    if any(type(x) not in (float, int) or not 0 <= x <= 1 or not math.isfinite(x)
           for x in raw.values()):
        raise ValueError("probabilities must be finite numbers between zero and one")
    if not math.isclose(sum(raw.values()), 1, abs_tol=1e-9, rel_tol=0):
        raise ValueError("probabilities must sum to one")
    return {k: float(raw[k]) for k in LABELS}


def evaluate(gold: dict, predictions: dict) -> dict:
    """Compute all seven named metrics and diagnostics on the fixed gold case set.

    Unknown evidence IDs require adjudication and are rejected, never silently
    treated as true, false, or dropped. Missing case IDs also invalidate the run.
    Material IDs in this evaluation schema identify pre-adjudicated snapshots.
    """
    if not isinstance(gold, dict) or not isinstance(predictions, dict):
        raise ValueError("gold and predictions must be dictionaries")
    if gold.get("schema_version") != 1 or predictions.get("schema_version") != 1:
        raise ValueError("evaluation schema_version must be 1")
    if gold.get("dataset_kind") not in {"synthetic", "reviewed"}:
        raise ValueError("dataset_kind must be synthetic or reviewed")
    cases = _index(gold.get("cases"), "gold cases")
    outputs = _index(predictions.get("cases"), "prediction cases")
    if not cases or cases.keys() != outputs.keys():
        raise ValueError("predictions must contain exactly the nonempty fixed gold case set")
    counts = Counter()
    brier_terms, calibrations, rows = [], [], []
    confusion = {label: {other: 0 for other in LABELS} for label in LABELS}
    events = set()
    for identifier, case in cases.items():
        output = outputs[identifier]
        events.add(_text(case.get("event_id"), "event_id"))
        cutoff = _text(case.get("as_of"), "as_of")
        _timestamp(cutoff, "as_of")
        if output.get("as_of") != cutoff:
            raise ValueError(f"{identifier}: prediction and gold cutoffs must match exactly")
        truth, decision = case.get("truth"), output.get("decision")
        if truth not in LABELS or decision not in LABELS:
            raise ValueError("truth and decision require a four-state label")
        if type(case.get("high_risk")) is not bool:
            raise ValueError("high_risk must be boolean")
        confusion[truth][decision] += 1
        admitted = decision == "true"
        counts["accepted"] += admitted
        counts["true"] += truth == "true"
        counts["accepted_true"] += admitted and truth == "true"
        counts["false"] += truth == "false"
        counts["blocked_false"] += not admitted and truth == "false"
        high_false = case["high_risk"] and truth == "false"
        counts["high_false"] += high_false
        counts["accepted_high_false"] += admitted and high_false
        counts["correct_label"] += decision == truth
        counts["false_identified"] += truth == decision == "false"

        source, predicted_source = case.get("source"), output.get("source")
        if not isinstance(source, dict) or not isinstance(predicted_source, dict):
            raise ValueError("each case requires source objects")
        if type(source.get("traceable")) is not bool:
            raise ValueError("source.traceable must be boolean")
        alternatives = [_roots(x, "acceptable_root_sets") for x in
                        _list(source.get("acceptable_root_sets"), "acceptable_root_sets")]
        if source["traceable"] != bool(alternatives) or any(not x for x in alternatives):
            raise ValueError("traceable sources need nonempty acceptable root sets; untraceable ones need none")
        expected_edges = _edges(source.get("valid_edges"), "gold edges")
        if any(identifier in roots or not roots <= _reachable(identifier, expected_edges)
               for roots in alternatives):
            raise ValueError("gold original roots need an annotated path from the target")
        predicted_edges = _edges(predicted_source.get("edges"), "predicted edges")
        roots = _roots(predicted_source.get("roots"), "predicted roots")
        status = predicted_source.get("status")
        if status not in {"resolved", "earliest_accessible", "unresolved"}:
            raise ValueError("invalid provenance status")
        if status != "resolved" and roots:
            raise ValueError("only resolved provenance may report confirmed original roots")
        resolved = status == "resolved"
        if resolved and not roots:
            raise ValueError("resolved provenance must report roots")
        source_correct = (resolved and source["traceable"] and roots in alternatives
                          and predicted_edges <= expected_edges
                          and roots <= _reachable(identifier, predicted_edges))
        counts["traceable"] += source["traceable"]
        counts["source_correct"] += source_correct
        counts["source_resolved"] += resolved
        counts["untraceable"] += not source["traceable"]
        counts["false_root"] += resolved and not source["traceable"]
        counts["edges_correct"] += len(predicted_edges & expected_edges)
        counts["edges_predicted"] += len(predicted_edges)
        counts["edges_gold"] += len(expected_edges)

        expected_evidence = _index(case.get("evidence"), "gold evidence")
        supplied_evidence = _index(output.get("evidence"), "predicted evidence")
        if supplied_evidence.keys() - expected_evidence.keys():
            raise ValueError("unjudged evidence IDs require gold adjudication before scoring")
        for record in expected_evidence.values():
            if record.get("stance") not in STANCES:
                raise ValueError("invalid gold evidence stance")
            _text(record.get("origin"), "gold evidence origin")
            counts["gold_supports"] += record["stance"] == "supports"
        for key, record in supplied_evidence.items():
            if record.get("stance") not in STANCES:
                raise ValueError("invalid predicted evidence stance")
            _text(record.get("origin"), "predicted evidence origin")
            counts["evidence_reported"] += 1
            correct = record["stance"] == expected_evidence[key]["stance"]
            counts["stance_correct"] += correct
            if record["stance"] == "supports":
                counts["support_claims"] += 1
                counts["support_correct"] += correct
        for left, right in combinations(expected_evidence, 2):
            same = expected_evidence[left]["origin"] == expected_evidence[right]["origin"]
            joined = (left in supplied_evidence and right in supplied_evidence and
                      supplied_evidence[left]["origin"] == supplied_evidence[right]["origin"])
            counts["duplicate_tp"] += same and joined
            counts["duplicate_fp"] += joined and not same
            counts["duplicate_fn"] += same and not joined
        probabilities = _probabilities(output.get("probabilities"))
        if probabilities is not None:
            brier_terms.append(sum((probabilities[label] - int(label == truth)) ** 2 for label in LABELS))
            top = max(LABELS, key=lambda label: probabilities[label])
            calibrations.append((probabilities[top], int(top == truth)))
        rows.append({"id": identifier, "event_id": case["event_id"], "truth": truth,
                     "decision": decision, "source_correct": bool(source_correct),
                     "provenance_status": status})

    metrics = {
        "VP": ratio(counts["accepted_true"], counts["accepted"]),
        "FR": ratio(counts["blocked_false"], counts["false"]),
        "TR": ratio(counts["accepted_true"], counts["true"]),
        "SR": ratio(counts["source_correct"], counts["traceable"]),
        "EN": ratio(counts["support_correct"], counts["support_claims"]),
        "HFAR": ratio(counts["accepted_high_false"], counts["high_false"]),
    }
    brier = sum(brier_terms) / len(cases) if len(brier_terms) == len(cases) else None
    metrics["CA"] = {"value": None if brier is None else 1 - brier / 2,
                     "brier_multiclass": brier, "probability_cases": len(brier_terms),
                     "required_cases": len(cases),
                     "note": "Normalized Brier quality; calibration plus discrimination, not calibration alone."}
    bins = [{"count": 0, "confidence_sum": 0., "correct_sum": 0} for _ in range(10)]
    for confidence, correct in calibrations:
        group = bins[min(9, int(confidence * 10))]
        group["count"] += 1
        group["confidence_sum"] += confidence
        group["correct_sum"] += correct
    ece = (sum(abs(b["confidence_sum"] - b["correct_sum"]) for b in bins) / len(cases)
           if len(calibrations) == len(cases) else None)
    duplicate_denominator = 2 * counts["duplicate_tp"] + counts["duplicate_fp"] + counts["duplicate_fn"]
    diagnostics = {
        "source_precision": ratio(counts["source_correct"], counts["source_resolved"]),
        "unknown_source_false_promotion": ratio(counts["false_root"], counts["untraceable"]),
        "edge_precision": ratio(counts["edges_correct"], counts["edges_predicted"]),
        "annotated_edge_recall": ratio(counts["edges_correct"], counts["edges_gold"]),
        "evidence_support_recall": ratio(counts["support_correct"], counts["gold_supports"]),
        "stance_accuracy": ratio(counts["stance_correct"], counts["evidence_reported"]),
        "false_identification_recall": ratio(counts["false_identified"], counts["false"]),
        "classification_accuracy": ratio(counts["correct_label"], len(cases)),
        "admission_coverage": ratio(counts["accepted"], len(cases)),
        "duplicate_pair_f1": {"value": 2 * counts["duplicate_tp"] / duplicate_denominator
                              if duplicate_denominator else None,
                              "tp": counts["duplicate_tp"], "fp": counts["duplicate_fp"],
                              "fn": counts["duplicate_fn"]},
        "ECE10": {"value": ece, "bins": bins},
    }
    missing = [key for key in (*WEIGHTS, "HFAR") if metrics[key]["value"] is None]
    score = None if missing else 100 * math.prod(metrics[key]["value"] ** weight
                                               for key, weight in WEIGHTS.items()) * (1 - metrics["HFAR"]["value"]) ** 2
    return {
        "schema_version": 1, "dataset_kind": gold["dataset_kind"],
        "case_count": len(cases), "event_count": len(events), "metrics": metrics,
        "diagnostics": diagnostics, "confusion_matrix": confusion,
        "aggregate": {"name": "NVScore-v0.2-experimental", "value": score,
                      "weights": WEIGHTS, "missing_metrics": missing,
                      "status": "not_computable" if missing else "computed",
                      "official_benchmark": False},
        "limitations": [
            "Gold labels must be separately adjudicated at the stated evidence cutoff.",
            "Synthetic results validate arithmetic and contracts, not real-news accuracy.",
            "Wilson intervals are per-unit binomial references; correlated cases require event-cluster analysis.",
            "NVScore weights are provisional design choices, not validated or official acceptance thresholds.",
            "A computed aggregate is not a deployment gate; inspect coverage, false roots, duplication and high-risk errors.",
        ], "cases": rows,
    }
