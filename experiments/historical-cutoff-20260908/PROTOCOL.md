# Historical-cutoff comparison: frozen protocol

This is a new experiment, separate from every earlier batch. Gstack's model
benchmark guidance supplies fixed settings, provider preflight, measured usage
and explicit failures. Its generic model shootout does not run this harness;
this driver reuses the established recorded local transport and full pipeline.
No remote model judge, new provider, inference or later-gold loading occurs
during implementation or the offline self-test. Actual launch follows root
review of the corpus and a transport-readiness check.

## Question and sample

Compare the same requested Astra model alone versus Astra with the full harness
on claims made before 2024. Every evidence packet ends at its own timezone-aware
cutoff, no later than 2023-12-31 23:59:59 UTC. Later 2025–2026 evidence is used
only by a separate evaluator to assess subsequent real-world findings. Neither
arm is told the outcome composition or the reason a particular claim was chosen.

The selected sample has two event families: the 2023 Osaka DAT study and the
2017 Hargreaves wastewater study, each with public 2025 fabrication findings.
Each contributes one authenticity target and one true attribution control, in
named and deterministically identity-masked form: eight cases, sixteen runs.
The four named cases form the primary historical analysis; four masked derivatives
are a separate sensitivity analysis and are never counted as more independent
events. The targets are curator formulations of the original papers' implicit
data-authenticity assertions, not verbatim dated historical statements.
Control/future-outcome classifications remain in private gold only;
input variant metadata uses only `original` or `blinded` and opaque pairing IDs.
This helps expose an always-abstain or always-false strategy. A later finding of
fabrication must concern the precise observation/data-existence claim; it does
not establish that a biological effect itself is false. Do not force
the count by accepting unsubstantiated historical availability. The driver
accepts 1–12 cases including variants; family and variant counts must be reported.
Cases from one event, and original/masked versions, are correlated observations.
The exact earliest public disclosure date for Hargreaves is uncertain; the
publisher's 2025 retraction date and admission of fabrication are verified. The
Osaka investigation began privately in 2024 and was publicly announced in 2025.
The current institutional report may include later 2025 revisions. Neither claim
of first-ever private discovery nor exhaustive absence of earlier public rumors
is made. Both historical evidence packets stop at 2023-12-31.

The corpus uses one complete historical manuscript per family plus an expressly
identified excerpt from that same manuscript as the harness's initial material.
These are two access scopes of one source, not independent corroboration. Original
PDF bytes are retained; later covers/banners are excluded from exposed text.
The text transport includes captions and extracted tables but cannot inspect the
figures visually, so this is not a test of image-forensics detection.

## Allowed corpus schema

`inputs/corpus.json` contains exactly `schema_version: 1` and a `cases` list.
Each case contains these fields only:

```json
{
  "target": {
    "id": "h01",
    "text": "The exact historical claim, including attribution and qualifiers.",
    "as_of": "2023-12-31T23:59:59Z",
    "source_version_id": "v1"
  },
  "claim_made_at": "2023-01-01T00:00:00Z",
  "initial_version_ids": ["v1"],
  "materials": [{
    "version_id": "v1",
    "url": "https://example.invalid/historical-record",
    "content": "Complete permitted historical text, without later annotations.",
    "retrieved_at": "2026-09-08T00:00:00Z",
    "published_at": "2023-01-01T00:00:00Z",
    "available_at": "2023-01-01T00:00:00Z",
    "availability_basis": "Evidence that THIS exact version was available by the cutoff.",
    "issuer": "Contemporary publisher"
  }],
  "config": {"max_rounds": 4, "max_documents": 6, "max_decomposition_calls": 8},
  "variant": {"kind": "original", "pair_id": "family01"}
}
```

The example timestamps and content above are schema illustrations, not evidence.
`config` and `variant` are optional; the driver strips claim date and variant
metadata before inference. Claim date, exact-version availability and any supplied
publication timestamp must precede the case cutoff. `published_at` may be null
or omitted when no precise publication timestamp is established. Later retrieval is permitted only for demonstrably
old versions. A current live page with an old publication date is insufficient
proof: later edits, appended corrections, nav links and metadata can leak facts.
Researchers must inspect the exact exposed bytes and document the archive/version
evidence. Do not fabricate midnight timestamps for date-only observations. A
documented conservative upper bound may represent `available_at`/`claim_made_at`
(for example, the end of the stated date anywhere on Earth, expressed in UTC);
state that it is an upper bound and retain the actual date-only metadata in the
private research archive. This does not establish that an edited current page
is identical to the version available on that date.

Keep source captures, research notes, later sources, verdicts, blinding mappings
and semantic-change notes outside `inputs/`, preferably in `private/`. None are
accepted as corpus keys. Keep later evidence in a separate `private/gold.json`;
the driver never opens that file, hashes its bytes, or copies it into a worker.

Blinded cases are prepared deterministically before inference. Replace only
identifiers using a private mapping; preserve counts, dates, negation, attribution,
source dependence and relevant technical meaning. Record the transformation code
hash, private mapping and any semantic differences for evaluator review. The
driver receives only already transformed corpus text and opaque pairing metadata.
Changed wording may change difficulty and historical meaning. Blinding cannot
erase model memory or prove a clean training cutoff; report it as a sensitivity
check, not a privacy or contamination cure.

## Matching conditions and isolation

