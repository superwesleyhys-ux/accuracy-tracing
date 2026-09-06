# FactCircuit v0.3 adapter contract

`factcircuit.provenance.run_provenance` orchestrates immutable snapshots, exact source spans, bounded retrieval, decomposition, source lineage and layered verification. It has no built-in truth oracle or network dependency. Plug-ins supply semantic findings; the runner validates structure, ordering, scope and evidence references.

The legacy policy API remains separate. The earlier `newsverify` import path is retained as a compatibility alias. Historical v0.2/v0.3 reports keep their original names and contents; this document describes the current contract.

## Public entry point

```python
from factcircuit.provenance import (
    MaterialVersion, RetrievalHit, Target, TraceConfig, run_provenance,
)

report = run_provenance(
    target=Target(
        id="claim-1",
        text="The bridge reopened before Friday.",
        as_of="2026-09-04T20:00:00Z",
        source_version_id="article:v1",
        assessment_mode="evidence",
        evidence_scope=("notice:v1",),
    ),
    provider=provider,
    decomposer=decomposer,
    verifier=verifier,
    config=TraceConfig(
        max_rounds=5,
        max_documents=30,
        max_decomposition_calls=30,
    ),
)
```

`target` and `config` may also be dictionaries with the exact dataclass fields. A JSON-array `evidence_scope` is normalized to a tuple. Adapters return the frozen dataclasses documented below, not unvalidated model JSON.

`assessment_mode` is `evidence` or `world`. Evidence mode asks what the frozen evidence-scope versions entail; world mode asks whether the actual event is established. Originality, document entailment and real-world truth are separate questions.

## Immutable material versions

`MaterialVersion` contains:

| Field | Contract |
| --- | --- |
| `version_id` | Nonempty immutable-version identity, independent of URL |
| `url` | Locator only; it establishes no provenance by itself |
| `content` | Exact preserved extracted text |
| `retrieved_at` | Time this observation was retrieved, with timezone |
| `published_at` | Publisher-reported publication time or `None` |
| `available_at` | Evidenced time this exact version existed or `None` |
| `availability_basis` | Evidence reference for exact-version availability or `None` |
| `issuer` | Publisher/issuer label; defaults to `unknown` |

The immutable fingerprint excludes only `retrieved_at`, because a later retrieval of the same unchanged publisher version is a new observation. Reusing a `version_id` with changed content or publisher/availability metadata is an integrity error. Corrections need new version IDs even when the URL is unchanged.

For a historical cutoff, `published_at` alone is insufficient. A version without supported `available_at`, or one available after `Target.as_of`, is saved and audited but excluded from the current graph and verifier. Late retrieval of a demonstrably old version is allowed; no arbitrary age cutoff applies. The runner checks that `availability_basis` is present, but cannot authenticate it.

## Provider and exact task attribution

The legacy provider interface remains valid:

```python
class Provider:
    def search(self, target, tasks, round_number, limit):
        yield material  # MaterialVersion, at most limit values
```

A task-aware provider should implement the preferred interface:

```python
class Provider:
    def search_hits(self, target, tasks, round_number, limit):
        yield RetrievalHit(material, (tasks[0].id,))
```

The runner prefers `search_hits` when present. A `RetrievalHit.task_ids` tuple freezes which current-round tasks selected that exact return. IDs must be nonempty, unique and members of the round's issued task set. Lazy providers must use the envelope; the legacy `last_attribution` sidecar is copied before iteration and cannot be mutated after yielding.

The staged decomposer advertises `requires_task_attribution=True`. For it, every external return from round 2 onward must have task attribution; first-round seeds and internal `revisit_versions` calls are exempt. Bare `MaterialVersion` returns remain compatible with non-strict adapters.

After a round, a task-aware provider sets `last_feedback` to one exact record per issued task:

```python
{
    "gap_id": "verification:record",
    "action": "fetch",                 # fetch | search | reanalyse
    "locator": "https://example.org/record",
    "status": "returned",             # returned | unavailable | budget_exhausted
    "reason": "matching snapshot returned",
    "version_ids": ["record:v1"],
}
```

