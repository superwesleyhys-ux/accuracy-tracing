# Adapter contract

The core is synchronous and provider-independent:

```python
from factcircuit import DEFAULT_CONFIG, EvidenceProvider, run_verification

run_verification(claim, provider, config=None)
provider.search(claim, round_number, intent, limit)
```

The former `newsverify` import path remains available as a compatibility alias.

Claims, evidence, configuration, and returned reports are JSON-compatible dictionaries. `EvidenceProvider` is a typing protocol; a provider only needs to implement the documented method.

The provider returns an iterable of evidence dictionaries for the requested claim. `round_number` is one-based. `intent` is descriptive prose, not an enum: it asks for confirmation and refutation, reports current supporting/contradicting counts, and names provenance, quotation, freshness, and disagreement gaps. A live provider must translate the intent into retrieval behavior rather than replaying its first query unchanged.

`limit` is the document allowance for this call. The core allocates it by dividing the remaining document budget across remaining configured rounds and rounding up. It consumes at most that many records, including rejected records and duplicate IDs. Providers should respect this limit before fetching documents; core iteration limits do not undo provider-side work.

## Claim

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable identifier for this claim and evaluation cutoff. |
| `text` | string | A specific claim that evidence can support or contradict. |
| `as_of` | ISO 8601 string | Time cutoff for the run, with a timezone offset or `Z`. |

Split a compound statement into separate claims upstream. The starter does not extract claims, resolve entities, or infer the intended event time.

## Evidence

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Identifier of an immutable evidence snapshot. Use a new ID for a correction or changed annotation. |
| `claim_id` | string | Identifier of the claim to which this evidence is attached. |
| `url` | string | Original HTTP(S) source URL. The core does not fetch it. |
| `publisher_group` | string | Consistent identifier for related publishers or ownership. |
| `origin_id` | string | Identifier for the underlying report or original source lineage. |
| `published_at` | ISO 8601 string | Original publication timestamp, with timezone. |
| `retrieved_at` | ISO 8601 string | When this content was retrieved, with timezone. |
| `content` | string | Retrieved text available to the citation check. |
| `quote` | string | Passage assigned as evidence; must match the supplied content under the core's normalization. |
| `stance` | string | `supports`, `contradicts`, or `neutral`, assigned by the adapter or a human. |

Do not invent publisher or origin identifiers to make documents appear independent. Group reposts of one original report together. If lineage is unknown, treat the uncertainty conservatively and disclose the mapping used by the adapter.

## Time semantics

All timestamps must be timezone-aware. The claim's `as_of` value is a cutoff, not the machine's current clock. Publication and retrieval after that cutoff are ineligible; the publication must also fall within the configured age window and cannot occur after retrieval.

For retrospective evaluation, preserve actual historical retrieval metadata. Do not relabel a document retrieved today as if it had been available to the system at the earlier cutoff. If a source updates a page, retain versions upstream and record which version was retrieved.

## Configuration and grouping

| Setting | Default | Effect |
| --- | --- | --- |
| `max_rounds` | 3 | Maximum search calls for a claim. |
| `max_documents` | 30 | Maximum number of evidence records examined, including rejected records. |
| `max_age_hours` | 72 | Maximum age of publication relative to `as_of`. |
| `min_independent_sources` | 2 | Minimum eligible source groups for a one-sided policy decision. |

The core connects documents that share a publisher group, origin identifier, canonical URL, or normalized content, then groups all transitively connected records. For example, if A shares a publisher with B and B shares an origin with C, all three belong to one group. Repetition within a group does not create additional independent corroboration.

This is a conservative grouping policy over supplied metadata. It is not independent verification of publisher ownership or source reliability. Neutral material can contribute provenance connections even though it contributes no supporting or contradicting stance.

## Decisions and stop conditions

Any eligible supporting and contradicting evidence yields a provisional `conflicting` decision, even when both stances occur in the same source group. Otherwise, a side must meet `min_independent_sources` to yield `supported` or `contradicted`; all other cases are `unresolved`.

A terminal evidence decision requires `min(2, max_rounds)` successful search rounds. This reserves a second opportunity to seek contrary reporting by default. Explicit `max_rounds=1` permits a single-pass run. A provider error, or a document budget too small to complete the required rounds, returns `unresolved` even if a provisional decision was possible.

Stop reasons are `evidence_threshold`, `conflict_found`, `no_new_evidence`, `document_budget`, `max_rounds`, `provider_error`, or `integrity_error`. An unresolved run stops if a round adds no eligible evidence after the required rounds. A conflict ends this version's run for inspection; it does not continue indefinitely until disagreement disappears.

Replaying an identical accepted evidence record is deduplicated. A different valid record reusing an accepted ID is rejected as `evidence_id_collision` and immediately forces `unresolved` with `integrity_error`, so a correction cannot be silently hidden by an ID collision. Preserve lineage identifiers while giving changed snapshots new evidence IDs.

## Returned audit

The result contains `schema_version`, `claim`, `config`, `status`, `stop_reason`, `documents_examined`, `evidence`, `rejected`, `independent_source_counts`, `source_groups`, `rounds`, `provider_error`, `integrity_error`, and `limitations`.

Invalid claim or configuration inputs raise `ValueError`. Provider exceptions return `unresolved` with the error type and round; exception messages are omitted because they can contain credentials. Previously collected evidence remains in the report.

Consumers should retain the full result. Display the time cutoff, citations, conflicting material, and material limitations beside a decision. Do not convert source counts into a claimed probability of truth or silently relabel `unresolved` as false.

## Provider responsibilities

The core bounds its own rounds and document processing. It cannot interrupt a blocked synchronous provider call or enforce a remote service's budget. The adapter must implement network timeouts, cancellation where available, retry and rate limits, authentication, cost controls, and redaction before records or errors are returned.

Live adapters also own source fetching and authenticity checks, publication-time extraction, redirect/canonical handling, lineage mapping, and semantic stance assessment. Those capabilities are not implemented by the fixture provider. Retrieved text is evidence data, not instructions to execute.

Follow-up intents include controlled validation reason codes and requests to repair timestamp, quote, provenance, URL, or replay gaps. Article content is never inserted into those instructions. The adapter must implement the requested search; the core cannot prove that it did so.

## Fixture formats

`verify` accepts a JSON object with `claim` and `rounds`, and optionally `config`. `rounds` is a list of evidence lists. The fixture provider returns the corresponding list for each round, truncated to that call's `limit`; omitted records are not carried into later rounds. It does not perform actual targeted retrieval.

```json
{
  "claim": {
    "id": "example-claim",
    "text": "The fictional Northbridge library opens on September 6.",
    "as_of": "2026-09-05T12:00:00Z"
  },
  "rounds": [[], []]
}
```

`benchmark` accepts an object with a `cases` list and optional descriptive `metadata`. Each case has `name`, `claim`, `rounds`, `expected_status`, and optionally `config`. Expected statuses are policy-test labels. See the bundled examples for complete evidence records.