Both arms use local Codex login, requested `gpt-6-astra`, medium reasoning, the
same explicit temporary HTTP provider profile, and current per-process skill
catalog disabling. Built-in Codex instructions remain. Every stage in both arms
receives the identical historical evidence contract before its task prompt.
The contract asks for evidence-supported judgments as of the cutoff, distinguishes
source assertions from world facts, and prohibits later memories or outside tools.
It does not reveal any selected case's later outcome.

The direct arm receives the full allowed case pool once. The harness initially
receives its designated source and selects further material only from that same
pool. No browsing, external retrieval, filesystem tool or other model is supplied.
Per-case calls are one for direct and at most ten for the harness; every call has
a 90-second deadline. Run sequentially, rotating arm order by case. No logical
retry, selective rerun or API fallback is allowed. Internal CLI transport retries
are not counted as separate logical calls. There is no common token ceiling.

The supervisor reads the allowed corpus, its boolean/hash preflight, and a
separate registration containing only artifact hashes and a timestamp. It never
opens the committed gold or review artifacts. It copies the permitted corpus
and required Python source to a temporary workspace.
A macOS `sandbox-exec` worker denies all file reads from the original repository,
the original corpus directory, and any additional `--deny-read-root` directories.
This excludes original research, gold, private mappings, reports and old outputs.
The original registration and its supervisor archive are also denied by exact
file path, including when they are outside the repository. The worker receives
neither the registration nor its gold hash and verifies denial before any model
call; no unsandboxed fallback exists.
The installed Python/Codex runtime and Codex login remain accessible. This is
filesystem separation of research artifacts, not erasure of pretrained knowledge
or an attestation that every provider-side instruction is absent.

Every exposed packet, response, receipt, selected source and accepted revision is
preserved. Code and corpus are copied with SHA-256 checks before inference.
Outputs are copied back after the worker exits, including partial results on
failure. A new output directory is mandatory. The inference artifact is
`stage-artifacts/predictions.json`; it contains no gold labels.

## Preflight and commands

The supervisor requires `PREFLIGHT.json` with the exact corpus SHA-256 and boolean
true fields `passed`, `cutoff_evidence_reviewed`, `claim_dates_reviewed`,
`future_gold_separated`, `variant_transforms_reviewed`, and
`local_transport_ready`. The independent reviewer should keep detailed evidence
outside this boolean/hash record. This is a launch gate, not proof of gold quality.

Live launch also requires `REGISTRATION.json` (override with `--registration`).
Its exact fields are `schema_version: 1`, a timezone-aware ISO `registered_at`
timestamp no later than launch, and seven 64-character hexadecimal hashes:
`corpus_sha256`, `gold_sha256`, `scorer_sha256`, `helper_sha256`, `builder_sha256`,
`input_review_sha256`, and `gold_review_sha256`. The corpus commitment must match
the actual input bytes. A separate preparation step computes these commitments;
the inference supervisor validates only the metadata and corpus commitment,
without opening gold, scorer, scorer-helper, builder or review files. It copies the exact
registration to the result directory as `registration.json` and binds its byte
hash as `registration_sha256` in the manifest before starting the worker.
Registration contents never enter the worker, its policy or a model packet;
the worker policy records only denied file paths. The separate scorer validates
the committed artifacts against this frozen registration before scoring.
The deterministic offline stub may run without registration.

```sh
python experiments/historical-cutoff-20260908/run_test.py --self-test
python experiments/historical-cutoff-20260908/run_test.py --corpus experiments/historical-cutoff-20260908/inputs/corpus.json
# Only after independent dataset and local transport preflight:
python experiments/historical-cutoff-20260908/run_test.py --run --output experiments/historical-cutoff-20260908/results
```

The first two commands perform no inference. The self-test uses explicit synthetic
transport responses and tests real filesystem denial. Live launch is currently
macOS-specific; other platforms require an independently verified equivalent
sandbox. Do not substitute an unisolated worker to make the command pass.

## Separate scoring contract

The scorer, implemented/reviewed separately, joins predictions to private gold
only after the inference batch finishes. Gold should retain distinct fields for
`cutoff_evidence_verdict`, `cutoff_rationale`, `future_actual_verdict`,
`future_resolution_as_of` (2025 or 2026), later source evidence, and adjudication
uncertainty. The future label must not overwrite the evidence-at-cutoff label.

Report these separately, with every scheduled case retained in each arm's
denominator and execution failures excluded from successful abstention credit:

- Agreement with independently reviewed cutoff-evidence verdicts.
- Abstention and valid abstention when contemporary evidence cannot settle it.
- Unsupported certainty when the model gives `supported` or `contradicted`
  without enough eligible cutoff evidence, even if that verdict happens to match
  later findings. Retain `conflicting` as its own class; do not silently treat an
  explicit conflict judgment as confident acceptance or rejection.
- Later-world correctness and error direction, explicitly descriptive and not
  evidence of what was knowable at the cutoff.
- Exact quote integrity and eligible-source coverage, separately from semantic
  entailment, attribution accuracy and certainty.
- Logical calls, input/output/cached tokens, timing, errors and actual loop proof.

Do not reward clairvoyance: agreement with a later falsehood finding is not a
cutoff reasoning success when the supplied contemporary packet is unresolved.
Conversely, a well-supported contemporary attribution need not become a model
error merely because the underlying assertion was later disproved. Original vs
blinded comparisons are paired by event and report semantic transformation
differences. If the selected sample contains only later-refuted claims, disclose
that selection after inference; it cannot estimate broad sensitivity/specificity
or general news accuracy. Preserve predeclared labels and adjudicate defects in
separate records rather than rewriting the original primary score.