All six fields are required. IDs are unique and must preserve the issued action and locator. In strict staged rounds, feedback must cover the full issued set. `returned` must list exactly the versions attributed to that gap; the other statuses require an empty list and cannot hide an attributed return. Invalid or contradictory feedback produces `provider_error`.

`SnapshotSearchProvider` is an offline reference implementation. It schedules the most constrained exact fetch/reanalyse tasks first, lets one version cover every matching exact obligation, then gives each broad search one candidate before filling remaining capacity. Duplicate snapshot and seed IDs are rejected. It records actual consumed—not merely planned—hits and distinguishes `unavailable` from a task deferred by round capacity. It does not browse the live web.

## Mandatory decomposition

```python
class Decomposer:
    def decompose(self, target, material, context):
        return Analysis(
            fragments=(...),
            relations=(...),
            gaps=(...),
            resolutions=(...),
            origins=(...),
            notes="Observable result, not private reasoning",
            revisit_versions=(...),
        )
```

Every consumed type-valid return is saved before decomposition. Eligible material is passed to the configured decomposer. Historically ineligible material uses an isolated `ConservativeDecomposer`; it is retained in observation/history output but never shown to a stateful semantic adapter, current graph or verifier. This prevents direct run-time leakage, not knowledge already present in model weights.

The detached `context` contains the frozen target, eligible materials, current analyses, canonical graph findings, active `gaps`, historical `gap_registry`, verification history, usage, `current_round_returns`, canonical `retrieval_feedback`, and current assessments. The current decomposition call additionally receives:

- `current_return`: exact version/task receipt for this return;
- `current_material_eligible`;
- `current_material_exclusion_reasons`.

An accepted `Analysis` is a complete replacement for that material owner, not a delta. The runner validates the entire candidate projection before committing eligible state. A failure leaves no partial eligible material, analysis or graph mutation.

### Analysis records

| Type | Key fields and rules |
| --- | --- |
| `Span` | `version_id`, `start`, `end`, `quote`; end-exclusive exact Unicode substring |
| `Fragment` | `id`, `text`, `span`, `parent_id`, `qualifiers`, `qualifier_spans`; parent chain must reach the target and be acyclic |
| `Relation` | `id`, downstream `from_version`, optional upstream `to_version`, `kind`, `status`, `basis`, `rationale`, optional `upstream_locator` |
| `Gap` | `id`, `question`, `stage`, `dimension`, `blocking`, `target_id`, `basis`, `decision_impact`, `action`, `locator`, optional persistent `probe_id` |
| `Resolution` | registered `gap_id`, nonempty exact `basis`, nonempty `rationale` |
| `OriginFinding` | target/version, exact basis, explicit original-material kind and rationale |

Relation kinds are `quotes`, `cites`, `reprints`, `translates`, `derives`, `supports`, and `contradicts`. Statuses are `direct`, `declared`, `inferred`, `unresolved`, and `excluded`. A direct propagation edge needs an available upstream version and source-side basis. `supports`/`contradicts` are semantic relations and never substitute for a propagation path.

`original_material_located` requires an eligible `OriginFinding`, an eligible `target.source_version_id`, a direct propagation path from that version to the claimed original, and no blocking provenance gap. This is completion of the plug-in's evidenced trace, not proof that no inaccessible earlier source exists.

### Gap lifecycle and revisions

Gap IDs are operational identities. Stage, effective dimension, target, action, locator and probe cannot change under one ID. Blocking severity is monotonic for the entire registered lifetime of an ID, including after resolution; a genuinely weaker later task needs a new ID. Different live owners of one ID must emit exactly the same gap definition. The staged verifier persists `probe_id`, so unavailable feedback and resolutions cannot leak from one target probe to another.

Gap and resolution events from current material revisions are ordered by committed analysis revision: the latest explicit open/close event wins. Independent closures after the latest reopen merge their exact basis and rationales. Verifier tasks are preserved until explicitly resolved; a newer decomposition may close or reopen them transactionally. Historical IDs remain in `gap_registry` so a later valid closure can be checked even when the gap is not currently open.

