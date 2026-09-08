"""Versioned provenance orchestration with mandatory decomposition on every return.

This module does not infer source lineage or news truth. Plug-ins supply semantic
analyses; the runner enforces version, citation, temporal and loop contracts. The
default decomposer deliberately leaves provenance unresolved. All inputs are data.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable, Protocol


@dataclass(frozen=True)
class Target:
    id: str
    text: str
    as_of: str
    source_version_id: str | None = None


@dataclass(frozen=True)
class MaterialVersion:
    version_id: str
    url: str
    content: str
    retrieved_at: str
    published_at: str | None = None
    available_at: str | None = None
    availability_basis: str | None = None
    issuer: str = "unknown"


@dataclass(frozen=True)
class Span:
    version_id: str
    start: int
    end: int
    quote: str


@dataclass(frozen=True)
class Fragment:
    id: str
    text: str
    span: Span
    parent_id: str
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Relation:
    id: str
    from_version: str
    to_version: str | None
    kind: str
    status: str
    basis: tuple[Span, ...]
    rationale: str
    upstream_locator: str | None = None


@dataclass(frozen=True)
class Gap:
    id: str
    question: str
    stage: str = "provenance"


@dataclass(frozen=True)
class Resolution:
    gap_id: str
    basis: tuple[Span, ...]
    rationale: str


@dataclass(frozen=True)
class OriginFinding:
    target_id: str
    version_id: str
    basis: tuple[Span, ...]
    material_kind: str
    rationale: str


@dataclass(frozen=True)
class Analysis:
    fragments: tuple[Fragment, ...] = ()
    relations: tuple[Relation, ...] = ()
    gaps: tuple[Gap, ...] = ()
    resolutions: tuple[Resolution, ...] = ()
    origins: tuple[OriginFinding, ...] = ()
    notes: str = ""
    revisit_versions: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationResult:
    verdict: str = "unresolved"
    basis: tuple[Span, ...] = ()
    rationale: str = ""
    gaps: tuple[Gap, ...] = ()
    resolutions: tuple[Resolution, ...] = ()


@dataclass(frozen=True)
class TraceConfig:
    max_rounds: int = 5
    max_documents: int = 30
    max_decomposition_calls: int = 30


class TraceProvider(Protocol):
    def search(self, target: Target, tasks: tuple[Gap, ...], round_number: int,
               limit: int) -> Iterable[MaterialVersion]: ...


class Decomposer(Protocol):
    def decompose(self, target: Target, material: MaterialVersion,
                  context: dict) -> Analysis: ...


class Verifier(Protocol):
    def verify(self, target: Target, context: dict) -> VerificationResult: ...


class ConservativeDecomposer:
    """Keep the whole text verbatim; no semantic or original-source inference."""

    def decompose(self, target, material, context):
        return Analysis(fragments=(Fragment(
            id=f"{material.version_id}:full", text=material.content,
            span=Span(material.version_id, 0, len(material.content), material.content),
            parent_id=target.id,
        ),), notes="Conservative full-text preservation; semantic decomposition unavailable.")


class ReplayTraceProvider:
    """Offline materials only. Rounds are indexed by provider call number."""

    def __init__(self, rounds: Iterable[Iterable[MaterialVersion]]):
        self.rounds = tuple(tuple(items) for items in rounds)

    def search(self, target, tasks, round_number, limit):
        if round_number <= len(self.rounds):
            yield from self.rounds[round_number - 1][:limit]


def _time(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from exc


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _tuple_of(items, cls, name):
    if not isinstance(items, tuple) or any(not isinstance(item, cls) for item in items):
        raise ValueError(f"{name} must be a tuple of {cls.__name__}")


def _fingerprint(material):
    # Retrieval is an observation, not part of the immutable publisher version.
    payload = asdict(material)
    payload.pop("retrieved_at")
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _material_eligibility(material, cutoff):
    if not isinstance(material, MaterialVersion):
        raise ValueError("provider must yield MaterialVersion objects")
    for name in ("version_id", "url", "content", "issuer"):
        _nonempty(getattr(material, name), name)
    retrieved = _time(material.retrieved_at, "retrieved_at")
    published = _time(material.published_at, "published_at") if material.published_at is not None else None
    available = _time(material.available_at, "available_at") if material.available_at is not None else None
    if material.availability_basis is not None:
        _nonempty(material.availability_basis, "availability_basis")
    reasons = []
    if published is not None and published > retrieved:
        reasons.append("published_after_retrieval")
    if published is not None and published > cutoff:
        reasons.append("published_after_as_of")
    if available is None:
        reasons.append("version_availability_unknown")
    elif not material.availability_basis:
        reasons.append("version_availability_unsubstantiated")
    elif available > cutoff:
        reasons.append("version_available_after_as_of")
    if available is not None and available > retrieved:
        reasons.append("available_after_retrieval")
    return reasons


def _span(span, materials):
    if not isinstance(span, Span) or span.version_id not in materials:
        raise ValueError("span must reference a stored eligible material version")
    if type(span.start) is not int or type(span.end) is not int:
        raise ValueError("span offsets must be integers")
    content = materials[span.version_id].content
    if not (0 <= span.start < span.end <= len(content)) or content[span.start:span.end] != span.quote:
        raise ValueError("span quote must exactly match the original character offsets")


def _basis(items, materials):
    _tuple_of(items, Span, "basis")
    if not items:
        raise ValueError("an evidence basis is required")
    for item in items:
        _span(item, materials)


def _gap(gap):
    if not isinstance(gap, Gap):
        raise ValueError("invalid gap type")
    _nonempty(gap.id, "gap.id")
    _nonempty(gap.question, "gap.question")
    if gap.stage not in {"provenance", "verification"}:
        raise ValueError("gap.stage must be provenance or verification")


def _resolution(resolution, materials):
    _nonempty(resolution.gap_id, "resolution.gap_id")
    _nonempty(resolution.rationale, "resolution.rationale")
    _basis(resolution.basis, materials)


def _validate_analysis(analysis, target, material, materials):
    if not isinstance(analysis, Analysis):
        raise ValueError("decomposer must return Analysis")
    for name, cls in (("fragments", Fragment), ("relations", Relation), ("gaps", Gap),
                      ("resolutions", Resolution), ("origins", OriginFinding)):
        _tuple_of(getattr(analysis, name), cls, name)
    if not isinstance(analysis.notes, str):
        raise ValueError("analysis.notes must be a string")
    _tuple_of(analysis.revisit_versions, str, "revisit_versions")
    if any(version not in materials for version in analysis.revisit_versions):
        raise ValueError("revisit_versions must refer to available material versions")
    for fragment in analysis.fragments:
        for name in ("id", "text", "parent_id"):
            _nonempty(getattr(fragment, name), f"fragment.{name}")
        _span(fragment.span, materials)
        _tuple_of(fragment.qualifiers, str, "qualifiers")
    for edge in analysis.relations:
        _nonempty(edge.id, "relation.id")
        _nonempty(edge.rationale, "relation.rationale")
        if edge.from_version not in materials:
            raise ValueError("relation source version is unavailable")
        if edge.to_version is not None and edge.to_version not in materials:
            raise ValueError("unavailable upstream needs upstream_locator and to_version=None")
        if edge.to_version is None:
            _nonempty(edge.upstream_locator, "upstream_locator")
        if edge.kind not in {"quotes", "cites", "reprints", "translates", "derives", "supports", "contradicts"}:
            raise ValueError("invalid relation kind")
        if edge.status not in {"direct", "declared", "inferred", "unresolved", "excluded"}:
            raise ValueError("invalid relation status")
        _basis(edge.basis, materials)
        if not any(item.version_id == edge.from_version for item in edge.basis):
            raise ValueError("relation basis must include a source-side span")
        if edge.status == "direct" and edge.to_version is None:
            raise ValueError("direct relation requires an available upstream version")
    for gap in analysis.gaps:
        _gap(gap)
    for resolution in analysis.resolutions:
        _resolution(resolution, materials)
    for origin in analysis.origins:
        if origin.target_id != target.id or origin.version_id not in materials:
            raise ValueError("origin must identify the target and an eligible version")
        if origin.material_kind not in {"original_record", "original_interview", "original_dataset", "original_observation"}:
            raise ValueError("origin requires an explicit original-material kind")
        _nonempty(origin.rationale, "origin.rationale")
        _basis(origin.basis, materials)
        if not any(item.version_id == origin.version_id for item in origin.basis):
            raise ValueError("origin basis must locate evidence in the claimed original")


def run_provenance(target: Target | dict, provider: TraceProvider,
                   decomposer: Decomposer | None = None, verifier: Verifier | None = None,
                   config: TraceConfig | dict | None = None) -> dict:
    """Run a bounded trace. Provider/analysis errors are audited and fail unresolved.

    Historical eligibility needs an explicit, evidenced ``available_at`` for the
    exact version. ``published_at`` alone never proves historical availability.
    A late retrieval of an evidenced old version is allowed; there is no age cap.
    All returned valid versions, including duplicates/ineligible ones, visit psi.
    """
    target = Target(**target) if isinstance(target, dict) else target
    config = TraceConfig(**config) if isinstance(config, dict) else (config or TraceConfig())
    if not isinstance(target, Target) or not isinstance(config, TraceConfig):
        raise ValueError("invalid target or config type")
    _nonempty(target.id, "target.id")
    _nonempty(target.text, "target.text")
    if target.source_version_id is not None:
        _nonempty(target.source_version_id, "target.source_version_id")
    cutoff = _time(target.as_of, "target.as_of")
    for name in ("max_rounds", "max_documents", "max_decomposition_calls"):
        if type(getattr(config, name)) is not int or getattr(config, name) < 1:
            raise ValueError(f"{name} must be a positive integer")
    decomposer = decomposer or ConservativeDecomposer()
    materials = {}
    eligible = {}
    fingerprints = {}
    current_analyses = {}
    history = []
    verifications = []
    operations = []
    observations = []
    errors = []
    initial = Gap("origin:" + target.id, "Find the producing record and evidenced lineage for: " + target.text)
    gaps = {initial.id: initial}
    provenance_gap_ids = {initial.id}
    resolved = {}
    verification_gaps = {}
    verification_resolved = {}
    verification_gap_revisions = {}
    analysis_resolution_revisions = {}
    runtime_gaps = {}
    fragments = {}
    relations = {}
    origins = {}
    usage = {"rounds": 0, "documents": 0, "unique_versions": 0, "decomposition_calls": 0, "verification_calls": 0}
    fact_status = "not_checked" if verifier is None else "unresolved"
    stop_reason = "round_budget"
    fatal = False

    def event(action, **values):
        operations.append({"sequence": len(operations) + 1, "round": usage["rounds"], "action": action, **values})

    def context():
        return deepcopy({
            "target": asdict(target), "materials": [asdict(item) for item in eligible.values()],
            "analyses": {key: asdict(item) for key, item in current_analyses.items()},
            "fragments": [asdict(item) for item in fragments.values()],
            "relations": [asdict(item) for item in relations.values()],
            "origins": [asdict(item) for item in origins.values()],
            "gaps": [asdict(item) for item in gaps.values()],
            "verification_history": deepcopy(verifications), "usage": dict(usage),
        })

    def rebuild():
        # Rebuild from current revisions so removed findings cannot linger.
        fragments.clear()
        relations.clear()
        origins.clear()
        proposed_gaps = {initial.id: initial, **runtime_gaps}
        proposed_resolved = {}
        for version_id, analysis in current_analyses.items():
            for item in analysis.fragments:
                fragments[item.id] = item
            for item in analysis.relations:
                relations[item.id] = item
            for item in analysis.origins:
                origins[(item.target_id, item.version_id)] = item
            for item in analysis.gaps:
                proposed_gaps[item.id] = item
            for item in analysis.resolutions:
                # A verifier's newer request supersedes earlier evidence. A
                # rebuild or unchanged revisit must not silently close it again.
                if analysis_resolution_revisions[version_id][item.gap_id] >= verification_gap_revisions.get(item.gap_id, 0):
                    proposed_resolved[item.gap_id] = item
        # Gap identity keeps its stage even if a later analysis removes or
        # resolves the request. Verifiers cannot relabel provenance as fact work.
        provenance_gap_ids.update(item.id for item in proposed_gaps.values() if item.stage == "provenance")
        # Preserve verification tasks until explicitly resolved by either stage.
        proposed_gaps.update(verification_gaps)
        proposed_resolved.update(verification_resolved)
        if origins and not has_origin_path():
            proposed_gaps["lineage:" + target.id] = Gap("lineage:" + target.id,
                "Provide the target source version and an evidenced citation/derivation path to an original material")
            provenance_gap_ids.add("lineage:" + target.id)
        gaps.clear()
        gaps.update({key: value for key, value in proposed_gaps.items() if key not in proposed_resolved})
        resolved.clear()
        resolved.update(proposed_resolved)

    def has_origin_path():
        if target.source_version_id is None or target.source_version_id not in eligible:
            return False
        roots = {item.version_id for item in origins.values()}
        adjacency = {}
        for edge in relations.values():
            if edge.status == "direct" and edge.kind in {"quotes", "cites", "reprints", "translates", "derives"}:
                adjacency.setdefault(edge.from_version, set()).add(edge.to_version)
        pending = [target.source_version_id]
        visited = set()
        while pending:
            version = pending.pop()
            if version in roots:
                return True
            if version not in visited:
                visited.add(version)
                pending.extend(adjacency.get(version, ()))
        return False

    def structural_fingerprint():
        def records(values, excluded=()):
            items = [{key: value for key, value in asdict(item).items() if key not in excluded}
                     for item in values]
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        state = {"fragments": records(fragments.values()),
                 "relations": records(relations.values(), ("rationale",)),
                 "origins": records(origins.values(), ("rationale",)),
                 "gaps": records(gaps.values())}
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def fail(stage, exc):
        nonlocal fatal, fact_status, stop_reason
        fatal = True
        fact_status = "unresolved" if verifier is not None else "not_checked"
        stop_reason = "integrity_error" if stage == "integrity" else f"{stage}_error"
        errors.append({"stage": stage, "type": type(exc).__name__, "message": str(exc)})
        event("error", stage=stage, message=str(exc))

    def analyze(material, reasons, duplicate, revisit=False):
        usage["decomposition_calls"] += 1
        event("decompose_started", version_id=material.version_id, duplicate=duplicate, revisit=revisit)
        psi_context = context()
        psi_context["current_material_eligible"] = not reasons
        psi_context["current_material_exclusion_reasons"] = reasons
        analysis = decomposer.decompose(target, material, psi_context)
        validation_materials = dict(eligible)
        validation_materials[material.version_id] = material
        _validate_analysis(analysis, target, material, validation_materials)
        revision = {"revision": len(history) + 1, "round": usage["rounds"],
                    "version_id": material.version_id, "duplicate": duplicate, "revisit": revisit,
                    "accepted": not reasons, "analysis": asdict(analysis), "exclusion_reasons": reasons}
        history.append(revision)
        event("decompose_completed", version_id=material.version_id, revision=revision["revision"])
        if reasons:
            event("excluded_from_graph", version_id=material.version_id, reasons=reasons)
            return ()
        eligible[material.version_id] = material
        previous = current_analyses.pop(material.version_id, None)
        previous_resolutions = {item.gap_id: item for item in previous.resolutions} if previous else {}
        previous_revisions = analysis_resolution_revisions.get(material.version_id, {})
        accepted_revision = len(history) + len(verifications)
        # Preserve the age of unchanged evidence, including cosmetic rationale
        # edits. New or changed evidence can explicitly answer a reopened gap.
        analysis_resolution_revisions[material.version_id] = {
            item.gap_id: previous_revisions[item.gap_id]
            if item.gap_id in previous_resolutions
            and set(item.basis) == set(previous_resolutions[item.gap_id].basis)
            else accepted_revision
            for item in analysis.resolutions
        }
        current_analyses[material.version_id] = analysis
        event("alignment_checked", version_id=material.version_id, analysis_changed=previous != analysis)
        rebuild()
        event("graph_updated", version_id=material.version_id, open_gaps=len(gaps))
        return analysis.revisit_versions

    seen_structures = {structural_fingerprint()}
    previous_structure = structural_fingerprint()
    for round_number in range(1, config.max_rounds + 1):
        capacity = min(config.max_documents - usage["documents"], config.max_decomposition_calls - usage["decomposition_calls"])
        if capacity <= 0:
            stop_reason = "document_budget" if usage["documents"] >= config.max_documents else "decomposition_budget"
            break
        usage["rounds"] = round_number
        tasks = tuple(gaps.values()) or (Gap("inspect-lineage", "Inspect unresolved upstream lineage"),)
        event("search", tasks=[asdict(item) for item in tasks], limit=capacity)
        try:
            iterator = iter(provider.search(target, tasks, round_number, capacity))
        except Exception as exc:
            fail("provider", exc)
            break
        new_eligible = 0
        received = 0
        for _ in range(capacity):
            if usage["decomposition_calls"] >= config.max_decomposition_calls:
                break
            try:
                material = next(iterator)
            except StopIteration:
                break
            except Exception as exc:
                fail("provider", exc)
                break
            received += 1
            usage["documents"] += 1
            try:
                reasons = _material_eligibility(material, cutoff)
                fingerprint = _fingerprint(material)
            except Exception as exc:
                fail("material", exc)
                break
            duplicate = material.version_id in materials
            if duplicate and fingerprints[material.version_id] != fingerprint:
                observations.append({"material": asdict(material), "accepted": False, "reasons": ["version_id_collision"]})
                fail("integrity", ValueError("version_id_collision: revisions require a new version_id"))
                break
            if not duplicate:
                materials[material.version_id] = material
                fingerprints[material.version_id] = fingerprint
                usage["unique_versions"] += 1
            observations.append({"version_id": material.version_id, "retrieved_at": material.retrieved_at,
                                 "duplicate": duplicate, "eligible": not reasons, "reasons": reasons})
            event("snapshot_saved" if not duplicate else "duplicate_observed", version_id=material.version_id,
                  sha256=fingerprint, eligible=not reasons)
            was_eligible = material.version_id in eligible
            try:
                # Nothing may enter the graph or verifier before this call.
                pending = list(analyze(material, reasons, duplicate))
                visited = {material.version_id}
                while pending:
                    version_id = pending.pop(0)
                    if version_id in visited:
                        event("revisit_cycle_detected", version_id=version_id)
                        runtime_gaps["revisit:" + version_id] = Gap("revisit:" + version_id, "Resolve repeated reanalysis dependency for " + version_id)
                        rebuild()
                        continue
                    if usage["decomposition_calls"] >= config.max_decomposition_calls:
                        runtime_gaps["revisit:" + version_id] = Gap("revisit:" + version_id, "Reanalysis pending after decomposition budget: " + version_id)
                        rebuild()
                        break
                    visited.add(version_id)
                    event("revisit_requested", version_id=version_id)
                    pending.extend(analyze(eligible[version_id], [], True, revisit=True))
            except Exception as exc:
                fail("decomposer", exc)
                break
            if reasons:
                continue
            if not was_eligible:
                new_eligible += 1
        if fatal:
            break
        if verifier is not None and eligible:
            usage["verification_calls"] += 1
            event("verification_started")
            try:
                check = verifier.verify(target, context())
                if not isinstance(check, VerificationResult):
                    raise ValueError("verifier must return VerificationResult")
                if check.verdict not in {"supported", "contradicted", "conflicting", "unresolved"}:
                    raise ValueError("invalid verification verdict")
                if not isinstance(check.rationale, str):
                    raise ValueError("verification rationale must be a string")
                _tuple_of(check.basis, Span, "verification basis")
                if check.verdict != "unresolved":
                    _basis(check.basis, eligible)
                    _nonempty(check.rationale, "verification rationale")
                else:
                    for item in check.basis:
                        _span(item, eligible)
                _tuple_of(check.gaps, Gap, "verification gaps")
                _tuple_of(check.resolutions, Resolution, "verification resolutions")
                for item in check.gaps:
                    _gap(item)
                    if item.stage != "verification":
                        raise ValueError("verifier search gaps must use stage=verification")
                    if item.id in provenance_gap_ids:
                        raise ValueError("verifier may not replace provenance gaps")
                for item in check.resolutions:
                    _resolution(item, eligible)
                    if item.gap_id in provenance_gap_ids:
                        raise ValueError("verifier may not resolve provenance gaps")
            except Exception as exc:
                fail("verifier", exc)
                break
            verifications.append({"round": round_number, **asdict(check)})
            for item in check.gaps:
                verification_gaps[item.id] = item
                verification_gap_revisions[item.id] = len(history) + len(verifications)
                verification_resolved.pop(item.id, None)
            for item in check.resolutions:
                verification_gaps.pop(item.gap_id, None)
                verification_resolved[item.gap_id] = item
            rebuild()
            fact_status = "unresolved" if any(item.stage == "verification" for item in gaps.values()) else check.verdict
            event("verification_completed", verdict=fact_status, followup_tasks=len(check.gaps))
        provenance_complete = has_origin_path() and not any(item.stage == "provenance" for item in gaps.values())
        if provenance_complete and (verifier is None or fact_status != "unresolved") and not gaps:
            stop_reason = "complete"
            break
        if received == 0:
            stop_reason = "empty_results"
            break
        structure = structural_fingerprint()
        structural_progress = structure not in seen_structures
        event("progress_checked", new_eligible_versions=new_eligible, new_structure=structural_progress)
        if new_eligible == 0 and not structural_progress:
            stop_reason = "no_new_eligible_materials" if structure == previous_structure else "repeated_state"
            break
        seen_structures.add(structure)
        previous_structure = structure
        if usage["documents"] >= config.max_documents:
            stop_reason = "document_budget"
            break
        if usage["decomposition_calls"] >= config.max_decomposition_calls:
            stop_reason = "decomposition_budget"
            break
    provenance_status = "original_material_located" if has_origin_path() and not any(item.stage == "provenance" for item in gaps.values()) else ("partial" if eligible else "unresolved")
    if fatal:
        provenance_status = "unresolved"
    event("stopped", reason=stop_reason)
    return {
        "schema_version": "0.2", "scope": "plugin-supplied semantic analyses; no built-in truth oracle",
        "target": asdict(target), "config": asdict(config), "provenance_status": provenance_status,
        "fact_status": fact_status, "stop_reason": stop_reason, "usage": usage,
        "materials": [asdict(item) for item in materials.values()],
        "eligible_version_ids": list(eligible), "observations": observations,
        "analyses": {key: asdict(item) for key, item in current_analyses.items()}, "analysis_history": history,
        "fragments": [asdict(item) for item in fragments.values()],
        "relations": [asdict(item) for item in relations.values()],
        "origins": [asdict(item) for item in origins.values()],
        "gaps": [asdict(item) for item in gaps.values()],
        "resolutions": [asdict(item) for item in resolved.values()],
        "verification_history": verifications, "operations": operations, "errors": errors,
    }
