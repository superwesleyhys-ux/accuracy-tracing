"""Export source-free evaluation receipts, or verify the published bundle.

Default export requires the private local experiment archives. --verify-public
uses only this script and reports/model-evaluation-20260908. Neither mode calls a
model, downloads sources, or changes an original experiment artifact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments/gstack-harness-eval-20260908"
PUBLIC = ROOT / "reports/model-evaluation-20260908"
CONDITIONS = ("direct", "double_loop")
VERDICTS = {"supported", "contradicted", "conflicting", "unresolved"}
BATCHES = (("original", "results", 6, 3), ("repair", "results-c03-repair", 1, 1))
PUBLIC_FILES = ("RESULTS.json", "RECEIPTS.json", "SOURCES.json", "README.md")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def count(value):
    return type(value) is int and value >= 0


def totals(receipts):
    known = [r["usage"] for r in receipts if count(r["usage"].get("input_tokens")) and count(r["usage"].get("output_tokens"))]
    cached = [u["cached_input_tokens"] for u in known if count(u.get("cached_input_tokens")) and u["cached_input_tokens"] <= u["input_tokens"]]
    input_tokens = sum(u["input_tokens"] for u in known)
    output_tokens = sum(u["output_tokens"] for u in known)
    return {"logical_calls": len(receipts), "successful_calls": sum(r["success"] is True for r in receipts),
            "known_usage_calls": len(known), "known_input_tokens": input_tokens, "known_output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens if receipts and len(known) == len(receipts) else None,
            "cached_input_tokens": sum(cached) if receipts and len(cached) == len(receipts) else None}


def batch_accounting(batch, receipts):
    labels = {g["case_id"]: g["expected_fact_status"] for g in batch["registered_labels"]}
    by_id = {r["id"]: r for r in receipts}
    conditions = {}
    for condition in CONDITIONS:
        runs = [r for r in batch["runs"] if r["condition"] == condition]
        relevant = [by_id[id] for run in runs for id in run["receipt_ids"]]
        conditions[condition] = {"cases": len(runs), "completed": sum(r["pipeline_success"] for r in runs),
                                 "registered_label_matches": sum(r["pipeline_success"] and r["visible_verdict"] == labels[r["case_id"]] for r in runs),
                                 "locally_audited_quote_integrity_matches": sum(r["pipeline_success"] and r["visible_verdict"] == labels[r["case_id"]] and r["locally_audited_quote_integrity"] for r in runs),
                                 **totals(relevant)}
    stages = defaultdict(list)
    for receipt in receipts:
        stages[receipt["condition"], receipt["stage"]].append(receipt)
    return {"conditions": conditions,
            "stages": [{"condition": condition, "stage": stage, **totals(items)} for (condition, stage), items in sorted(stages.items())]}


def canonical_url(value):
    parts = urlsplit(value)
    require(parts.scheme == "https" and parts.hostname and not parts.username and not parts.password, "Unsafe source URL")
    # Keep the public NIST document identifier, never request/cookie identifiers.
    query = urlencode([(key, val) for key, val in parse_qsl(parts.query) if parts.hostname == "tsapps.nist.gov" and key == "pub_id"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def source_rows():
    data = ARCHIVE / "data"
    sources = []
    for item in read(data / "source_index.json")["sources"]:
        meta = read(data / item["metadata_path"])
        for kind in ("raw", "text", "metadata"):
            require(digest(data / item[kind + "_path"]) == item[kind + "_sha256"], "Source metadata hash mismatch")
        licensed = item["version_id"] in {"s02", "s04"}
        sources.append({"version_id": item["version_id"], "title": meta["title"], "canonical_url": canonical_url(item["url"]),
                        "attribution": meta["issuer"], "role": "inference source" if item["version_id"] in {"s01", "s02", "s03", "s04", "s05", "s06"} else "access/adjudication audit only; excluded from inference pools",
                        "captured_at": meta["retrieved_at"], "observed_available_at": meta["observed_available_at"],
                        "raw_sha256": item["raw_sha256"], "text_sha256": item["text_sha256"], "metadata_sha256": item["metadata_sha256"],
                        "license": {"notice": "CC BY 4.0 stated by the published source" if licensed else "No blanket redistribution permission asserted; source and third-party credits apply",
                                    "url": "https://creativecommons.org/licenses/by/4.0/" if licensed else None},
                        "source_bytes_bundled": False})
    repair = ARCHIVE / "results/c03-repair-inputs"
    meta = read(repair / "sources/rydberg-news.metadata.json")
    original = next(s for s in sources if s["version_id"] == "s03")
    sources.append({**original, "version_id": "s03r", "role": "post-hoc repair source only",
                    "raw_sha256": digest(repair / "sources/rydberg-news.html"),
                    "text_sha256": digest(repair / "sources/rydberg-news.txt"),
                    "metadata_sha256": digest(repair / "sources/rydberg-news.metadata.json"),
                    "published_at": meta["published_at"], "extraction_change": "Restored the captured article dateline; complete source text remains local."})
    return {"scope": "Metadata for nine original captures plus one repaired extraction; source bytes, outbound-link lists and observed redirect URLs are excluded.",
            "hash_scope": "Hashes refer to the original local raw, extracted-text and metadata files, not downloaded current versions.", "sources": sources}


def export():
    require(all((ARCHIVE / folder / "all-results.json").is_file() for _, folder, _, _ in BATCHES),
            "Full local archives are required for export. Use --verify-public to check the published receipts without them.")
    receipts, batches, local_hashes = [], [], {}
    cli_version = read(ARCHIVE / "ISOLATION_REVIEW.json")["cli_version"]
    for batch_id, folder_name, expected_cases, families in BATCHES:
        folder = ARCHIVE / folder_name
        raw, summary = read(folder / "all-results.json"), read(folder / "SUMMARY.json")
        manifest = raw["manifest"]
        require(read(folder / "manifest.json") == manifest and all(v is True for v in manifest["integrity_checks"].values()), "Local manifest integrity failure")
        require(len(raw["results"]) == expected_cases * 2, "Incomplete local batch")
        for name, expected in manifest["frozen_sha256"].items():
            candidates = (ROOT / name, folder / "frozen-inputs" / name)
            require(any(p.is_file() and digest(p) == expected for p in candidates), "Unavailable frozen local input")
        corpus_path = folder / "frozen-inputs" / manifest["corpus_path"]
        gold_path = folder / "frozen-inputs" / manifest["gold_path"]
        corpus, gold = read(corpus_path), read(gold_path)
        require(raw["gold"] == gold, "Local labels differ from frozen labels")
        for key, path in {"aggregate": folder / "all-results.json", "manifest": folder / "manifest.json", "summary": folder / "SUMMARY.json", "corpus": corpus_path, "gold": gold_path}.items():
            local_hashes[f"{batch_id}.{key}"] = digest(path)
        summary_rows = {(r["id"], r["condition"]): r for r in summary["runs"]}
        batch = {"id": batch_id, "post_hoc": batch_id == "repair", "pooled_with_other_batches": False,
                 "case_count": expected_cases, "event_family_count": families,
                 "started_at": manifest["started_at"], "finished_at": manifest["finished_at"],
                 "configuration": {k: manifest[k] for k in ("model", "reasoning_effort", "tunnel", "workers", "timeout_seconds_per_call", "max_model_calls_per_harness_case", "max_total_logical_calls", "orchestration_retries", "internal_cli_transport_retries", "cross_route_fallback", "equal_token_budget")},
                 "cases": [{"id": c["target"]["id"], "target_text": c["target"]["text"], "as_of": c["target"]["as_of"],
                            "source_version_id": c["target"]["source_version_id"], "initial_version_ids": c["initial_version_ids"],
                            "pool_version_ids": [v["version_id"] for v in c["materials"]]} for c in corpus["cases"]],
                 "registered_labels": [{"case_id": g["id"], "expected_fact_status": g["expected_fact_status"]} for g in gold["cases"]], "runs": []}
        batch["configuration"]["local_cli_version"] = cli_version
        for run in raw["results"]:
            run_folder = folder / run["id"] / run["condition"]
            require(read(run_folder / "result.json") == run, "Local result sidecar mismatch")
            score = summary_rows[run["id"], run["condition"]]
            ids = []
            for ordinal, call in enumerate(run["calls"], 1):
                stem = run_folder / f"{ordinal:02d}-{call['stage']}"
                require(read(stem.with_suffix(".calls.json")) == [call], "Local receipt sidecar mismatch")
                receipt_id = f"{batch_id}:{run['id']}:{run['condition']}:{ordinal:02d}"
                ids.append(receipt_id)
                usage = call.get("usage") or {}
                receipts.append({"id": receipt_id, "batch": batch_id, "case_id": run["id"], "condition": run["condition"],
                                 "ordinal": ordinal, "stage": call["stage"], "model": call["model"], "reasoning_effort": call["reasoning_effort"],
                                 "tunnel": call["tunnel"], "success": call["success"], "status": call["status"],
                                 "timeout_seconds": call["timeout_seconds"], "wall_seconds": call["wall_seconds"],
                                 "local_skills_disabled": call.get("local_skills_disabled"),
                                 "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens")},
                                 "local_artifact_sha256": {kind: digest(stem.with_suffix(suffix)) if stem.with_suffix(suffix).is_file() else None
                                                           for kind, suffix in (("input", ".input.json"), ("response", ".response.json"), ("call", ".calls.json"))}})
            loop = score["mechanisms"] or {}
            batch["runs"].append({"case_id": run["id"], "condition": run["condition"], "visible_verdict": run["fact_status"],
                                  "raw_verdict": score["raw_verdict"], "pipeline_success": score["pipeline_success"],
                                  "registered_label_match": score["completed_label_match"],
                                  "locally_audited_quote_integrity": score["citations"]["passed"],
                                  "error_count": len(run["errors"]),
                                  "error_types": [e.get("type", "unspecified") for e in run["errors"]],
                                  "receipt_ids": ids, "logical_calls": len(ids),
                                  "loop_flags": {k: bool(loop.get(k, False)) for k in ("accepted_revisit_executed", "reanalysis_executed", "verification_feedback_executed", "both_loops_executed")},
                                  "elapsed_seconds": run["timer_seconds"], "clock_discrepancy": score["clock_discrepancy"]})
        own_receipts = [r for r in receipts if r["batch"] == batch_id]
        batch["accounting"] = batch_accounting(batch, own_receipts)
        for condition in CONDITIONS:
            actual, stored = batch["accounting"]["conditions"][condition], summary["conditions"][condition]
            require(actual["registered_label_matches"] == stored["completed_label_matches"] and actual["total_tokens"] == stored["total_tokens"] and actual["logical_calls"] == stored["model_calls"], "Recomputed public accounting differs from local summary")
        batches.append(batch)
    original = batches[0]
    subset = {condition: {"cases": 5, "registered_label_matches": sum(r["registered_label_match"] for r in original["runs"] if r["condition"] == condition and r["case_id"] != "c03")}
              for condition in CONDITIONS}
    results = {"schema_version": "1.0", "evaluation": "Astra through local Codex versus the same Astra with NewsVerify double-loop harness",
               "label_origin": "Agent-authored and agent-reviewed before inference; not independent human adjudication.",
               "batches": batches,
               "c03_defect": {"classification": "corpus_gold_defect", "post_hoc_review": True, "review_not_blind_to_outputs": True,
                              "registered_label_preserved": "supported", "strict_packet_relative_label_after_review": "unresolved",
                              "reason": "The original packet omitted the NIST article dateline asserted by the target; its quoted publication date identified the paper. The harness left the missing date unresolved.",
                              "original_scores_unchanged": True},
               "five_case_sensitivity_subset": {"source_batch": "original", "excluded_case": "c03", "post_hoc": True,
                                                "replaces_primary_score": False, "conditions": subset},
               "repair_limit": "Selected post-hoc c03r restores the captured news dateline and changes each measurement to each experimental shot together. Neither final citation list explicitly quotes the restored dateline. Repair results are never pooled with the original six cases.",
               "limits": ["Six constructed cases are clustered across three events; no general accuracy superiority is established.",
                          "The direct arm receives the entire eligible source pool immediately; the harness retrieves adaptively from the same finite pool with unequal computation.",
                          "Installed skill catalogs were excluded; built-in Codex instructions remain. This is not raw base-model API or offline-weight inference.",
                          "Quote-integrity and loop flags are locally audited claims; public receipts alone cannot verify semantic evidence or operation histories."]}
    receipt_document = {"scope": "49 logical transport invocations: 42 original and seven separately selected post-hoc calls. Internal CLI HTTP retries are not independently counted.", "receipts": receipts}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    write(PUBLIC / "RESULTS.json", results)
    write(PUBLIC / "RECEIPTS.json", receipt_document)
    write(PUBLIC / "SOURCES.json", source_rows())
    write(PUBLIC / "README.md", README)
    manifest = {"schema_version": "1.0", "raw_sources_bundled": False, "prompts_or_freeform_model_responses_bundled": False,
                "original_cases": 6, "original_runs": 12, "original_logical_calls": 42,
                "separate_post_hoc_cases": 1, "separate_post_hoc_runs": 2, "separate_post_hoc_logical_calls": 7,
                "total_public_receipts": 49, "source_metadata_records": 10,
                "exporter_sha256": digest(Path(__file__)), "local_archive_sha256": local_hashes,
                "public_file_sha256": {name: digest(PUBLIC / name) for name in PUBLIC_FILES},
                "verification_scope": "Recompute published accounting and denominators from sanitized receipts; source-free hashes cannot establish semantic accuracy or reproduce original inference."}
    write(PUBLIC / "MANIFEST.json", manifest)
    return verify_public()


def verify_public():
    manifest = read(PUBLIC / "MANIFEST.json")
    require(set(manifest["public_file_sha256"]) == set(PUBLIC_FILES), "Unexpected public artifact inventory")
    for name, expected in manifest["public_file_sha256"].items():
        require(digest(PUBLIC / name) == expected, f"Public artifact hash mismatch: {name}")
    require(digest(Path(__file__)) == manifest["exporter_sha256"], "Exporter version differs from the published manifest")
    results, receipt_document, sources = (read(PUBLIC / name) for name in ("RESULTS.json", "RECEIPTS.json", "SOURCES.json"))
    receipts = receipt_document["receipts"]
    require(len(receipts) == 49 == manifest["total_public_receipts"] and len({r["id"] for r in receipts}) == 49, "Expected 49 unique receipts")
    require(len(sources["sources"]) == 10 == manifest["source_metadata_records"], "Source metadata count differs")
    require(len(results["batches"]) == 2 and [b["id"] for b in results["batches"]] == ["original", "repair"], "Original and repair batches must stay separate")
    index = {r["id"]: r for r in receipts}
    for batch, (batch_id, _, expected_cases, _) in zip(results["batches"], BATCHES):
        ids = [c["id"] for c in batch["cases"]]
        labels = {g["case_id"]: g["expected_fact_status"] for g in batch["registered_labels"]}
        require(len(ids) == len(set(ids)) == batch["case_count"] == expected_cases and set(labels) == set(ids) and len(batch["registered_labels"]) == expected_cases, "Case/label denominator differs")
        require(all(label in VERDICTS for label in labels.values()), "Unknown registered label")
        require(len(batch["runs"]) == expected_cases * 2 and {(r["case_id"], r["condition"]) for r in batch["runs"]} == {(id, c) for id in ids for c in CONDITIONS}, "Missing or duplicate case/condition")
        used = []
        for run in batch["runs"]:
            require(len(run["receipt_ids"]) == run["logical_calls"], "Run call count differs")
            own = [index[id] for id in run["receipt_ids"]]
            require([r["ordinal"] for r in own] == list(range(1, len(own) + 1)), "Receipt order differs")
            for receipt in own:
                require((receipt["batch"], receipt["case_id"], receipt["condition"]) == (batch_id, run["case_id"], run["condition"]), "Receipt assigned to another run")
                require(receipt["model"] == "gpt-6-astra" and receipt["reasoning_effort"] == "medium" and receipt["tunnel"] == "local", "Inconsistent model or route")
                require(receipt["local_skills_disabled"] == 65 and receipt["success"] is True and receipt["status"] == "completed", "Receipt status/isolation differs from this completed run")
                require(receipt["stage"] in ({"direct"} if run["condition"] == "direct" else {"decompose", "select", "verify"}), "Unknown stage")
                require(all(count(receipt["usage"].get(k)) for k in ("input_tokens", "output_tokens", "cached_input_tokens")), "Missing or invalid receipt usage")
                require(receipt["usage"]["cached_input_tokens"] <= receipt["usage"]["input_tokens"], "Cached input exceeds input")
                require(all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in receipt["local_artifact_sha256"].values()), "Invalid local artifact hash")
            require(count(run["error_count"]) and run["error_count"] == len(run["error_types"]), "Error accounting differs")
            completed = bool(own) and not run["error_count"] and all(r["success"] for r in own) and run["visible_verdict"] in VERDICTS and run["raw_verdict"] in VERDICTS
            require(run["pipeline_success"] is completed, "Completion status differs from receipts")
            require(run["registered_label_match"] is (completed and run["visible_verdict"] == labels[run["case_id"]]), "Label score differs")
            require(len(own) <= (1 if run["condition"] == "direct" else 10), "Logical call budget exceeded")
            used.extend(run["receipt_ids"])
        own_receipts = [r for r in receipts if r["batch"] == batch_id]
        require(len(used) == len(set(used)) == len(own_receipts) and set(used) == {r["id"] for r in own_receipts}, "Extra or omitted receipts")
        require(batch_accounting(batch, own_receipts) == batch["accounting"], "Published accounting differs from receipts")
        require(batch["post_hoc"] is (batch_id == "repair") and batch["pooled_with_other_batches"] is False, "Repair pooling or scope changed")
        prefix = "original" if batch_id == "original" else "separate_post_hoc"
        require(manifest[prefix + "_cases"] == len(ids) and manifest[prefix + "_runs"] == len(batch["runs"])
                and manifest[prefix + "_logical_calls"] == len(own_receipts), "Manifest counts differ from published runs/receipts")
    primary, repair = [b["accounting"]["conditions"] for b in results["batches"]]
    require(primary["direct"]["registered_label_matches"] == 6 and primary["double_loop"]["registered_label_matches"] == 5, "Original registered scores changed")
    require(primary["direct"]["total_tokens"] == 104986 and primary["double_loop"]["total_tokens"] == 600318, "Original token totals changed")
    require(repair["direct"]["total_tokens"] == 18137 and repair["double_loop"]["total_tokens"] == 98216, "Repair token totals changed")
    for condition in CONDITIONS:
        subset = [r for r in results["batches"][0]["runs"] if r["condition"] == condition and r["case_id"] != "c03"]
        require(results["five_case_sensitivity_subset"]["conditions"][condition] == {"cases": len(subset), "registered_label_matches": sum(r["registered_label_match"] for r in subset)}, "Sensitivity subset differs")
    for name in PUBLIC_FILES:
        text = (PUBLIC / name).read_text(encoding="utf-8")
        require(not re.search(r'/Users/|/private/var/folders/|"(?:session_id|thread_id|conversation_id)"|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', text), "Excluded personal or credential-shaped content in public export")
    return {"passed": True, "original_cases": 6, "original_registered_matches": {"direct": 6, "double_loop": 5},
            "separate_post_hoc_cases": 1, "public_receipts": len(receipts), "no_model_calls": True,
            "verification": "Published hashes, case/condition denominators, registered-label accounting and usage totals; not semantic source verification."}


README = """# Astra versus the double-loop harness: public results

