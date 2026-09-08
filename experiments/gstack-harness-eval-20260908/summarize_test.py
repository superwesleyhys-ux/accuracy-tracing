"""Audit and summarize the frozen Astra/local-Codex versus harness batch."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from newsverify.provenance import MaterialVersion, _material_eligibility, _time

VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
CONDITIONS = ("direct", "double_loop")


def read(path):
    def reject(value):
        raise ValueError("Nonfinite JSON value in artifact")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def nonnegative_int(value):
    return type(value) is int and value >= 0


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def citation_audit(output, case, visible_verdict):
    checks, problems = [], []
    if not isinstance(output, dict) or not isinstance(output.get("basis"), list):
        return {"passed": False, "spans": [], "problems": ["Missing or malformed basis"]}
    if not isinstance(output.get("rationale"), str) or not output["rationale"].strip():
        problems.append("Rationale is empty or malformed")
    if not output["basis"] and (visible_verdict != "unresolved" or output.get("verdict") != "unresolved"):
        problems.append("A settled raw or visible verdict requires evidence")
    materials = {m["version_id"]: m for m in case["materials"]}
    for span in output["basis"]:
        if not isinstance(span, dict):
            checks.append({"valid": False, "problem": "Malformed citation"})
            continue
        version, quote = span.get("version_id"), span.get("quote")
        material = materials.get(version) if isinstance(version, str) else None
        start = material["content"].find(quote) if material and isinstance(quote, str) and quote else -1
        exact = start >= 0
        unique = bool(exact and material["content"].find(quote, start + 1) < 0)
        try:
            eligible = bool(material) and not _material_eligibility(MaterialVersion(**material), _time(case["target"]["as_of"], "cutoff"))
        except (TypeError, ValueError):
            eligible = False
        offsets = not ("start" in span or "end" in span) or (
            nonnegative_int(span.get("start")) and nonnegative_int(span.get("end"))
            and span["start"] == start and isinstance(quote, str) and span["end"] == start + len(quote))
        checks.append({"version_id": version, "exact_quote": exact, "unique_quote": unique,
                       "eligible": bool(eligible), "offsets_valid": bool(offsets),
                       "valid": bool(unique and eligible and offsets)})
    return {"passed": not problems and all(c["valid"] for c in checks), "spans": checks, "problems": problems}


def output_shape_valid(output, condition):
    if not isinstance(output, dict):
        return False
    fields = {"verdict", "basis", "rationale"}
    if condition == "double_loop":
        fields |= {"round", "gaps", "resolutions"}
    if set(output) != fields or not isinstance(output.get("verdict"), str) or output["verdict"] not in VERDICTS:
        return False
    if not isinstance(output.get("rationale"), str) or not isinstance(output.get("basis"), list):
        return False
    if condition == "double_loop" and (not nonnegative_int(output["round"]) or not isinstance(output["gaps"], list) or not isinstance(output["resolutions"], list)):
        return False
    for span in output["basis"]:
        if not isinstance(span, dict) or not {"version_id", "quote"} <= set(span) <= {"version_id", "quote", "start", "end"}:
            return False
        if not isinstance(span["version_id"], str) or not isinstance(span["quote"], str):
            return False
    return True


def mechanisms(report):
    history = records(report.get("analysis_history"))
    verifications = records(report.get("verification_history"))
    operations = records(report.get("operations"))
    revisits = []
    for index, item in enumerate(history):
        prior = [(i, h) for i, h in enumerate(history[:index]) if h.get("accepted") is True and h.get("version_id") == item.get("version_id")]
        if item.get("accepted") is not True or item.get("revisit") is not True or not prior:
            continue
        previous_index, previous = prior[-1]
        known = {h.get("version_id") for h in history[:previous_index + 1] if h.get("accepted") is True}
        new_versions = sorted({h["version_id"] for h in history[previous_index + 1:index]
                               if h.get("accepted") is True and h.get("version_id") not in known})
        revisits.append({"version_id": item.get("version_id"), "revision": item.get("revision"),
                         "previous_revision": previous.get("revision"), "new_versions_since_previous_analysis": new_versions,
                         "analysis_changed": item.get("analysis") != previous.get("analysis")})
    generated = {}
    for verification in verifications:
        for gap in records(verification.get("gaps")):
            if gap.get("stage") == "verification" and isinstance(gap.get("id"), str) and nonnegative_int(verification.get("round")):
                generated[gap["id"]] = min(generated.get(gap["id"], verification["round"]), verification["round"])
    open_ids = {gap.get("id") for gap in records(report.get("gaps"))}
    feedback = []
    for request in records(report.get("execution", {}).get("provider_requests")):
        selected, round_number = request.get("selected_version_id"), request.get("round")
        if not isinstance(selected, str) or not nonnegative_int(round_number):
            continue
        gaps = sorted({g["id"] for g in records(request.get("tasks")) if g.get("stage") == "verification"
                       and g.get("id") in generated and generated[g["id"]] < round_number})
        if not gaps:
            continue
        same_round = [o for o in operations if o.get("round") == round_number and nonnegative_int(o.get("sequence"))]
        saved = [o["sequence"] for o in same_round if o.get("action") == "snapshot_saved" and o.get("version_id") == selected and o.get("eligible") is True]
        decomposed = [o["sequence"] for o in same_round if o.get("action") == "decompose_completed" and o.get("version_id") == selected]
        verified = [o["sequence"] for o in same_round if o.get("action") == "verification_completed"]
        old_saved = any(o.get("action") == "snapshot_saved" and o.get("version_id") == selected and o.get("round", round_number) < round_number for o in operations)
        completed = bool(not old_saved and selected in report.get("eligible_version_ids", []) and saved and decomposed and verified
                         and min(saved) < min(decomposed) < min(verified))
        historical_verifier = {r.get("gap_id") for v in verifications if v.get("round", -1) >= round_number for r in records(v.get("resolutions")) if r.get("gap_id") in gaps}
        historical_decomposer = {r.get("gap_id") for h in history if h.get("accepted") is True and h.get("round", -1) >= round_number
                                  for r in records(h.get("analysis", {}).get("resolutions")) if r.get("gap_id") in gaps}
        historically_resolved = historical_verifier | historical_decomposer
        feedback.append({"round": round_number, "gap_ids": gaps, "selected_version_id": selected,
                         "admitted_decomposed_then_verified": completed,
                         "historically_resolved_gap_ids": sorted(historically_resolved),
                         "finally_resolved_gap_ids": sorted(historically_resolved - open_ids),
                         "still_open_gap_ids": sorted(set(gaps) & open_ids)})
    reanalysis = any(r["new_versions_since_previous_analysis"] for r in revisits)
    verified_feedback = any(f["admitted_decomposed_then_verified"] for f in feedback)
    return {"accepted_revisit_executed": bool(revisits), "reanalysis_executed": reanalysis,
            "verification_feedback_executed": verified_feedback, "both_loops_executed": bool(reanalysis and verified_feedback),
            "recorded_analysis_changed": any(r["analysis_changed"] for r in revisits),
            "analysis_change_scope": "Any recorded field, including notes; not evidence of semantic improvement.",
            "revisits": revisits, "feedback": feedback}


def score_run(run, case, gold):
    condition = run["condition"]
    report = run.get("report") if isinstance(run.get("report"), dict) else {}
    history = report.get("verification_history")
    output = run.get("raw_response") if condition == "direct" else history[-1] if isinstance(history, list) and history else None
    calls = run.get("calls") if isinstance(run.get("calls"), list) else []
    shape = output_shape_valid(output, condition)
    visible = run.get("fact_status")
    errors = run.get("errors")
    completed = bool(shape and calls and isinstance(errors, list) and not errors
                     and isinstance(visible, str) and visible in VERDICTS and all(isinstance(c, dict) and c.get("success") is True for c in calls))
    if condition == "direct" and shape and visible != output["verdict"]:
        completed = False
    citations = citation_audit(output, case, visible)
    matched = completed and visible == gold["expected_fact_status"]
    timer, utc = run.get("timer_seconds"), run.get("utc_elapsed_seconds")
    valid_timing = finite_number(timer) and finite_number(utc)
    return {"id": run["id"], "condition": condition, "expected": gold["expected_fact_status"],
            "observed": visible, "raw_verdict": output.get("verdict") if isinstance(output, dict) else None,
            "shape_valid": shape, "pipeline_success": completed, "completed_label_match": matched,
            "evidence_valid_label_match": bool(matched and citations["passed"]),
            "calls": len(calls), "errors": errors, "final_output": output, "citations": citations,
            "mechanisms": mechanisms(report) if condition == "double_loop" else None,
            "provenance_status": report.get("provenance_status"), "stop_reason": report.get("stop_reason"),
            "timer_seconds": timer, "utc_elapsed_seconds": utc,
            "clock_discrepancy": not valid_timing or abs(timer - utc) > 1}


def token_stats(calls):
    known, cached, attempts = [], [], len(calls)
    for call in calls:
        usage = call.get("usage") if isinstance(call, dict) else None
        if not isinstance(usage, dict) or not nonnegative_int(usage.get("input_tokens")) or not nonnegative_int(usage.get("output_tokens")):
            continue
        if usage.get("total_tokens") is not None and (not nonnegative_int(usage["total_tokens"]) or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]):
            continue
        known.append(usage)
        cache = usage.get("cached_input_tokens")
        if cache is None and isinstance(usage.get("input_tokens_details"), dict):
            cache = usage["input_tokens_details"].get("cached_tokens")
        if nonnegative_int(cache) and cache <= usage["input_tokens"]:
            cached.append(cache)
    inp = sum(u["input_tokens"] for u in known)
    out = sum(u["output_tokens"] for u in known)
    return {"attempts": attempts, "successful_calls": sum(isinstance(c, dict) and c.get("success") is True for c in calls),
            "known_usage_calls": len(known), "known_input_tokens": inp, "known_output_tokens": out,
            "known_total_tokens": inp + out, "total_tokens": inp + out if attempts and len(known) == attempts else None,
            "known_cached_usage_calls": len(cached), "known_cached_input_tokens": sum(cached),
            "cached_input_tokens": sum(cached) if attempts and len(cached) == attempts else None}


def load_batch(out, root=ROOT):
    out, root = Path(out), Path(root)
    raw = read(out / "all-results.json")
    manifest, results = raw["manifest"], raw["results"]
    require(manifest == read(out / "manifest.json"), "Manifest sidecar does not match aggregate")
    require(isinstance(manifest.get("frozen_sha256"), dict) and bool(manifest["frozen_sha256"]), "No frozen artifact hashes")
    verified = {}
    for name, expected in manifest["frozen_sha256"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe frozen artifact path")
        candidates = (root / name, out / "frozen-inputs" / name)
        matching = next((p for p in candidates if p.is_file() and sha(p) == expected), None)
        require(matching is not None, f"Frozen artifact missing or changed: {name}")
        verified[name] = matching
    if "integrity_checks" in manifest:
        require(set(manifest["integrity_checks"]) == set(verified) and all(v is True for v in manifest["integrity_checks"].values()), "Run recorded an integrity failure")
    require(manifest["corpus_path"] in verified and manifest["gold_path"] in verified, "Corpus or labels were not frozen")
    corpus = read(verified[manifest["corpus_path"]])
    gold_document = read(verified[manifest["gold_path"]])
    require(raw["gold"] == gold_document, "Aggregate labels differ from frozen labels")
    cases = {c["target"]["id"]: c for c in corpus["cases"]}
    gold = {g["id"]: g for g in gold_document["cases"]}
    require(len(cases) == len(corpus["cases"]) == manifest["case_count"], "Invalid case denominator")
    require(len(gold) == len(gold_document["cases"]) and set(gold) == set(cases), "Labels do not cover the case set exactly")
    require(isinstance(results, list) and len(results) == len(cases) * 2, "Missing or extra condition result")
    actual = [(r["id"], r["condition"]) for r in results]
    require(set(actual) == {(id, c) for id in cases for c in CONDITIONS} and len(set(actual)) == len(actual), "Duplicate or missing condition result")
    for run in results:
        require(isinstance(run["id"], str) and Path(run["id"]).name == run["id"] and run["id"] not in (".", ".."), "Unsafe result identifier")
        folder = out / run["id"] / run["condition"]
        require(read(folder / "result.json") == run, "Result sidecar differs from aggregate")
        for number, call in enumerate(run["calls"], 1):
            require(call.get("stage") in {"direct", "select", "decompose", "verify"}, "Unknown transport stage")
            require(read(folder / f"{number:02d}-{call['stage']}.calls.json") == [call], "Transport receipt differs from aggregate")
    return manifest, results, cases, gold


def summarize(out, root=ROOT):
    out = Path(out)
    manifest, results, cases, gold = load_batch(out, root)
    rows = [score_run(r, cases[r["id"]], gold[r["id"]]) for r in results]
    grouped = defaultdict(list)
    for run in results:
        for call in run["calls"]:
            grouped[run["condition"], call["stage"]].append(call)
    stages = [{"condition": condition, "stage": stage, **token_stats(calls)} for (condition, stage), calls in sorted(grouped.items())]
    conditions = {}
    for condition in CONDITIONS:
        relevant = [r for r in rows if r["condition"] == condition]
        calls = [call for run in results if run["condition"] == condition for call in run["calls"]]
        conditions[condition] = {"cases": len(cases), "completed": sum(r["pipeline_success"] for r in relevant),
                                 "completed_label_matches": sum(r["completed_label_match"] for r in relevant),
                                 "evidence_valid_label_matches": sum(r["evidence_valid_label_match"] for r in relevant),
                                 "model_calls": len(calls), **token_stats(calls)}
    direct, harness = (conditions[c]["total_tokens"] for c in CONDITIONS)
    summary = {"conditions": conditions, "stage_tokens": stages, "runs": rows,
               "harness_to_direct_token_ratio": harness / direct if direct and harness is not None else None,
               "both_loop_cases": [r["id"] for r in rows if r["mechanisms"] and r["mechanisms"]["both_loops_executed"]],
               "timing_warning": any(r["clock_discrepancy"] for r in rows), "case_count": len(cases),
               "event_family_count": manifest.get("event_family_count", 3), "held_out": False,
               "frozen_artifact_count": len(manifest["frozen_sha256"]), "all_results_sha256": sha(out / "all-results.json"),
               "summarizer_sha256": sha(Path(__file__)),
               "scope": "Constructed development cases clustered by event; finite source-pool comparison, not independent held-out accuracy evidence."}
    (out / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    render_report(out, summary, manifest, cases, gold)
    return summary


def render_report(out, summary, manifest, cases, gold):
    def shown(value):
        return "unknown" if value is None else str(value)
    lines = ["# Gstack-guided Astra versus harness test", "",
             f"This fresh batch requested **{manifest['model']}**, **{manifest['reasoning_effort']}** reasoning through **{manifest['tunnel']}**. Every case and execution failure is retained.", "",
             "| Workflow | Completed | Label matches | Evidence-valid label matches | Logical model calls | Total tokens |",
             "|---|---:|---:|---:|---:|---:|"]
    for condition, stats in summary["conditions"].items():
        lines.append(f"| {condition} | {stats['completed']}/{stats['cases']} | {stats['completed_label_matches']}/{stats['cases']} | {stats['evidence_valid_label_matches']}/{stats['cases']} | {stats['model_calls']} | {shown(stats['total_tokens'])} |")
    ratio = summary["harness_to_direct_token_ratio"]
    if ratio is not None:
        lines += ["", f"The harness used **{ratio:.2f}×** the reported input-plus-output tokens. Cached input is included; this is not a price ratio."]
    lines += ["", "The local baseline uses Astra through Codex with installed skill catalogs excluded. Normal Codex system/developer instructions remain; this is not a raw base-model or offline-weight test. Gstack guided review and evaluation, and was not added to either inference prompt.", "",
              "Astra alone sees the complete eligible frozen pool immediately. The harness starts with one source and selects more from that same finite pool. Computation and initial evidence access differ; there is no common enforced token budget.", "",
              "| Case | Expected | Astra alone | Harness visible verdict | Harness raw verdict | Both loops |", "|---|---|---|---|---|---|"]
    index = {(r["id"], r["condition"]): r for r in summary["runs"]}
    for id in cases:
        a, b = (index[id, condition] for condition in CONDITIONS)
        def status(row):
            return str(row["observed"]) + (" (incomplete/error)" if not row["pipeline_success"] else "")
        lines.append(f"| {id} | {a['expected']} | {status(a)} | {status(b)} | {shown(b['raw_verdict'])} | {b['mechanisms']['both_loops_executed']} |")
    lines += ["", "A label match requires a completed valid-shaped answer and no execution error. Evidence-valid matches additionally require a nonempty rationale and unique, exact, eligible quotations with correct offsets when supplied. Settled raw or visible verdicts need evidence. Quote integrity does not independently establish semantic entailment.", "",
              "## Recorded token use", "", "| Workflow / stage | Known usage / attempts | Input known | Output known | Cached input known | Complete total |", "|---|---:|---:|---:|---:|---:|"]
    for stats in summary["stage_tokens"]:
        lines.append(f"| {stats['condition']} / {stats['stage']} | {stats['known_usage_calls']}/{stats['attempts']} | {stats['known_input_tokens']} | {stats['known_output_tokens']} | {stats['known_cached_input_tokens']} ({stats['known_cached_usage_calls']}/{stats['attempts']}) | {shown(stats['total_tokens'])} |")
    total = summary["conditions"]["double_loop"]["total_tokens"]
    if total:
        largest = max((s for s in summary["stage_tokens"] if s["condition"] == "double_loop"), key=lambda s: s["total_tokens"])
        lines += ["", f"**{largest['stage']}** accounts for **{100 * largest['total_tokens'] / total:.1f}%** of harness tokens. Decomposition includes first analyses and revisits, and can answer verification questions. Stage accounting does not isolate either loop's causal contribution."]
    lines += ["", "Missing or invalid usage stays unknown, including failed calls. Counts describe logical transport invocations, not HTTP requests; internal CLI/provider retries are not controlled or counted separately. No orchestration retry or route fallback is used.", "",
              "## Cases and evidence", ""]
    for id, case in cases.items():
        lines += [f"### {id}", "", case["target"]["text"], "", f"Expected: **{gold[id]['expected_fact_status']}**. {gold[id].get('reason', '')}", ""]
        for condition in CONDITIONS:
            row = index[id, condition]
            lines += [f"**{condition}**: completed={row['pipeline_success']}; label match={row['completed_label_match']}; evidence-valid match={row['evidence_valid_label_match']}.", "",
                      f"[Preserved result]({id}/{condition}/result.json)", "", "```json",
                      json.dumps({key: row[key] for key in ("observed", "raw_verdict", "final_output", "errors", "citations", "mechanisms")}, ensure_ascii=False, indent=2), "```", ""]
    lines += ["## Interpretation limits", "",
              f"These are **{summary['case_count']} constructed cases across {summary['event_family_count']} event families**. Cases in the same family are clustered. Agent-authored labels were reviewed before inference; this is development validation, not independent human adjudication or a standard held-out benchmark. No general superiority follows from this batch.", "",
              "Loop execution is separate from answer quality. Reanalysis requires an accepted revisit after another newly admitted version was analyzed. Verification feedback requires a previously generated gap, a new eligible saved source, decomposition and later verification in order. Historical resolutions are not reported as final while the gap remains open. Provenance status is a diagnostic, not independently established attribution accuracy.", "",
              "Earlier experiments remain preserved. Their sources and CLI prompt environment differ, so their token totals are not a controlled performance baseline for this batch.", "",
              ("Timing warning: a case has missing/invalid timing or a UTC-versus-runtime discrepancy exceeding one second. Do not rank speed from these measurements." if summary["timing_warning"] else "Recorded UTC and runtime intervals agree within one second per case. Timing remains a small uncontrolled sample, not a production reliability result."), "",
              f"All {summary['frozen_artifact_count']} frozen artifacts, case/condition denominators, labels, result sidecars and transport receipts were checked before scoring.", "",
              "[Protocol](../PROTOCOL.md) · [Isolation verification](../ISOLATION_REVIEW.json) · [Machine-readable summary](SUMMARY.json)"]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    result = summarize(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "results")
    print(json.dumps({key: result[key] for key in ("conditions", "stage_tokens", "both_loop_cases", "timing_warning")}, indent=2))
