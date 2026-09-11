#!/usr/bin/env python3
"""Score fact accuracy, future risk detection and token use after inference."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def usage(calls: list[dict]) -> dict:
    known = []
    for call in calls:
        value = call.get("usage")
        if not isinstance(value, dict):
            continue
        a, b = value.get("input_tokens"), value.get("output_tokens")
        if type(a) is int and type(b) is int and a >= 0 and b >= 0:
            known.append((a, b))
    return {
        "attempts": len(calls),
        "successful_calls": sum(call.get("success") is True for call in calls),
        "known_usage_calls": len(known),
        "usage_complete": bool(calls) and len(known) == len(calls),
        "input_tokens": sum(a for a, _ in known) if len(known) == len(calls) and calls else None,
        "output_tokens": sum(b for _, b in known) if len(known) == len(calls) and calls else None,
        "total_tokens": sum(a + b for a, b in known) if len(known) == len(calls) and calls else None,
    }


def evidence_valid(result: dict, case: dict) -> bool:
    materials = {item["version_id"]: item for item in case["materials"]}
    evidence = result.get("evidence")
    if not isinstance(evidence, list):
        return False
    if result.get("fact_verdict") in {"supported", "contradicted"} and not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict) or item.get("version_id") not in materials:
            return False
        material = materials[item["version_id"]]
        start, end, quote = item.get("start"), item.get("end"), item.get("quote")
        if type(start) is not int or type(end) is not int or not isinstance(quote, str):
            return False
        if start < 0 or end <= start or material["content"][start:end] != quote:
            return False
        try:
            available = datetime.fromisoformat(material["available_at"].replace("Z", "+00:00"))
            cutoff = datetime.fromisoformat(case["target"]["as_of"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            return False
        if available > cutoff:
            return False
    if result.get("claim_scope") == "real_world_provenance" and not result.get("independent_authentication"):
        return result.get("fact_verdict") == "unresolved" and result.get("fraud_risk") == "high"
    if result.get("claim_scope") == "source_attribution" and result.get("fact_verdict") == "supported":
        return result.get("fraud_risk") == "low"
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit("score output already exists")
    output.mkdir(parents=True)
    predictions = read(run / "predictions.json")
    corpus = read(run / "corpus.json")
    gold_doc = read(args.gold.resolve())
    baseline = read(args.baseline_summary.resolve())
    cases = {case["target"]["id"]: case for case in corpus["cases"]}
    gold = {row["id"]: row for row in gold_doc["cases"]}
    rows = []
    all_calls = []
    for row in predictions["results"]:
        case_id = row["id"]
        result = row.get("result") or {}
        valid = row.get("status") == "completed" and evidence_valid(result, cases[case_id])
        fact_correct = valid and result.get("fact_verdict") == gold[case_id]["cutoff_expected"]
        later_false = gold[case_id]["future_expected"] == "contradicted"
        risk_high = valid and result.get("fraud_risk") == "high"
        rows.append({
            "id": case_id,
            "role": gold[case_id]["role"],
            "variant": gold[case_id]["variant"],
            "cutoff_expected": gold[case_id]["cutoff_expected"],
            "fact_verdict": result.get("fact_verdict"),
            "claim_scope": result.get("claim_scope"),
            "fraud_risk": result.get("fraud_risk"),
            "pipeline_valid": valid,
            "strict_fact_correct": fact_correct,
            "later_false": later_false,
            "later_false_detected": later_false and risk_high,
            "control_high_risk": not later_false and risk_high,
        })
        all_calls.extend(row.get("calls") or [])
    totals = usage(all_calls)
    direct_tokens = baseline["conditions"]["direct"]["total_tokens"]
    ratio = totals["total_tokens"] / direct_tokens if totals["total_tokens"] is not None else None
    fact_correct = sum(row["strict_fact_correct"] for row in rows)
    detections = sum(row["later_false_detected"] for row in rows)
    later_false_count = sum(row["later_false"] for row in rows)
    control_flags = sum(row["control_high_risk"] for row in rows)
    goals = {
        "strict_fact_accuracy_at_least_75_percent": fact_correct >= 6,
        "later_false_detection_4_of_4": detections == 4 and later_false_count == 4,
        "tokens_no_more_than_2x_direct": ratio is not None and ratio <= 2,
    }
    summary = {
        "comparison": {
            "direct_baseline": {
                "model": "gpt-5.6-luna", "reasoning_effort": "low",
                "strict_fact_correct": baseline["conditions"]["direct"]["evidence_valid"],
                "cases": baseline["conditions"]["direct"]["cases"],
                "tokens": direct_tokens,
                "source_summary_sha256": sha(args.baseline_summary.resolve()),
            },
            "single_pass_harness": {
                "model": read(run / "manifest.json")["model"],
                "reasoning_effort": read(run / "manifest.json")["reasoning_effort"],
                "strict_fact_correct": fact_correct,
                "cases": len(rows),
                "strict_fact_accuracy": fact_correct / len(rows),
                "later_false_detected": detections,
                "later_false_cases": later_false_count,
                "control_high_risk": control_flags,
                "control_cases": len(rows) - later_false_count,
                **totals,
            },
            "harness_to_direct_token_ratio": ratio,
        },
        "goals": goals,
        "all_goals_met": all(goals.values()),
        "rows": rows,
        "limitations": [
            "All eight cases were previously observed development cases.",
            "The cases represent two event families; masked variants are correlated.",
            "The four controls are attribution claims, not clean nonfraud provenance controls.",
            "High fraud risk means missing independent authentication, not proof of fabrication.",
        ],
    }
    dump(output / "SUMMARY.json", summary)
    lines = [
        "# Total local comparison: direct model and single-pass harness", "",
        "The candidate separates cutoff fact verification from an early provenance-risk forecast.", "",
        "| Measure | Direct Luna | Luna + single-pass harness | Goal |",
        "|---|---:|---:|---:|",
        f"| Strict cutoff fact accuracy | {baseline['conditions']['direct']['evidence_valid']}/8 | {fact_correct}/8 ({100*fact_correct/len(rows):.1f}%) | ≥6/8 |",
        f"| Later-false cases identified early | 0/4¹ | {detections}/{later_false_count} | 4/4 |",
        f"| Control cases flagged high risk | — | {control_flags}/{len(rows)-later_false_count} | diagnostic |",
        f"| Model calls | {baseline['conditions']['direct']['attempts']} | {totals['attempts']} | ≤ one/case |",
        f"| Input + output tokens | {direct_tokens:,} | {totals['total_tokens']:,} | ≤{2*direct_tokens:,} |",
        f"| Harness / direct token ratio | 1.00× | {ratio:.2f}× | ≤2.00× |", "",
        f"**All registered goals met: {'yes' if summary['all_goals_met'] else 'no'}.**", "",
        "## Per-case results", "",
        "| Case | Role | Fact expected | Fact result | Scope | Risk | Strict |",
        "|---|---|---|---|---|---|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['id']} | {row['role']} | {row['cutoff_expected']} | {row['fact_verdict']} | {row['claim_scope']} | {row['fraud_risk']} | {'yes' if row['strict_fact_correct'] else 'no'} |")
    lines += ["", "¹ The direct baseline had no separate risk output. None of its cutoff fact verdicts identified the four later-false claims; the harness adds a dedicated predictive risk channel.", "",
        "## Interpretation", "",
        "A high risk output records that a real-world provenance claim is supported only by the subject publication and lacks independent authentication in the bounded packet. It does not claim that pre-2024 evidence proved fabrication.", "",
        "This is an in-sample development result over two event families. The attribution controls test whether the policy preserves literal report claims, but they do not measure false-positive risk on genuine, independently authenticated experiments.", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary["comparison"], indent=2))
    print(json.dumps(summary["goals"], indent=2))


if __name__ == "__main__":
    main()
