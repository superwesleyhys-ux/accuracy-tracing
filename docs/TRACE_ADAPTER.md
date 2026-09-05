# Accuracy Tracing: provenance and verification adapter contract

This is the v0.2 orchestration contract. The existing `newsverify.core` API remains
separate. The import package remains `newsverify` for compatibility.

## What runs today

`newsverify.provenance.run_provenance` enforces immutable versions, exact citation
spans, historical availability, mandatory decomposition of each returned material,
analysis revision history, distinct relation types, bounded retrieval and a
verification-to-provenance feedback path. It has no network or model dependency.

The default `ConservativeDecomposer` preserves a complete original-text fragment
and leaves the source question open. It does not perform semantic extraction.
`trace_demo` uses manually supplied synthetic annotations and deterministic replay
verdicts. Neither passing its tests nor its final verdict measures real-news accuracy.

## Public entry points

```python
from newsverify.provenance import (
    Target, MaterialVersion, ReplayTraceProvider, TraceConfig, run_provenance,
)

target = Target(
    id="claim-1",
    text="A fixed original claim, including its qualifiers.",
    as_of="2026-09-04T20:00:00Z",
    source_version_id="article:v1",
)
version = MaterialVersion(
    version_id="article:v1",
    url="https://example.org/article",
    content="A fixed original claim, including its qualifiers.",
    retrieved_at="2026-09-05T01:00:00Z",
    published_at="2026-09-04T12:00:00Z",
    available_at="2026-09-04T12:01:00Z",
    availability_basis="Exact-version archive record identifier or stored capture reference",
)
report = run_provenance(
    target, ReplayTraceProvider(((version,),)),
    config=TraceConfig(max_rounds=5, max_documents=30, max_decomposition_calls=30),
)
# This conservative run is partial, not a claim that the original was found.
```

`target` and `config` can also be dictionaries with the exact dataclass field
names. The adapters must return the documented dataclass objects, not unvalidated
JSON. Adapters are responsible for converting and validating model outputs.

`newsverify.trace_demo.build_demo()` returns keyword arguments accepted by
`run_provenance`. `newsverify.trace_demo.run_demo()` returns a JSON-serializable
report with `evaluation_mode="synthetic_annotated_replay"`.

## Provider

```python
class Provider:
    def search(self, target, tasks, round_number, limit):
        # target: frozen Target
        # tasks: tuple[Gap, ...], including verification questions when needed
        # Yield at most limit MaterialVersion objects.
        yield version
```

The runner consumes the iterable one item at a time, never beyond its remaining
document/decomposition budget. Adapters must independently bound network requests,
timeouts, model tokens and other costs; the runner cannot preempt a blocking
adapter call or prevent a provider from eagerly doing work before yielding.

`MaterialVersion` fields:

| Field | Contract |
| --- | --- |
| `version_id` | Nonempty immutable-version identity, independent of URL |
| `url` | Locator string; a locator alone establishes no provenance |
| `content` | Exact preserved extracted text |
| `retrieved_at` | Time this observation was retrieved, with timezone |
| `published_at` | Publisher's reported publication time, or explicitly `None` |
| `available_at` | Evidenced time this exact version existed, or `None` |
| `availability_basis` | Reference to evidence of exact-version availability, or `None` |
| `issuer` | Publisher/issuer label; defaults to `unknown` |

The same URL may have many version IDs. Reusing an ID with changed content,
publisher metadata or availability evidence produces `integrity_error` and an
unresolved result. A different `retrieved_at` for an otherwise identical version
is a new observation, not a new publisher version. Preserve its observation time.

For a historical cutoff, an early `published_at` alone is insufficient. Versions
without a supported `available_at`, or with availability/publication after the
cutoff, are audited but excluded from the graph and verifier. All timestamps must
include a timezone. Late retrieval of a demonstrably old version is valid; no
72-hour freshness filter is applied. A missing publication timestamp is preserved
explicitly and does not replace the availability requirement.

The runner checks the presence of `availability_basis`; it cannot independently
authenticate an archive reference. A production adapter and the independent gold
review must inspect that evidence. Do not fill this field with an invented claim.

## Mandatory psi decomposition

```python
class Decomposer:
    def decompose(self, target, material, context):
        return Analysis(
            fragments=(...), relations=(...), gaps=(...),
            resolutions=(...), origins=(...),
            notes="Observable analysis result, not private reasoning",
            revisit_versions=(...),
        )
```

Every type-valid material return is saved in the run's in-memory snapshot store
before this call, including duplicates and historically excluded versions. The
runner validates the analysis, aligns cited character spans, and only then updates
the current graph. Invalid schemas/dates and conflicting immutable IDs fail before
semantic processing and leave an explicit error.

The `context` is a detached JSON-like snapshot of the target, eligible materials,
current analyses, fragments, relations, origins, gaps, verification history and
usage. It excludes historically rejected content. For the current call it also
contains `current_material_eligible` and `current_material_exclusion_reasons`.
Analysis of an ineligible current material is retained in audit history but never
merged into current state or sent to the verifier.

This graph exclusion does not isolate a stateful semantic plugin from the rejected
text it saw during psi, and it cannot remove future knowledge from model
pretraining. Strict historical experiments require isolated semantic adapters
that admit only eligible materials to stateful model execution. Isolation of the
psi path for ineligible returns is pending; this release does not claim complete
historical leakage prevention.

### Analysis objects

All collection fields must be tuples; dataclasses are frozen.

