"""Preregistered development rounds and final historical paired confirmation.

Default: validate only. --run requires reviewed frozen inputs, registration and
the macOS filesystem sandbox. --self-test runs synthetic local stubs, no model.
The supervisor reads registration commitments, never future gold or a scorer.
Only the plan's selected canonical cases enter the isolated inference worker.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OLD_VALIDATOR = ROOT / "experiments/historical-cutoff-20260908/run_test.py"
OLD_TRANSPORT = ROOT / "experiments/double-loop-pilot/run_test.py"
historical = runpy.run_path(str(OLD_VALIDATOR))
read, dump, sha = (historical[name] for name in ("read", "dump", "sha"))
require, object_hash = (historical[name] for name in ("require", "object_hash"))
TEMPORAL_INSTRUCTION = historical["TEMPORAL_INSTRUCTION"]
DIRECT_PROMPT = historical["DIRECT_PROMPT"]
MODEL, EFFORT, TIMEOUT = "gpt-6-astra", "medium", 90
MAX_CALLS, CLAIM_CALLS = 24, 10
CONDITIONS = ("direct", "news_tracing")
FROZEN_CORPUS_SHA256 = "b5ad5c900145a7a5b208fe8752c1051119d2be18bfa45ececd4d025f6dcf2826"
REGISTRATION_HASH_FIELDS = {"corpus_sha256", "gold_sha256", "scorer_sha256", "helper_sha256",
                            "input_review_sha256", "gold_review_sha256", "driver_sha256",
                            "plan_sha256", "protocol_sha256", "code_manifest_sha256"}
DEVELOPMENT_CASES = ["h01", "h02", "h05", "h06"]
CONFIRMATION_CASES = [f"h{i:02d}" for i in range(1, 9)]


def validate_corpus(corpus, live=False):
    packets, descriptions = historical["validate_corpus"](corpus)
    require(not live or [p["target"]["id"] for p in packets] in (DEVELOPMENT_CASES, CONFIRMATION_CASES),
            "Live comparison requires a complete registered case set")
    for packet in packets:
        require(len(packet["materials"]) == 2, "Each case must retain exactly two source versions")
        value = packet["config"].get("max_documents", 6)
        require(type(value) is int and 1 <= value <= 20, "Invalid per-case document cap")
    return packets, descriptions


def news_payload(case, research_mode="full"):
    require(research_mode in {"full", "claim"}, "Unknown research mode")
    target = case["target"]
    return {"news": [{"id": target["id"], "text": target["text"],
        "claims": [target["text"]], "materials": deepcopy(case["materials"]),
        "as_of": target["as_of"], "source_version_id": target["source_version_id"]}],
        "config": {"depth": 1, "max_queries": 2, "max_claims": 1, "research_mode": research_mode,
            "max_documents": case["config"].get("max_documents", 6), "max_searches": 0,
            "max_origin_depth": 0, "max_origin_calls": CLAIM_CALLS}}


def validate_plan(plan, stub=False):
    require(isinstance(plan, dict) and set(plan) == {"schema_version", "round_id", "phase", "development_round",
            "case_ids", "conditions", "max_development_rounds", "research_mode"}, "Unexpected optimization plan fields")
    require(type(plan["schema_version"]) is int and plan["schema_version"] == 2
            and type(plan["development_round"]) is int and 1 <= plan["development_round"] <= 3
            and type(plan["max_development_rounds"]) is int and plan["max_development_rounds"] == 3,
            "Optimization is limited to three development rounds")
    require(plan["research_mode"] in {"full", "claim"}, "Research mode must be explicitly registered")
    require(plan["phase"] in {"development", "confirmation"}
            and plan["round_id"] == (f"round-{plan['development_round']}" if plan["phase"] == "development" else "confirmation")
            and plan["conditions"] == list(CONDITIONS), "Round identity or arm conditions differ")
    expected = DEVELOPMENT_CASES if plan["phase"] == "development" else CONFIRMATION_CASES
    require(plan["case_ids"] == expected or stub and plan["case_ids"] == ["h01"], "Plan case denominator differs")
    return plan


def code_inventory():
    files = [Path(__file__).resolve(), OLD_VALIDATOR, OLD_TRANSPORT]
    files += sorted((ROOT / "newsverify").rglob("*.py"))
    return {"schema_version": 1, "files": {str(p.relative_to(ROOT)): sha(p) for p in files}}


def prepare(plan_path, code_manifest_path):
    validate_plan(read(plan_path))
    path = Path(code_manifest_path)
    require(not path.exists(), "Code commitment already exists; never overwrite a registered inventory")
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(path, code_inventory())
    return {"inference_started": False, "plan_sha256": sha(plan_path),
            "code_manifest_sha256": sha(path), "driver_sha256": sha(__file__)}


def validate_registration(value, commitments):
    require(isinstance(value, dict) and set(value) == REGISTRATION_HASH_FIELDS | {"schema_version", "registered_at"},
            "Registration requires version, timestamp and the ten artifact hashes only")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "Invalid registration version")
    require(all(isinstance(value[k], str) and re.fullmatch(r"[0-9a-f]{64}", value[k])
                for k in REGISTRATION_HASH_FIELDS), "Registration hashes must be lowercase SHA256")
    require(all(value[key] == expected for key, expected in commitments.items()),
            "Registration differs from current round inputs or executable inventory")
    require(isinstance(value["registered_at"], str), "Registration time must be ISO text")
    registered = datetime.fromisoformat(value["registered_at"].replace("Z", "+00:00"))
    require(registered.utcoffset() is not None and registered <= datetime.now(timezone.utc),
            "Registration must be timezone-aware and precede inference")


def block_source_network():
    from newsverify.news_sources import NewsSourceCollector
    def forbidden(*args, **kwargs):
        raise RuntimeError("Live source collection is forbidden in this historical comparison")
    NewsSourceCollector.fetch = forbidden
    NewsSourceCollector.search = forbidden
    NewsSourceCollector._download = forbidden
    return forbidden


def transport_class(shared, stub):
    class HistoricalLocal(shared["RecordedLocal"]):
        def __init__(self, *, case, condition, destination):
            super().__init__(model=MODEL, reasoning_effort=EFFORT, timeout=TIMEOUT)
            self.case = case
            self.condition = condition
            self.destination = destination
            self.max_calls = 1 if condition == "direct" else MAX_CALLS
            self.deadline = time.monotonic() + self.max_calls * TIMEOUT + 30
            self.guard_blocked_calls = []

        def generate(self, stage, instructions, packet, schema):
            remaining = self.deadline - time.monotonic()
            if len(self.calls) >= self.max_calls or remaining <= 0:
                reason = "case_call_budget" if len(self.calls) >= self.max_calls else "case_deadline"
                self.guard_blocked_calls.append({"stage": stage, "reason": reason})
                raise shared["tunnels"].TunnelError("Historical case call budget or deadline exhausted; no request sent.")
            self.timeout = min(TIMEOUT, remaining)
            self.current_stage = stage
            augmented = deepcopy(packet)
            require("historical_target" not in augmented, "Reserved historical_target field already present")
            augmented["historical_target"] = deepcopy(self.case["target"])
            print(f"{self.case['target']['id']} / {self.condition}: {len(self.calls)+1:02d} {stage} started", flush=True)
            try:
                return super().generate(stage, TEMPORAL_INSTRUCTION + "\n" + instructions, augmented, schema)
            finally:
                status = self.calls[-1]["status"] if self.calls else "failed_before_request"
                print(f"{self.case['target']['id']} / {self.condition}: {stage} {status}", flush=True)

    if stub:
        HistoricalLocal._generate = stub_generate
    return HistoricalLocal


def stub_generate(self, instructions, evidence, schema, record):
    """Exercise all imported research phases and both formal source versions."""
    packet = json.loads(evidence.split("EVIDENCE PACKET:\n", 1)[1])
    require(instructions.startswith(TEMPORAL_INSTRUCTION), "Missing temporal prefix")
    require(packet["historical_target"] == self.case["target"], "Historical target changed")
    record.update(test_stub=True, local_skills_disabled=None, exit_code=0,
                  usage={"input_tokens": 11, "output_tokens": 3})
    stage = self.current_stage
    first, second = self.case["materials"]
    proposals = {
        "deconstruct": {"core_event": self.case["target"]["text"], "date": "2023-01-01",
            "entities": {"people": [], "organizations": [], "locations": []},
            "key_claims": [self.case["target"]["text"]], "causal_hints": []},
        "search_plan": {"queries": [{"angle": "source", "query": "Synthetic source record"}]},
        "source_trace": {"sources": [{"url": first["url"], "outlet": first["issuer"],
            "publish_time": "2023-01-01", "source_type": "research report", "is_original": False,
            "facts": [{"claim": first["content"], "date_mentioned": "2023-01-01"}]}]},
        "source_verify": {"consistent_facts": [], "disputed_facts": [], "credibility_note": "Unverified fixture."},
        "causal_dig": {"causes": [{"title": "Earlier report", "date": "2023-01-01", "summary": "Unverified proposed background.",
            "relation": "Proposed background only", "sources": [{"url": first["url"], "title": first["issuer"]}],
            "confidence": 0.0, "grounded": False, "is_root": True}]},
        "grounding_check": {"checks": [{"node_id": "event_001", "event_title": "Earlier report", "grounded": False,
            "matching_urls": [], "note": "No independent causal evidence."}]},
        "timeline_build": {"events": [{"title": "Report", "date": "2023-01-01", "description": "A report made a claim.",
            "significance": "重大", "sources": [{"url": first["url"], "title": first["issuer"]}],
            "causal_links": [], "source_count": 1}]},
        "perspective": {"perspectives": [{"event_id": "timeline_000", "event_title": "Report", "views": [], "divergence_note": "No contrast supplied."}]},
        "synthesis": {"key_findings": [], "information_gaps": ["Synthetic fixture only."], "causal_summary": "", "bias_notes": []},
    }
    if stage in proposals:
        return proposals[stage]
    if stage == "direct_response":
        return {"text": "Unverified synthetic research draft."}
    if stage == "select":
        return {"version_id": packet["catalog"][0]["version_id"], "rationale": "Inspect the other supplied record."}
    if stage == "decompose":
        material = packet["material"]
        known = {m["version_id"] for m in packet["context"]["materials"]} | {material["version_id"]}
        result = {"fragments": [{"id": "fact", "text": material["content"], "quote": material["content"], "qualifiers": []}],
            "relations": [], "gaps": [], "resolutions": [], "origins": [], "revisit_versions": [], "notes": "Synthetic source annotation."}
        if material["version_id"] == first["version_id"]:
            result["relations"] = [{"id": "upstream", "from_version": first["version_id"],
                "to_version": second["version_id"] if second["version_id"] in known else None,
                "kind": "cites", "status": "direct" if second["version_id"] in known else "declared",
                "basis": [{"version_id": first["version_id"], "quote": first["content"]}],
                "upstream_locator": second["url"], "rationale": "The fixture explicitly cites the source."}]
        else:
            basis = [{"version_id": second["version_id"], "quote": second["content"]}]
            result["origins"] = [{"version_id": second["version_id"], "basis": basis,
                "material_kind": "original_record", "rationale": "Synthetic producing record."}]
            result["resolutions"] = [{"gap_id": "origin:" + packet["target"]["id"], "basis": basis,
                "rationale": "Synthetic source record obtained."}]
            result["revisit_versions"] = [first["version_id"]]
        return result
    require(stage in {"direct", "verify"}, "Unexpected synthetic stage")
    response = {"verdict": "supported", "basis": [{"version_id": first["version_id"], "quote": first["content"]}],
                "rationale": "The supplied synthetic report states the attributed count."}
    if stage == "verify":
        response.update(gaps=[], resolutions=[])
    return response


def run_one(case, condition, output, cls, shared, forbidden_collector, research_mode="full"):
    destination = output / case["target"]["id"] / condition
    destination.mkdir(parents=True, exist_ok=False)
    result = {"id": case["target"]["id"], "condition": condition, "route": "local",
              "started_at": datetime.now(timezone.utc).isoformat(), "errors": []}
    started, transport = time.perf_counter(), None
    try:
        transport = cls(case=case, condition=condition, destination=destination)
        if condition == "direct":
            from newsverify.model_runner import VERDICT_SCHEMA, validate_output
            response = transport.generate("direct", DIRECT_PROMPT,
                {"target": case["target"], "materials": case["materials"]}, VERDICT_SCHEMA)
            result["raw_response"] = response
            validate_output(response, VERDICT_SCHEMA)
            result["fact_status"] = response["verdict"]
        else:
            from newsverify.news_tracing_runner import run_news_tracing
            payload = news_payload(case, research_mode)
            dump(destination / "news-input.json", payload)
            report = run_news_tracing(payload, tunnel="local", transport=transport,
                timeout=TIMEOUT, max_model_calls=MAX_CALLS, collector_factory=forbidden_collector)
            result["news_report"] = report
            require(len(report["results"]) == 1 and len(report["results"][0]["claims"]) == 1,
                    "Integrated harness changed the one-item/one-claim denominator")
            item = report["results"][0]
            claim = item["claims"][0]
            result.update(report=claim["trace"], fact_status=claim["fact_status"],
                          errors=deepcopy(item["errors"]), news_item_status=item["status"])
            if item["status"] != "completed" and not result["errors"]:
                result["errors"].append({"type": "IncompleteNewsItem", "message": "Integrated news item did not complete."})
    except Exception as exc:
        message = str(exc) if isinstance(exc, shared["tunnels"].TunnelError) else "No valid final result; inspect retained stage artifacts."
        result.update(fact_status="execution_failed", errors=result["errors"] + [{"type": type(exc).__name__, "message": message}])
    result["calls"] = deepcopy(transport.calls) if transport is not None else []
    result["guard_blocked_calls"] = deepcopy(transport.guard_blocked_calls) if transport else []
    result["timer_seconds"] = time.perf_counter() - started
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["utc_elapsed_seconds"] = (datetime.fromisoformat(result["finished_at"]) - datetime.fromisoformat(result["started_at"])).total_seconds()
    dump(destination / "result.json", result)
    print(f"{result['id']} / {condition}: {result['fact_status']}, {len(result['calls'])} calls, {len(result['errors'])} errors", flush=True)
    return result


def worker(stub=False):
    policy = read(HERE / "worker-policy.json")
    historical["check_denied_roots"](policy["denied_roots"])
    for path in policy["denied_files"]:
        try:
            with open(path, "rb"):
                pass
        except PermissionError:
            continue
        raise ValueError("Protected registration file was readable")
    require(sha(HERE / "inputs/corpus.json") == policy["corpus_sha256"], "Worker corpus changed")
    packets, _ = validate_corpus(read(HERE / "inputs/corpus.json"), live=not stub)
    require([p["target"]["id"] for p in packets] == policy["case_ids"], "Worker case denominator changed")
    require(policy.get("research_mode") in {"full", "claim"}, "Worker research mode is missing")
    sys.path.insert(0, str(ROOT))
    shared = runpy.run_path(str(OLD_TRANSPORT))
    shared["tunnels"].subprocess = shared["LocalHTTPProcess"]()
    forbidden = block_source_network()
    cls = transport_class(shared, stub)
    output = ROOT / "worker-results"
    output.mkdir()
    dump(output / "isolation.json", {"filesystem_denial_verified": True, "source_network_disabled": True,
        "registration_loaded": False, "gold_loaded": False, "test_stub": stub})
    rows = []
    for index, case in enumerate(packets):
        for condition in CONDITIONS if index % 2 == 0 else tuple(reversed(CONDITIONS)):
            rows.append(run_one(case, condition, output, cls, shared, forbidden, policy["research_mode"]))
            dump(output / "progress.json", {"completed": len(rows), "expected": len(packets) * 2})
            dump(output / "predictions.json", {"results": rows, "gold_loaded": False, "test_stub": stub})


def launch(corpus_path, review_path, output, denied_roots=(), stub=False, registration_path=None,
           *, plan_path, protocol_path, code_manifest_path):
    corpus_path, review_path, output = (Path(p).resolve() for p in (corpus_path, review_path, output))
    corpus_hash = sha(corpus_path)
    require(stub or corpus_hash == FROZEN_CORPUS_SHA256, "Live corpus differs from the original frozen eight-case corpus")
    corpus = read(corpus_path)
    # The immutable archive has its own historical case order. Only the
    # derived worker packet must follow the explicitly registered round order.
    validate_corpus(corpus)
    plan_path, protocol_path, code_manifest_path = (Path(p).resolve() for p in (plan_path, protocol_path, code_manifest_path))
    plan = validate_plan(read(plan_path), stub=stub)
    cases = {case["target"]["id"]: case for case in corpus["cases"]}
    require(set(plan["case_ids"]) <= set(cases), "Planned cases are missing from canonical corpus")
    selected = {"schema_version": 1, "cases": [cases[cid] for cid in plan["case_ids"]]}
    packets, descriptions = validate_corpus(selected, live=not stub)
    inventory = read(code_manifest_path)
    require(inventory == code_inventory(), "Registered executable inventory differs from current code")
    commitments = {"corpus_sha256": corpus_hash, "driver_sha256": sha(__file__),
                   "plan_sha256": sha(plan_path), "protocol_sha256": sha(protocol_path),
                   "code_manifest_sha256": sha(code_manifest_path)}
    review = read(review_path)
    flags = {"passed", "cutoff_evidence_reviewed", "claim_dates_reviewed", "future_gold_separated", "variant_transforms_reviewed"}
    require(isinstance(review, dict) and set(review) <= flags | {"corpus_sha256", "local_transport_ready"},
            "Preflight must contain only boolean gates and corpus hash")
    require(review.get("corpus_sha256") == corpus_hash and all(review.get(k) is True for k in flags),
            "Reviewed corpus/cutoff/variant preflight required")
    require(stub or review.get("local_transport_ready") is True, "Local transport preflight required")
    registration_hash = None
    if not stub or registration_path is not None:
        registration_path = Path(registration_path or HERE / "REGISTRATION.json").resolve()
        registration_hash = sha(registration_path)
        validate_registration(read(registration_path), commitments)
        require(sha(registration_path) == registration_hash, "Registration changed during validation")
    require(not output.exists(), "Output already exists; prior attempts must not be overwritten")
    sandbox = shutil.which("sandbox-exec")
    require(sys.platform == "darwin" and sandbox, "A working macOS filesystem sandbox is mandatory; no fallback")
    deny_existing = {ROOT.resolve(), corpus_path.parent, *(Path(p).resolve() for p in denied_roots)}
    require(all(p.is_dir() for p in deny_existing), "Protected roots must exist")
    hashes = inventory["files"]
    output.mkdir(parents=True)
    dump(output / "worker-corpus.json", selected)
    worker_corpus_hash = sha(output / "worker-corpus.json")
    for source, name, expected in ((corpus_path, "corpus.json", corpus_hash),
        (plan_path, "plan.json", commitments["plan_sha256"]),
        (protocol_path, "protocol.md", commitments["protocol_sha256"]),
        (code_manifest_path, "code-manifest.json", commitments["code_manifest_sha256"])):
        shutil.copyfile(source, output / name)
        require(sha(output / name) == expected, "Round commitment changed during freeze")
    deny = sorted(deny_existing | {output}, key=str)
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "model": MODEL, "reasoning_effort": EFFORT,
        "tunnel": "local", "conditions": list(CONDITIONS), "case_count": len(packets), "workers": 1,
        "max_logical_calls": len(packets) * (1 + MAX_CALLS), "max_model_calls_per_harness_case": MAX_CALLS,
        "max_model_calls_per_claim_trace": CLAIM_CALLS, "timeout_seconds_per_call": TIMEOUT,
        "case_deadline_seconds": {"direct": TIMEOUT + 30, "news_tracing": MAX_CALLS * TIMEOUT + 30},
        "orchestration_retries": 0, "internal_cli_retries": "not independently bounded or counted",
        "cross_route_fallback": False, "gold_loaded": False, "test_stub": stub,
        "corpus_sha256": corpus_hash, "review_sha256": sha(review_path), "case_inputs": descriptions,
        "worker_corpus_sha256": worker_corpus_hash, "plan_sha256": commitments["plan_sha256"],
        "protocol_sha256": commitments["protocol_sha256"], "code_manifest_sha256": commitments["code_manifest_sha256"],
        "round_id": plan["round_id"], "phase": plan["phase"], "development_round": plan["development_round"],
        "case_ids": plan["case_ids"], "research_mode": plan["research_mode"],
        "registration_sha256": registration_hash, "frozen_code_sha256": hashes,
        "temporal_instruction": TEMPORAL_INSTRUCTION, "direct_prompt": DIRECT_PROMPT,
        "local_connection_profile": "explicit ephemeral Codex-login HTTP",
        "local_profile_options": ["-c", 'model_provider="double_loop_local_http"', "-c",
            'model_providers.double_loop_local_http={name="Codex login HTTP",wire_api="responses",requires_openai_auth=true,supports_websockets=false}'],
        "filesystem_isolation": "sandbox-exec denies original repository, corpus directory, output and declared private roots",
        "denied_roots": [str(p) for p in deny], "source_network_disabled": True,
        "model_memory_erased": False, "equal_token_budget": False,
        "baseline_evidence_access": "both exact eligible source versions immediately",
        "harness_evidence_access": "actual integrated research excerpts then adaptive formal verification over the same two versions",
        "research_excerpt_limits": {"per_document_characters": 16000, "total_characters": 60000,
            "duplicate_url_policy": "all eligible versions retained; fair allocation across versions; offsets explicit"},
        "research_advice": {"maximum_serialized_characters": 6000, "untrusted": True,
            "formal_stages": ["decompose", "select", "verify"], "admitted_as_evidence": False},
        "discovery_scope": "No new sources. Fixed explicit claim; bounded untrusted research advice may guide selection or reinspection, never supply evidence.",
        "news_payloads": [{"id": p["target"]["id"], "sha256": object_hash(news_payload(p, plan["research_mode"])),
                           "config": news_payload(p, plan["research_mode"])["config"]} for p in packets]}
    dump(output / "manifest.json", manifest)
    denied_files = [plan_path, protocol_path, code_manifest_path, review_path,
                    output / "plan.json", output / "protocol.md", output / "code-manifest.json"]
    if registration_hash:
        archive = output / "registration.json"
        shutil.copyfile(registration_path, archive)
        require(sha(archive) == registration_hash, "Registration changed during freeze")
        denied_files.extend([registration_path, archive])
    with tempfile.TemporaryDirectory(prefix="optimization-round-worker-") as temporary:
        isolated = Path(temporary).resolve()
        require(not any(isolated.is_relative_to(p) for p in deny), "Worker overlaps protected roots")
        for name, expected in hashes.items():
            archive = output / "frozen-inputs" / name
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, archive)
            require(sha(archive) == expected, "Code changed during freeze")
            destination = isolated / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, destination)
            require(sha(destination) == expected, "Worker code changed during copy")
        worker_here = isolated / "experiments/harness-optimization-20260909"
        destination = worker_here / "inputs/corpus.json"
        destination.parent.mkdir(parents=True)
        shutil.copyfile(output / "worker-corpus.json", destination)
        require(sha(destination) == worker_corpus_hash, "Worker corpus changed during freeze")
        shutil.copyfile(review_path, output / "preflight.json")
        require(sha(output / "preflight.json") == manifest["review_sha256"], "Preflight changed during freeze")
        dump(worker_here / "worker-policy.json", {"corpus_sha256": worker_corpus_hash, "case_ids": plan["case_ids"],
            "research_mode": plan["research_mode"],
            "denied_roots": [str(p) for p in deny], "denied_files": [str(p) for p in denied_files]})
        command = [sandbox, "-p", historical["sandbox_profile"](deny, denied_files),
            sys._base_executable, "-I", "-S", "-B", str(worker_here / "run_round.py"), "--worker"]
        if stub:
            command.append("--stub")
        env = {k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "CODEX_API_KEY", "PYTHONPATH", "PYTHONHOME"}}
        started = time.perf_counter()
        process = subprocess.Popen(command, cwd=isolated, env=env, start_new_session=True)
        def stop():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        try:
            code = process.wait(timeout=len(packets) * ((MAX_CALLS + 1) * TIMEOUT + 60) + 120)
        except subprocess.TimeoutExpired:
            stop()
            code = -1
        except BaseException:
            stop()
            raise
        finally:
            if (isolated / "worker-results").exists():
                shutil.copytree(isolated / "worker-results", output / "stage-artifacts")
        manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), timer_seconds=time.perf_counter() - started,
            worker_exit_code=code, frozen_integrity={name: sha(ROOT / name) == expected for name, expected in hashes.items()})
        dump(output / "manifest.json", manifest)
        require(code == 0 and all(manifest["frozen_integrity"].values()), "Worker failed or frozen code changed; partial receipts retained")
    return output


def self_test(retain_output=None, research_mode="claim"):
    if retain_output is not None:
        retain_output = Path(retain_output).resolve()
        require(not retain_output.exists(), "Self-test output must be a fresh directory")
    with tempfile.TemporaryDirectory(prefix="optimization-round-offline-") as temporary:
        base = Path(temporary)
        private = base / "private"
        private.mkdir()
        material = {"version_id": "v1", "url": "https://fixture.invalid/article",
            "content": "The report stated seven. Source: https://fixture.invalid/record",
            "retrieved_at": "2026-01-01T00:00:00Z", "published_at": "2023-01-01T00:00:00Z",
            "available_at": "2023-01-01T00:00:00Z", "availability_basis": "Synthetic fixture only.", "issuer": "Fixture"}
        second = {**material, "version_id": "v2", "url": "https://fixture.invalid/record",
                  "content": "The producing record reported seven."}
        corpus = {"schema_version": 1, "cases": [{"target": {"id": "h01", "text": "The report stated seven.",
            "as_of": "2023-12-31T23:59:59Z", "source_version_id": "v1"}, "claim_made_at": "2023-01-01T00:00:00Z",
            "materials": [material, second], "initial_version_ids": ["v1"], "config": {"max_documents": 6}}]}
        corpus_path = private / "corpus.json"
        dump(corpus_path, corpus)
        dump(private / "gold.json", {"SECRET_LATER_GOLD": "MUST_NOT_APPEAR"})
        review = {key: True for key in ("passed", "cutoff_evidence_reviewed", "claim_dates_reviewed", "future_gold_separated", "variant_transforms_reviewed")}
        review["corpus_sha256"] = sha(corpus_path)
        dump(base / "review.json", review)
        plan = {"schema_version": 2, "round_id": "round-2", "phase": "development", "development_round": 2,
                "case_ids": ["h01"], "conditions": list(CONDITIONS), "max_development_rounds": 3,
                "research_mode": research_mode}
        dump(base / "plan.json", plan)
        (base / "protocol.md").write_text("Synthetic no-model protocol fixture.\n", encoding="utf-8")
        dump(base / "code-manifest.json", code_inventory())
        registration = {key: "a" * 64 for key in REGISTRATION_HASH_FIELDS}
        registration.update(schema_version=1, registered_at="2023-01-01T00:00:00+00:00",
                            corpus_sha256=sha(corpus_path), driver_sha256=sha(__file__),
                            plan_sha256=sha(base / "plan.json"), protocol_sha256=sha(base / "protocol.md"),
                            code_manifest_sha256=sha(base / "code-manifest.json"))
        dump(base / "registration.json", registration)
        output = launch(corpus_path, base / "review.json", base / "results", stub=True,
                        registration_path=base / "registration.json", plan_path=base / "plan.json",
                        protocol_path=base / "protocol.md", code_manifest_path=base / "code-manifest.json")
        predictions = read(output / "stage-artifacts/predictions.json")["results"]
        require(len(predictions) == 2 and all(not r["errors"] for r in predictions), "Paired synthetic run failed")
        require({r["condition"] for r in predictions} == set(CONDITIONS), "Condition labels changed")
        harness = next(r for r in predictions if r["condition"] == "news_tracing")
        phases = harness["news_report"]["results"][0]["analysis"]["report"]["phase_status"]
        required = {"deconstruct", "search_plan", "source_trace", "source_verify", "synthesis"}
        omitted = {"causal_dig", "grounding_check", "timeline_build", "perspective", "direct_response"}
        if research_mode == "full":
            required |= omitted
        require(required <= {p["stage"] for p in phases if p["status"] == "completed"}, "Synthetic research stages did not complete")
        if research_mode == "claim":
            require(omitted <= {p["stage"] for p in phases if p["status"] == "skipped"}
                    and not omitted & {call["stage"] for call in harness["calls"]}, "Claim mode skipped-stage scope differs")
        require({"decompose", "verify", "select"} <= {c["stage"] for c in harness["calls"]}, "Formal adaptive loop was not exercised")
        inputs = list((output / "stage-artifacts").rglob("*.input.json"))
        require(inputs and all(read(p)["instructions"].startswith(TEMPORAL_INSTRUCTION)
                and read(p)["packet"]["historical_target"] == corpus["cases"][0]["target"] for p in inputs), "Temporal boundary changed")
        require(all("SECRET_LATER_GOLD" not in p.read_text() for p in inputs), "Gold fixture leaked")
        require(all("gold_sha256" not in p.read_text() and "a" * 64 not in p.read_text() for p in inputs), "Registration entered a model request")
        require(read(output / "worker-corpus.json") == corpus, "Worker subset projection changed")
        for path in inputs:
            actual = read(path)
            packet = actual["packet"]
            if "fetched_evidence" in packet:
                require([m["version_id"] for m in packet["fetched_evidence"]] == ["v1", "v2"], "Research source identities changed")
                require(all(m["content_start"] == 0 and m["content_end"] == len(m["content"])
                            for m in packet["fetched_evidence"]), "Research excerpt offsets changed")
            if path.name.split("-", 1)[-1] in {"decompose.input.json", "select.input.json", "verify.input.json"}:
                require(packet["research_advice"]["trust"] == "untrusted_model_proposals_not_evidence"
                        and len(json.dumps(packet["research_advice"], ensure_ascii=False)) <= 6000,
                        "Bounded advice was not preserved")
            if "material" in packet:
                require(packet["material"]["version_id"] not in {m["version_id"] for m in packet["context"]["materials"]},
                        "Current material was duplicated in decomposition context")
        require(len(harness["calls"]) <= MAX_CALLS and all(c["timeout_seconds"] <= TIMEOUT for r in predictions for c in r["calls"]), "Shared bounds failed")
        # Exercise both guards without touching a CLI, credentials or network.
        shared = runpy.run_path(str(OLD_TRANSPORT))
        cls = transport_class(shared, True)
        guard_output = base / "guard-check"
        guard_output.mkdir()
        direct = cls(case=corpus["cases"][0], condition="direct", destination=guard_output)
        packet = {"target": corpus["cases"][0]["target"], "materials": corpus["cases"][0]["materials"]}
        direct.generate("direct", DIRECT_PROMPT, packet, shared["original"].VERDICT_SCHEMA)
        try:
            direct.generate("direct", DIRECT_PROMPT, packet, shared["original"].VERDICT_SCHEMA)
        except shared["tunnels"].TunnelError:
            pass
        else:
            raise ValueError("Direct call cap failed")
        require(len(direct.calls) == 1 and direct.guard_blocked_calls[-1]["reason"] == "case_call_budget", "Guard emitted an extra call")
        harness_guard = cls(case=corpus["cases"][0], condition="news_tracing", destination=guard_output)
        require(harness_guard.max_calls == MAX_CALLS, "Harness guard differs from the shared case cap")
        harness_guard.deadline = time.monotonic() - 1
        try:
            harness_guard.generate("deconstruct", "Synthetic only", {}, {})
        except shared["tunnels"].TunnelError:
            pass
        else:
            raise ValueError("Case deadline failed")
        require(not harness_guard.calls and harness_guard.guard_blocked_calls[-1]["reason"] == "case_deadline", "Expired case emitted a call")
        for mutate in (lambda c: c.update(gold="forbidden"),
                       lambda c: c["cases"][0]["target"].update(as_of="2025-01-01T00:00:00Z"),
                       lambda c: c["cases"][0]["materials"][0].update(available_at="2025-01-01T00:00:00Z")):
            invalid = deepcopy(corpus)
            mutate(invalid)
            try:
                validate_corpus(invalid)
            except ValueError:
                pass
            else:
                raise ValueError("Gold or temporal mutation accepted")
        for mutate in (lambda p: p.update(development_round=4),
                       lambda p: p.update(case_ids=["h01", "h03"]),
                       lambda p: p.update(conditions=["news_tracing"]),
                       lambda p: p.update(extra_instruction="forbidden"),
                       lambda p: p.update(research_mode="unregistered")):
            invalid = deepcopy(plan)
            mutate(invalid)
            try:
                validate_plan(invalid, stub=True)
            except ValueError:
                pass
            else:
                raise ValueError("Round limit, denominator or plan mutation accepted")
        if retain_output is not None:
            shutil.copytree(output, retain_output)
        print(json.dumps({"self_test": "passed", "remote_calls": 0, "paired_results": 2,
            "declared_research_phases_completed": True, "research_mode": research_mode,
            "formal_adaptive_loop_exercised": True,
            "filesystem_denial_verified": True, "registration_denial_verified": True,
            "deadline_and_call_guards_verified": True, "plan_denominators_verified": True,
            "research_advice_and_version_exposure_verified": True,
            "logged_stub_calls": sum(len(r["calls"]) for r in predictions)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "experiments/historical-cutoff-20260908/inputs/corpus.json")
    parser.add_argument("--review", type=Path, default=HERE / "PREFLIGHT.json")
    parser.add_argument("--registration", type=Path, default=HERE / "REGISTRATION.json")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--protocol", type=Path, default=HERE / "PROTOCOL.md")
    parser.add_argument("--code-manifest", type=Path)
    parser.add_argument("--output", type=Path, default=HERE / "results")
    parser.add_argument("--deny-read-root", action="append", type=Path, default=[])
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--prepare", action="store_true", help="Write a fresh executable hash inventory before registration; no inference")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-output", type=Path, help="Retain synthetic artifacts in a fresh directory, only with --self-test")
    parser.add_argument("--self-test-research-mode", choices=("full", "claim"), default="claim")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--stub", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.stub)
    elif args.self_test:
        self_test(args.self_test_output, args.self_test_research_mode)
    elif args.prepare:
        require(args.plan is not None and args.code_manifest is not None, "--prepare requires --plan and --code-manifest")
        print(json.dumps(prepare(args.plan, args.code_manifest), indent=2))
    elif args.run:
        require(args.plan is not None and args.code_manifest is not None, "--run requires --plan and --code-manifest")
        launch(args.corpus, args.review, args.output, args.deny_read_root, registration_path=args.registration,
               plan_path=args.plan, protocol_path=args.protocol, code_manifest_path=args.code_manifest)
    else:
        _, descriptions = validate_corpus(read(args.corpus))
        require(sha(args.corpus) == FROZEN_CORPUS_SHA256, "Corpus differs from frozen historical inputs")
        plan = validate_plan(read(args.plan)) if args.plan else None
        identifiers = plan["case_ids"] if plan else [entry["id"] for entry in descriptions]
        print(json.dumps({"inference_started": False, "corpus_sha256": sha(args.corpus), "case_ids": identifiers,
                          "conditions": list(CONDITIONS), "max_logical_calls": len(identifiers) * (MAX_CALLS + 1)}, indent=2))


if __name__ == "__main__":
    main()