The local test used the same Astra model with and without the harness. Gstack
guided development review; its skill catalog was excluded from both model paths.
Normal Codex instructions remain. This is not raw base-model API inference.

| Original six cases | Astra alone | Astra + harness |
|---|---:|---:|
| Completed runs | 6/6 | 6/6 |
| Matches to registered labels | 6/6 | 5/6 |
| Logical calls | 6 | 36 |
| Input + output tokens | 104,986 | 600,318 |

The harness used **5.72×** the tokens. Decomposition and revisits consumed
**51.1%** (306,478); verification 41.0% (245,969); selection 8.0% (47,871).
Cached input is already included. These are not monetary cost ratios.

The score difference is not an established accuracy advantage. Case **c03 had
a corpus/gold defect**: its claim named the NIST article date, but the evidence
packet omitted that dateline and supplied the paper date. The harness left the
missing qualifier unresolved. Original labels, all six denominators and outputs
remain preserved. A separately reported, post-hoc five-case subset ties **5/5**.

The selected **c03r post-hoc repair** restores the captured dateline and changes
“each measurement” to “each experimental shot” together. Both paths returned
supported: Astra used one call/18,137 tokens; the harness six calls/98,216 tokens.
It is **never pooled into the original score**. Neither final citation list
explicitly quotes the restored news dateline, although it is available in the
repaired packet. Quote integrity does not establish exhaustive qualifier coverage.

