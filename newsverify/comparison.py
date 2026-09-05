"""Paired, event-cluster comparisons of already-produced predictions.

Runs must declare matching model/corpus and per-target resource ceilings, with
complete usage logs. This checks those declarations; it does not execute models
or independently attest their usage. Synthetic comparisons prove no live gain.
"""
from copy import deepcopy
from collections import defaultdict
import random

from .evaluation import evaluate

RESOURCES = ("retrieval_calls", "model_tokens", "wall_seconds")


def _run_contract(payload):
    run = payload.get("run")
    if not isinstance(run, dict):
        raise ValueError("comparison requires run metadata")
    for key in ("name", "model_id", "corpus_id"):
        if not isinstance(run.get(key), str) or not run[key].strip():
            raise ValueError(f"run.{key} is required")
    budget = run.get("per_target_budget")
    if not isinstance(budget, dict) or set(budget) != set(RESOURCES):
        raise ValueError("run requires all three per-target budget ceilings")
    for key, value in budget.items():
        if type(value) not in (int, float) or not 0 < value < float("inf"):
            raise ValueError("budgets must be finite positive numbers")
        if key != "wall_seconds" and type(value) is not int:
            raise ValueError("call and token ceilings must be integers")
    for case in payload["cases"]:
        usage = case.get("usage")
        if not isinstance(usage, dict) or set(usage) != set(RESOURCES):
            raise ValueError("each prediction needs complete usage logs")
        for key, value in usage.items():
            if type(value) not in (int, float) or not 0 <= value <= budget[key]:
                raise ValueError(f"invalid or exceeded usage for {key}")
            if key != "wall_seconds" and type(value) is not int:
                raise ValueError("call and token usage must be integers")
    return run


def _values(report):
    result = {k: v["value"] for k, v in report["metrics"].items()}
    result.update({k: v["value"] for k, v in report["diagnostics"].items()})
    result["NVScore"] = report["aggregate"]["value"]
    return result


def _quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _rename_target(case, name):
    original = case["id"]
    case["id"] = name
    for edge in case["source"].get("valid_edges", case["source"].get("edges", [])):
        for side in ("from", "to"):
            if edge[side] == original:
                edge[side] = name
    return case


def compare(gold, baseline, candidate, bootstrap_samples=500, seed=0):
    if type(bootstrap_samples) is not int or not 20 <= bootstrap_samples <= 10000:
        raise ValueError("bootstrap_samples must be an integer from 20 to 10000")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    first, second = evaluate(gold, baseline), evaluate(gold, candidate)
    run_a, run_b = _run_contract(baseline), _run_contract(candidate)
    for key in ("model_id", "corpus_id", "per_target_budget"):
        if run_a[key] != run_b[key]:
            raise ValueError(f"comparison requires matching {key}")
    groups = defaultdict(list)
    for case in gold["cases"]:
        groups[case["event_id"]].append(case)
    a_index = {c["id"]: c for c in baseline["cases"]}
    b_index = {c["id"]: c for c in candidate["cases"]}
    values_a, values_b = _values(first), _values(second)
    samples = {key: [] for key in values_a}
    rng = random.Random(seed)
    event_ids = list(groups)
    if len(groups) > 1:
        for _ in range(bootstrap_samples):
            sampled_gold, sampled_a, sampled_b = [], [], []
            for draw, event in enumerate(rng.choices(event_ids, k=len(event_ids))):
                for case in groups[event]:
                    unique = f"bootstrap-{draw}:{case['id']}"
                    sampled_gold.append(_rename_target(deepcopy(case), unique))
                    sampled_a.append(_rename_target(deepcopy(a_index[case["id"]]), unique))
                    sampled_b.append(_rename_target(deepcopy(b_index[case["id"]]), unique))
            scores_a = _values(evaluate(dict(gold, cases=sampled_gold), dict(baseline, cases=sampled_a)))
            scores_b = _values(evaluate(dict(gold, cases=sampled_gold), dict(candidate, cases=sampled_b)))
            for key in samples:
                if scores_a[key] is not None and scores_b[key] is not None:
                    samples[key].append(scores_b[key] - scores_a[key])
    differences = {}
    for key, draws in samples.items():
        complete = len(draws) == bootstrap_samples
        differences[key] = {
            "baseline": values_a[key], "candidate": values_b[key],
            "delta": values_b[key] - values_a[key] if values_a[key] is not None and values_b[key] is not None else None,
            "event_bootstrap95": [_quantile(draws, .025), _quantile(draws, .975)] if complete else None,
            "valid_bootstrap_samples": len(draws),
            "interval_status": "computed" if complete else "insufficient_events_or_undefined_resample_metrics",
            "preferred_direction": "lower" if key in {"HFAR", "unknown_source_false_promotion", "ECE10"} else "higher",
        }
    return {
        "dataset_kind": gold["dataset_kind"], "declared_budgets_match": True,
        "model_id": run_a["model_id"], "corpus_id": run_a["corpus_id"],
        "per_target_budget": run_a["per_target_budget"],
        "baseline_name": run_a["name"], "candidate_name": run_b["name"],
        "bootstrap_samples": bootstrap_samples, "seed": seed, "event_count": len(groups),
        "differences": differences,
        "conclusion": "synthetic_no_realworld_claim" if gold["dataset_kind"] == "synthetic" else "requires_predeclared_gate_and_adjudication_review",
        "limitations": [
            "Matching declared budgets and usage is not independent verification of real model execution.",
            "Intervals are unadjusted exploratory event-cluster percentile intervals, not a simultaneous seven-metric claim.",
            "Any undefined bootstrap resample suppresses that interval; no silent conditional resampling.",
            "A small number of events or handwritten predictions cannot demonstrate deployment readiness.",
        ],
    }