`revisit_versions` requests complete reanalysis of affected eligible versions under the same decomposition budget. A new upstream matching an old declared locator also schedules the downstream material automatically. Self/cycle requests are audited and deduplicated. Only unfinished reanalysis caused by the decomposition cap creates a runtime revisit gap.

## Optional verifier and validation loop

```python
class Verifier:
    def verify(self, target, context):
        return VerificationResult(
            verdict="unresolved",       # legacy evidence verdict
            basis=(),
            rationale="Need the named record",
            gaps=(...),
            resolutions=(),
            evidence_verdict="unresolved",
            world_verdict="unresolved",
            world_basis=(),
            world_rationale="No independent authentication yet",
        )
```

Conclusive verdicts require exact basis and nonempty rationale. Evidence conclusions may cite only the complete frozen evidence scope; world conclusions require their own basis. Only blocking gaps gate the matching assessment dimension. `fact_status` is the gated world decision, while `decision_status` follows `Target.assessment_mode`.

A generic verifier may resolve only registered verification gaps. The supplied staged verifier additionally requires an exact current-round task receipt and basis from a version attributed to that task. It derives a fixed target-only `TargetPlan`, requires every probe and required dimension exactly once in both layers, applies conservative source-grounding checks, and uses isolated evidence/world critics. See [STAGED_VALIDATION_LOOP.md](STAGED_VALIDATION_LOOP.md).

Verifier-created tasks never inject material directly. Returns are saved, eligibility-checked and decomposed before a later verifier call. A new task emitted after an empty result round is queued for the next round. A `budget_exhausted` task is retried while outer capacity remains; a complete `unavailable` receipt can terminate that fixed provider scope.

The outer verifier is skipped only when its complete canonical input is unchanged. That input includes material fingerprints, full verifier-visible analyses and graph objects (including fragment text/qualifiers and relation rationales), active gaps, current attributed receipts and, for verifiers declaring `uses_retrieval_feedback=True`, canonical task feedback. Structural loop progress separately ignores cosmetic prose, so a meaningful verifier recheck does not grant unbounded extra rounds.

## Budgets, termination and errors

`TraceConfig` independently caps provider rounds, consumed documents and decomposition calls (including revisits). The runner consumes iterables lazily and closes them when its budget ends, so providers can commit only actually consumed hits.

Normal stop reasons include `complete`, `provider_exhausted`, `empty_results`, `retrieval_budget`, `no_new_eligible_materials`, `repeated_state`, `round_budget`, `document_budget`, and `decomposition_budget`. Provider, material, decomposer, verifier and integrity failures use the matching `*_error` reason.

The optional model transport has separate call, total-output-token, per-call-output-token and wall-time caps. Staged transactions preflight their worst-case repair path before the first call, and each serialized stage input is capped at 250,000 characters. Input tokens are measured but not token-capped. SDK retries are disabled.

Any failure sets `assessment_valid=false` and current completion statuses fail closed. Previously accepted analyses, graph findings and raw verification history remain visible for diagnosis; they are not presented as a valid final success.

## Report and independent evaluation

The JSON report includes:

- frozen target/config and `schema_version="0.3"`;
- raw stored materials, eligible version IDs and retrieval observations;
- raw `retrieval_feedback` history;
- current analyses and append-only `analysis_history` with each `retrieval_receipt`;
- fragments, relations, origins, active gaps and combined resolutions;
- `verification_history`, `assessments`, `decision_status`, `fact_status`, `assessment_valid`;
- ordered operations, usage, provenance status, stop reason and errors.

For independent evaluation, freeze targets, cutoffs, raw versions, evidence scopes, gold origins, gold lineage and verdict labels before inference. Preserve every failed attempt. The bundled demos and regression fixtures are synthetic/hand-authored contract tests; they do not establish real-news accuracy or prove that splitting prompts improves it.