| Type | Fields and semantics |
| --- | --- |
| `Span` | `version_id`, `start`, `end`, `quote`; Unicode character offsets, end exclusive, exact original substring required |
| `Fragment` | `id`, `text`, `span`, `parent_id`, `qualifiers=()`; text can be a semantic restatement but the original span remains intact |
| `Relation` | `id`, `from_version`, `to_version`, `kind`, `status`, `basis`, `rationale`, `upstream_locator=None` |
| `Gap` | `id`, `question`, `stage="provenance"`; stage is provenance or verification |
| `Resolution` | `gap_id`, nonempty tuple `basis`, `rationale` |
| `OriginFinding` | `target_id`, `version_id`, nonempty tuple `basis`, `material_kind`, `rationale` |

Relations point from the downstream material to the candidate upstream material.
`kind` is one of `quotes`, `cites`, `reprints`, `translates`, `derives`, `supports`,
`contradicts`. `status` is one of `direct`, `declared`, `inferred`, `unresolved`,
`excluded`. Every relation needs an exact source-side evidence span. An unavailable
upstream uses `to_version=None` and a nonempty `upstream_locator`; it cannot be
marked `direct`.

`supports` and `contradicts` are semantic relationships and are never traversed as
propagation lineage, even if a plugin labels them `direct`. An explicit publisher
source statement can be recorded as `declared` while the underlying record remains
unavailable. Content similarity and early publication do not imply a direct edge.
Plugins must ground each semantic choice; structural validation cannot prove that
an annotation is substantively correct.

An `OriginFinding` must identify an eligible original record, original interview,
original dataset or original observation, with evidence in that version. Being
the earliest accessible article or having no outgoing links is not a root rule.

`original_material_located` requires all of:

1. An explicit eligible `OriginFinding` and an evidenced resolution of the initial
   `origin:<target.id>` question.
2. A supplied, eligible `target.source_version_id` with a path of `direct`
   citation/quotation/reprint/translation/derivation edges to the original. The
   original target version may itself be the original record.
3. No remaining provenance gaps.

This is completion of the plugin's evidenced trace within the target scope. It is
not a verified truth label or proof that no earlier inaccessible source exists.
When the initial article version is unknown, source findings can be retained but
lineage remains partial.

### Revisions and reanalysis

Keep the original target text and all raw version contents unchanged. A new
analysis replaces that version's current analysis; all prior analyses remain in
`analysis_history`. The current graph is rebuilt from current revisions so deleted
findings do not linger. Stable fragment/relation IDs permit explicit revisions;
the latest analysis wins for a reused ID. Use globally unique IDs for distinct
facts and only reuse an ID when intentionally revising the same finding.

`revisit_versions` names eligible old materials affected by a new finding. Each is
passed back to psi with updated context under the decomposition-call budget.
Adapters own identification of affected dependencies; the runner does not infer
the entire semantic dependency closure. Repeated reanalysis dependencies are
audited and leave an explicit gap. This prevents an adapter from silently cycling
forever. Budget exhaustion while reanalysis is pending also leaves a gap.

## Optional verifier and its return loop

```python
class Verifier:
    def verify(self, target, context):
        return VerificationResult(
            verdict="unresolved", basis=(), rationale="Need a direct record",
            gaps=(Gap("verification:record", "Find the correction", "verification"),),
            resolutions=(),
        )
```

Verdicts are `supported`, `contradicted`, `conflicting`, `unresolved`. A resolved
verdict needs nonempty exact evidence spans and a rationale. Verification gaps
remain open until explicitly resolved and force the visible fact status to
`unresolved`. A verifier may resolve verification gaps; it cannot close a known
provenance gap. The verifier cannot inject raw material directly. It requests a
retrieval task; provider results pass through snapshot preservation, psi and graph
updates before the next verification call.

`provenance_status` and `fact_status` remain independent. A sourced false claim is
possible. The demo produces `original_material_located` and `contradicted` after
three retrieval rounds, four material versions, six decomposition calls and three
verifications. The third round retrieves a correction requested by verification.

## Budgets, errors and output

`max_rounds` bounds provider calls. `max_documents` counts all consumed returns,
including duplicates and exclusions. `max_decomposition_calls` counts all psi
calls, including requested reanalysis. All are positive integers. Empty results,
a budget, completion, or a round with neither new eligible material nor a novel
structural state stops the run. The state includes fragments, relations, origin
findings and open gaps; revision counters, notes and rationale wording do not count
as progress. A repeated material that reveals a new gap can trigger the next
search. Previously seen structural states stop duplicate-only cycles. Duplicate
returns always receive decomposition and comparison before this decision.

Provider, material, decomposer, verifier and integrity failures are recorded in
`errors` and `operations`, terminate processing, and force current provenance to
`unresolved`; enabled fact verification is also reset to `unresolved`. Prior
successful annotations remain visible only as history, not a current success.

The JSON report includes raw `materials`, retrieval `observations`, current
`analyses`, append-only `analysis_history`, `fragments`, `relations`, `origins`,
open `gaps`, `resolutions`, `verification_history`, ordered `operations`, `usage`,
statuses and `stop_reason`. `snapshot_saved` means stored in this run before psi;
the caller must durably persist the report/snapshots for production use.

For independent evaluation, freeze the original target set, cutoff, raw versions,
gold origins, gold lineage relations and verdicts. Do not let adaptive fragments
change the evaluation denominator, and do not use these hand-annotated demo cases
as evidence of real-world accuracy improvement.
