#!/usr/bin/env python3
"""Score the immutable system holdout after sealed labels are revealed."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def call_usage(rows: list[dict]) -> dict:
    calls = [call for row in rows for call in (row.get("calls") or [])]
    known = []
    for call in calls:
        usage = call.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
        if type(input_tokens) is int and type(output_tokens) is int:
            known.append((input_tokens, output_tokens))
    complete = bool(calls) and len(known) == len(calls)
    return {
        "calls": len(calls),
        "successful_calls": sum(call.get("success") is True for call in calls),
        "known_usage_calls": len(known),
        "usage_complete": complete,
        "input_tokens": sum(item[0] for item in known) if complete else None,
        "output_tokens": sum(item[1] for item in known) if complete else None,
        "total_tokens": sum(sum(item) for item in known) if complete else None,
    }


def score_arm(rows: list[dict], gold: dict[str, dict], packets: dict[str, dict]) -> tuple[dict, list[dict]]:
    scored = []
    for row in rows:
        case_id = row["case_id"]
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        valid_ids = {item["id"] for item in packets[case_id]["evidence_passages"]}
        cited = result.get("evidence_passage_ids")
        evidence_valid = (
            row.get("status") == "completed"
            and isinstance(cited, list)
            and bool(cited)
            and len(cited) == len(set(cited))
            and all(item in valid_ids for item in cited)
        )
        predicted = result.get("risk") if evidence_valid else None
        expected = gold[case_id]["expected_risk"]
        correct = predicted == expected
        scored.append({
            "case_id": case_id,
            "expected": expected,
            "predicted": predicted,
            "confidence": result.get("confidence"),
            "evidence_valid": evidence_valid,
            "correct": correct,
        })
    tp = sum(item["expected"] == "elevated" and item["predicted"] == "elevated" for item in scored)
    tn = sum(item["expected"] == "ordinary" and item["predicted"] == "ordinary" for item in scored)
    positives = sum(item["expected"] == "elevated" for item in scored)
    negatives = sum(item["expected"] == "ordinary" for item in scored)
    sensitivity = tp / positives
    specificity = tn / negatives
    metrics = {
        "cases": len(scored),
        "correct": sum(item["correct"] for item in scored),
        "accuracy": sum(item["correct"] for item in scored) / len(scored),
        "true_positives": tp,
        "true_negatives": tn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "valid_outputs": sum(item["evidence_valid"] for item in scored),
        **call_usage(rows),
    }
    return metrics, scored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    gold_path = args.gold.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("score output already exists")
    output.mkdir(parents=True)

    registration = read(HERE / "REGISTRATION.json")
    if sha256(gold_path) != registration["sealed_gold_sha256"]:
        raise SystemExit("sealed gold hash does not match preregistration")
    predictions = read(run / "predictions.json")
    corpus = read(HERE / "corpus.json")
    source_audit = read(HERE / "SOURCE_AUDIT.json")
    manifest = read(run / "manifest.json")
    gold_doc = read(gold_path)
    gold = {item["id"]: item for item in gold_doc["cases"]}
    packets = {
        arm: {item["id"]: item[f"{arm}_packet"] for item in corpus["cases"]}
        for arm in ("direct", "harness")
    }
    expected_schedule = registration["schedule"]
    actual_schedule = [
        {"case_id": item.get("case_id"), "arm": item.get("arm")}
        for item in predictions.get("results", [])
    ]
    if actual_schedule != expected_schedule:
        raise SystemExit("run schedule does not match preregistration")

    by_arm = defaultdict(list)
    for row in predictions["results"]:
        by_arm[row["arm"]].append(row)
    metrics, per_case = {}, {}
    for arm in ("direct", "harness"):
        metrics[arm], per_case[arm] = score_arm(by_arm[arm], gold, packets[arm])
    direct_tokens = metrics["direct"]["total_tokens"]
    harness_tokens = metrics["harness"]["total_tokens"]
    token_ratio = (
        harness_tokens / direct_tokens
        if type(direct_tokens) is int and direct_tokens > 0 and type(harness_tokens) is int
        else None
    )
    if metrics["harness"]["balanced_accuracy"] > metrics["direct"]["balanced_accuracy"]:
        winner = "harness"
    elif metrics["harness"]["balanced_accuracy"] < metrics["direct"]["balanced_accuracy"]:
        winner = "direct"
    else:
        winner = "tie"
    criteria = {
        "harness_strictly_exceeds_direct_balanced_accuracy": winner == "harness",
        "all_16_calls_completed_with_valid_outputs": (
            metrics["direct"]["valid_outputs"] == 8
            and metrics["harness"]["valid_outputs"] == 8
            and metrics["direct"]["successful_calls"] == 8
            and metrics["harness"]["successful_calls"] == 8
        ),
        "harness_tokens_no_more_than_2x_direct": token_ratio is not None and token_ratio <= 2,
    }
    summary = {
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": (
            "valid_small_exploratory_holdout"
            if criteria["all_16_calls_completed_with_valid_outputs"]
            else "invalid_incomplete_or_schema_failure"
        ),
        "model": registration["model"],
        "reasoning_effort": registration["reasoning_effort"],
        "metrics": metrics,
        "harness_to_direct_token_ratio": token_ratio,
        "winner_by_registered_primary_metric": winner,
        "registered_success_criteria": criteria,
        "all_registered_success_criteria_met": all(criteria.values()),
        "per_case": per_case,
        "gold_sha256": sha256(gold_path),
        "registration_sha256": sha256(HERE / "REGISTRATION.json"),
        "limitations": [
            "Eight cases are too few for a statistically stable performance estimate.",
            "Control labels are right-censored absence of a located public finding, not proof of authenticity.",
            "Identity masking cannot remove post-cutoff facts embedded in model parameters.",
            "The arms intentionally receive different evidence because this evaluates the retrieval system, not a prompt-only ablation.",
        ],
    }
    dump(output / "SUMMARY.json", summary)
    dump(output / "REVEALED_GOLD.json", gold_doc)

    frozen_paths = {
        "corpus.json": HERE / "corpus.json",
        "policies.py": HERE / "policies.py",
        "run_test.py": HERE / "run_test.py",
        "summarize_test.py": HERE / "summarize_test.py",
        "PROTOCOL.md": HERE / "PROTOCOL.md",
        "SOURCE_AUDIT.json": HERE / "SOURCE_AUDIT.json",
    }
    observed_frozen = {name: sha256(path) for name, path in frozen_paths.items()}
    cutoff = registration["cutoff"]
    packet_dates = [
        passage["available_at"]
        for case in corpus["cases"]
        for arm in ("direct_packet", "harness_packet")
        for passage in case[arm]["evidence_passages"]
    ]
    source_dates = [
        source["available_at"]
        for case in source_audit["cases"]
        for source in case["sources"]
    ]
    rows = predictions.get("results", [])
    audit = {
        "registration_hash_matches_run_manifest": (
            manifest.get("registration_sha256") == sha256(HERE / "REGISTRATION.json")
        ),
        "frozen_file_hashes_match_registration": (
            observed_frozen == registration.get("frozen_sha256")
        ),
        "sealed_gold_hash_matches_registration": (
            sha256(gold_path) == registration["sealed_gold_sha256"]
        ),
        "run_schedule_matches_registration": actual_schedule == expected_schedule,
        "all_packet_passages_within_cutoff": all(item <= cutoff for item in packet_dates),
        "all_source_audit_records_within_cutoff": all(item <= cutoff for item in source_dates),
        "source_audit_contains_no_post_cutoff_outcomes": (
            source_audit.get("contains_post_cutoff_outcomes") is False
        ),
        "model_corpus_contains_no_outcome_fields": all(
            "later_outcome" not in json.dumps(case).lower() for case in corpus["cases"]
        ),
        "harness_preserves_direct_base_passages": all(
            case["harness_packet"]["evidence_passages"][:4]
            == case["direct_packet"]["evidence_passages"]
            for case in corpus["cases"]
        ),
        "runner_did_not_load_gold": predictions.get("gold_loaded") is False,
        "all_calls_completed_once_without_retry": (
            len(rows) == 16
            and all(row.get("status") == "completed" for row in rows)
            and all(len(row.get("calls") or []) == 1 for row in rows)
            and manifest.get("retries") == 0
            and manifest.get("fallback") is False
        ),
        "all_registered_success_criteria_met": all(criteria.values()),
    }
    audit["all_checks_passed"] = all(audit.values())
    dump(output / "AUDIT.json", audit)

    model = registration["model"]
    direct, harness = metrics["direct"], metrics["harness"]
    lines = [
        "# Honest system holdout v4: original model vs FactCircuit source tracing", "",
        "This is a preregistered system comparison on eight previously unused papers. The direct",
        "arm received the anonymized original-article record. The harness arm received the same",
        "record plus source traces that were already public by the end of 2024. Later publisher",
        "outcomes were sealed and revealed only after inference.", "",
        f"Both arms used the local Codex-login route with `{model}` at low reasoning, one call per case.", "",
        "| Registered measure | Direct model | FactCircuit harness |",
        "|---|---:|---:|",
        f"| Balanced accuracy | {direct['balanced_accuracy']:.1%} | {harness['balanced_accuracy']:.1%} |",
        f"| Overall accuracy | {direct['correct']}/8 ({direct['accuracy']:.1%}) | {harness['correct']}/8 ({harness['accuracy']:.1%}) |",
        f"| Later-positive recall | {direct['true_positives']}/4 ({direct['sensitivity']:.1%}) | {harness['true_positives']}/4 ({harness['sensitivity']:.1%}) |",
        f"| Control specificity | {direct['true_negatives']}/4 ({direct['specificity']:.1%}) | {harness['true_negatives']}/4 ({harness['specificity']:.1%}) |",
        f"| Valid completed outputs | {direct['valid_outputs']}/8 | {harness['valid_outputs']}/8 |",
        f"| Input + output tokens | {direct['total_tokens']:,} | {harness['total_tokens']:,} |",
        f"| Harness / direct tokens | 1.00x | {token_ratio:.2f}x |", "",
        f"**Winner by the preregistered primary metric: {winner}.**", "",
        f"**All registered success criteria met: {'yes' if summary['all_registered_success_criteria_met'] else 'no'}.**", "",
        "## Per-case blind results", "",
        "| Case | Later outcome | Direct | Harness |",
        "|---|---|---|---|",
    ]
    direct_rows = {row["case_id"]: row for row in per_case["direct"]}
    harness_rows = {row["case_id"]: row for row in per_case["harness"]}
    for case_id in registration["case_order"]:
        expected = gold[case_id]["expected_risk"]
        lines.append(
            f"| {case_id} | {expected} | {direct_rows[case_id]['predicted']} "
            f"({'correct' if direct_rows[case_id]['correct'] else 'wrong'}) | "
            f"{harness_rows[case_id]['predicted']} "
            f"({'correct' if harness_rows[case_id]['correct'] else 'wrong'}) |"
        )
    lines += ["", "## What the labels mean", "",
        "`elevated` means a publisher first issued the registered retraction outcome in 2025–2026.",
        "`ordinary` means the source audit located no retraction concerning the control through",
        "2026-09-11. The latter is a right-censored control label, not a claim that the work is",
        "authentic in every respect.", "", "## Guardrails and limitations", "",
        "The corpus, both arm packets, prompts, order, model, scorer, sealed-gold hash, and pass",
        "conditions were committed before the first call. The isolated runner sent only the",
        "registered anonymized packet for each arm. There were no retries or post-result changes.", "",
        "This eight-case result is exploratory and is not statistically conclusive. Model",
        "pretraining may contain later facts even though names, titles, DOI values, institutions,",
        "journals, URLs, and outcome reports were removed from the packet.", "", "## Reproduce", "",
        "See `experiments/honest-system-holdout-v4-20260911/PROTOCOL.md`, `REGISTRATION.json`,",
        "`corpus.json`, `SOURCE_AUDIT.json`, and the run receipts in this directory. The revealed",
        "gold file contains the post-cutoff publisher outcomes and matches the hash committed",
        "before inference.", ""
    ]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "winner": winner,
        "direct_balanced_accuracy": direct["balanced_accuracy"],
        "harness_balanced_accuracy": harness["balanced_accuracy"],
        "token_ratio": token_ratio,
        "criteria": criteria,
    }, indent=2))


if __name__ == "__main__":
    main()
