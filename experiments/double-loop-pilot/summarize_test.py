"""Summarize all first-attempt outcomes and audit actual loop execution."""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from newsverify.provenance import MaterialVersion, _material_eligibility, _time


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def citation_audit(output, case, visible_verdict):
    materials = {v["version_id"]: v for v in case["materials"]}
    checks = []
    if not output:
        return {"passed": False, "spans": []}
    for span in output["basis"]:
        m = materials.get(span["version_id"])
        quote = span["quote"]
        start = m["content"].find(quote) if m and quote else -1
        unique = start >= 0 and m["content"].find(quote, start + 1) < 0
        eligible = bool(m) and not _material_eligibility(MaterialVersion(**m), _time(case["target"]["as_of"], "cutoff"))
        offsets = ("start" not in span and "end" not in span) or (span.get("start") == start and span.get("end") == start + len(quote))
        checks.append({"version_id": span["version_id"], "unique_exact_quote": unique,
                       "eligible": bool(eligible), "offsets_valid": offsets,
                       "valid": bool(unique and eligible and offsets)})
    return {"passed": all(c["valid"] for c in checks) and (bool(checks) or visible_verdict == "unresolved"), "spans": checks}


def mechanisms(report):
    history = report.get("analysis_history", [])
    revisits = []
    for index, item in enumerate(history):
        earlier = [h for h in history[:index] if h["version_id"] == item["version_id"]]
        if item["revisit"] and item["accepted"] and earlier:
            revisits.append({"version_id": item["version_id"], "revision": item["revision"],
                             "previous_revision": earlier[-1]["revision"],
                             "analysis_changed": item["analysis"] != earlier[-1]["analysis"]})
    verifications = report.get("verification_history", [])
    generated = {}
    for v in verifications:
        for g in v["gaps"]:
            generated[g["id"]] = min(generated.get(g["id"], v["round"]), v["round"])
    feedback = []
    for request in report.get("execution", {}).get("provider_requests", []):
        selected = request["selected_version_id"]
        if selected is None:
            continue
        gaps = [g["id"] for g in request["tasks"] if g["stage"] == "verification" and generated.get(g["id"], request["round"]) < request["round"]]
        if not gaps:
            continue
        operations = [o for o in report["operations"] if o["round"] == request["round"]]
        decomposed = [o["sequence"] for o in operations if o["action"] == "decompose_completed" and o.get("version_id") == selected]
        verified = [o["sequence"] for o in operations if o["action"] == "verification_completed"]
        admitted = selected in report.get("eligible_version_ids", [])
        completed = bool(admitted and decomposed and verified and min(decomposed) < min(verified))
        verifier_resolved = {r["gap_id"] for v in verifications if v["round"] >= request["round"] for r in v["resolutions"] if r["gap_id"] in gaps}
        analysis_resolved = {r["gap_id"] for h in history if h["accepted"] and h["round"] >= request["round"] for r in h["analysis"]["resolutions"] if r["gap_id"] in gaps}
        resolved = sorted(verifier_resolved | analysis_resolved)
        feedback.append({"round": request["round"], "gap_ids": gaps, "selected_version_id": selected,
                         "admitted_decomposed_then_verified": completed, "resolved_gap_ids": resolved,
                         "resolved_by_verifier": sorted(verifier_resolved), "resolved_by_decomposer": sorted(analysis_resolved),
                         "still_open_gap_ids": sorted(g["id"] for g in report.get("gaps", []) if g["id"] in gaps)})
    return {"reanalysis_executed": bool(revisits), "recorded_analysis_changed": any(r["analysis_changed"] for r in revisits),
            "analysis_change_scope": "Any recorded Analysis field, including notes; not evidence of a semantic improvement.",
            "verification_feedback_executed": any(f["admitted_decomposed_then_verified"] for f in feedback),
            "both_loops_executed": bool(revisits) and any(f["admitted_decomposed_then_verified"] for f in feedback),
            "revisits": revisits, "feedback": feedback}