All **49 logical calls succeeded**: 42 original plus seven separate follow-up
calls. Both loops executed in five original cases and in the repaired case.
Internal CLI HTTP retries are not independently counted. The six original cases
are clustered across three events with agent-authored, agent-reviewed labels.
Astra alone sees the full eligible pool immediately; the harness selects from
that finite pool over multiple calls. There is no equal-token budget, independent
human adjudication, or demonstrated general accuracy winner.

## Public files

- [RESULTS.json](RESULTS.json): constructed targets, separate registered labels,
  all run outcomes/error counts, locally audited loop flags and separate scores.
- [RECEIPTS.json](RECEIPTS.json): 49 sanitized usage receipts with SHA-256 hashes
  of local input, response and original receipt files. No prompt or response text.
- [SOURCES.json](SOURCES.json): canonical source URLs, attribution, capture times,
  license notices and raw/text hashes. No third-party document bytes.
- [MANIFEST.json](MANIFEST.json): public-file hashes and hashes identifying the
  retained local archives.

Full sources, prompts, freeform model responses, private runtime logs and frozen
archive copies remain local under the repository's [contribution policy](../../CONTRIBUTING.md).
The public bundle supports recomputing accounting; it cannot independently verify
semantic evidence, quoted spans or complete loop histories. Hashes identify omitted
artifacts but do not substitute for access to them. Current downloads and hosted
model outputs can differ from the frozen evaluation.

From the repository root, verify this public bundle without archives or inference:

```sh
python3 tools/export_model_evaluation.py --verify-public
```

The [exporter](../../tools/export_model_evaluation.py) can regenerate the same
bundle without inference when the original full local archives are available:

```sh
python3 tools/export_model_evaluation.py
```

No claim is made that a fresh public clone can reproduce the original model
answers or source-level audits using these receipts alone.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-public", action="store_true", help="Verify public accounting without reading local archives")
    args = parser.parse_args()
    try:
        result = verify_public() if args.verify_public else export()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, "Evaluation export/verification failed: " + str(exc) + "\n")
    print(json.dumps(result, indent=2))