def main():
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "results"
    raw = read(out / "all-results.json")
    manifest, results = raw["manifest"], raw["results"]
    verified_files = {}
    for name, expected in manifest["frozen_sha256"].items():
        candidates = [ROOT / name, out / "frozen-inputs" / name]
        matching = next((p for p in candidates if p.is_file() and sha(p) == expected), None)
        assert matching is not None, f"Frozen artifact not available: {name}"
        verified_files[name] = matching
    corpus = read(verified_files[str((HERE / "corpus.json").relative_to(ROOT))])
    cases = {c["target"]["id"]: c for c in corpus["cases"]}
    gold = {g["id"]: g for g in raw["gold"]["cases"]}
    assert len(results) == 2 * len(cases)
    assert {(r["id"], r["condition"]) for r in results} == {(id, condition) for id in cases for condition in ["direct", "double_loop"]}
    assert raw["gold"] == read(verified_files[str((HERE / "gold.json").relative_to(ROOT))])
    rows, stages = [], defaultdict(list)
    for r in results:
        assert read(out / r["id"] / r["condition"] / "result.json") == r
        report = r.get("report", {})
        history = report.get("verification_history", [])
        output = r.get("raw_response") if r["condition"] == "direct" else history[-1] if history else None
        succeeded = bool(output and r["calls"] and not r["errors"] and all(c["success"] for c in r["calls"]))
        citations = citation_audit(output, cases[r["id"]], r["fact_status"])
        loop = mechanisms(report) if r["condition"] == "double_loop" else None
        row = {"id": r["id"], "condition": r["condition"], "expected": gold[r["id"]]["expected_fact_status"],
               "observed": r["fact_status"], "pipeline_success": succeeded,
               "expected_match": succeeded and r["fact_status"] == gold[r["id"]]["expected_fact_status"],
               "calls": len(r["calls"]), "errors": r["errors"], "final_output": output,
               "citations": citations, "mechanisms": loop, "provenance_status": report.get("provenance_status"),
               "stop_reason": report.get("stop_reason"), "timer_seconds": r["timer_seconds"],
               "utc_elapsed_seconds": r["utc_elapsed_seconds"],
               "clock_discrepancy": abs(r["timer_seconds"] - r["utc_elapsed_seconds"]) > 1}
        rows.append(row)
        for call in r["calls"]:
            stages[(r["condition"], call["stage"])].append(call)
    stage_stats = []
    for (condition, stage), calls in stages.items():
        known = [c for c in calls if c.get("usage") and isinstance(c["usage"].get("input_tokens"), int) and isinstance(c["usage"].get("output_tokens"), int)]
        inp = sum(c["usage"]["input_tokens"] for c in known)
        output = sum(c["usage"]["output_tokens"] for c in known)
        stage_stats.append({"condition": condition, "stage": stage, "attempts": len(calls),
                            "successful_calls": sum(c["success"] for c in calls), "known_usage_calls": len(known),
                            "known_input_tokens": inp, "known_output_tokens": output,
                            "total_tokens": inp + output if len(known) == len(calls) else None})
    conditions = {condition: {"cases": len(cases), "expected_matches": sum(r["expected_match"] for r in rows if r["condition"] == condition),
                              "completed": sum(r["pipeline_success"] for r in rows if r["condition"] == condition),
                              "model_calls": sum(r["calls"] for r in rows if r["condition"] == condition)}
                  for condition in ["direct", "double_loop"]}
    for condition, stats in conditions.items():
        totals = [s["total_tokens"] for s in stage_stats if s["condition"] == condition]
        stats["total_tokens"] = sum(totals) if totals and all(t is not None for t in totals) else None
    summary = {"conditions": conditions, "stage_tokens": stage_stats, "runs": rows,
               "both_loop_cases": [r["id"] for r in rows if r["mechanisms"] and r["mechanisms"]["both_loops_executed"]],
               "timing_warning": any(r["clock_discrepancy"] for r in rows),
               "all_results_sha256": sha(out / "all-results.json"), "summarizer_sha256": sha(Path(__file__)),
               "scope": "Three constructed cases over downloaded real papers; finite-pool integration pilot, not held-out general accuracy evidence."}
    direct_total = conditions["direct"]["total_tokens"]
    harness_total = conditions["double_loop"]["total_tokens"]
    summary["harness_to_direct_token_ratio"] = harness_total / direct_total if direct_total and harness_total is not None else None
    (out / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Astra alone versus the full double-loop harness", "",
             f"Fresh live runs through **{manifest['tunnel']}**, requesting **{manifest['model']}** with **{manifest['reasoning_effort']}** reasoning. All cases and failures are retained.", "",
             "| Condition | Expected matches | Completed cases | Model calls | Total tokens |", "|---|---:|---:|---:|---:|"]
    for condition, stats in conditions.items():
        lines.append(f"| {condition} | {stats['expected_matches']}/{stats['cases']} | {stats['completed']}/{stats['cases']} | {stats['model_calls']} | {stats['total_tokens'] if stats['total_tokens'] is not None else 'unknown'} |")
    if summary["harness_to_direct_token_ratio"] is not None:
        lines += ["", f"The harness used **{summary['harness_to_direct_token_ratio']:.2f} times** the total reported tokens of Astra alone across these cases. This compares input plus output tokens, including cached input; it is not a monetary cost ratio."]
    lines += ["", "The direct baseline sees the whole source pool immediately. The harness starts with the news article and selects more evidence from the same pool in response to its questions. Actual computation differs; this is not an equal-token comparison.", "",
              "| Case | Expected | Astra alone | With double loop | Reanalysis | Verification feedback |", "|---|---|---|---|---|---|"]
    if manifest.get("revision_note"):
        lines[2:2] = ["This is a fresh full-batch rerun after the documented resolution-validation correction. The earlier failed run remains preserved. Targets, evidence and expected labels are unchanged; this is development validation, not a new held-out test. [Correction and regression tests](../VALIDATION_FIX.md) · [First attempt](../results/REPORT.md)", ""]
    index = {(r["id"], r["condition"]): r for r in rows}
    for id in cases:
        a, b = index[id, "direct"], index[id, "double_loop"]
        def status(r):
            return r["observed"] + (" (execution error)" if not r["pipeline_success"] else "")
        lines.append(f"| {id} | {a['expected']} | {status(a)} | {status(b)} | {b['mechanisms']['reanalysis_executed']} | {b['mechanisms']['verification_feedback_executed']} |")
    lines += ["", "Loop execution is counted only from preserved operations: a revised older analysis, and a generated verification gap followed by selection, admission, decomposition and later verification. A correct verdict alone is not proof of either loop.", "",
              "## Case details", ""]
    for id, case in cases.items():
        lines += [f"### {id}", "", case["target"]["text"], "", f"Expected: {gold[id]['expected_fact_status']}. {gold[id]['reason']}", ""]
        for condition in ["direct", "double_loop"]:
            r = index[id, condition]
            lines += [f"**{condition}: {r['observed']}**. Calls: {r['calls']}. Final citation audit: {r['citations']['passed']}.", "",
                      f"[Preserved result]({id}/{condition}/result.json)", "", "```json",
                      json.dumps({"final_output": r["final_output"], "errors": r["errors"], "mechanisms": r["mechanisms"]}, ensure_ascii=False, indent=2), "```", ""]
    lines += ["## Observed token use", "", "| Condition / stage | Calls with usage / attempts | Input | Output | Total |", "|---|---:|---:|---:|---:|"]
    for s in stage_stats:
        lines.append(f"| {s['condition']} / {s['stage']} | {s['known_usage_calls']}/{s['attempts']} | {s['known_input_tokens']} known | {s['known_output_tokens']} known | {s['total_tokens'] if s['total_tokens'] is not None else 'unknown'} |")
    if harness_total:
        largest = max((s for s in stage_stats if s["condition"] == "double_loop"), key=lambda s: s["total_tokens"])
        lines += ["", f"The **{largest['stage']}** stage accounts for **{100 * largest['total_tokens'] / harness_total:.1f}%** of harness tokens. Decomposition includes both first analyses and revisits; this stage accounting does not isolate the causal contribution of either loop."]
    lines += ["", "Missing usage is unknown, not zero. Token totals are not prices; cached inputs, if present in receipts, are already included in input tokens.", "",
              "## Scope and validation", "",
              ("An isolated environment and required HTML/TLS packages were installed. "
               + ("All 145 tests (132 existing plus 13 double-loop contract and regression tests) passed before this rerun. " if manifest.get("revision_note") else "The original 132 tests and 11 new double-loop contract tests passed before live inference. ")
               + "Original one-round production files and prior experiments were preserved. Full source bytes, extracted text, URLs, rights information, exact timestamps and hashes are retained alongside the corpus."), "",
              "These are three manually constructed cases over two events, with agent-authored labels cross-reviewed before inference. The NIST event overlaps earlier development work. The initial news page is an entry point to the paper, not a claim that it contains the constructed methods-detail target verbatim. Source-path status is a model/core diagnostic, not independent proof of correct source attribution.", "",
              "Finite-pool adaptive retrieval does not test unrestricted web search. Shared model identity does not remove hidden CLI instructions. No general accuracy improvement, causal contribution of each individual loop, or production reliability claim follows from this small pilot.", "",
              ("**Timing warning:** UTC timestamp intervals diverged from recorded runtime timers. Their cause is undetermined; do not rank speed or route reliability from these timings." if summary["timing_warning"] else "UTC timestamp intervals and runtime timers did not show a discrepancy above one second per case. Timing still reflects one small uncontrolled sample."), "",
              "[Protocol](../PROTOCOL.md) · [Source notes](../SOURCES.md) · [Setup](../SETUP.md) · [Machine-readable summary](SUMMARY.json)"]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: summary[k] for k in ["conditions", "stage_tokens", "both_loop_cases", "timing_warning"]}, indent=2))


if __name__ == "__main__":
    main()
