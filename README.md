# FactCircuit development archive

> This public repository preserves the early Accuracy Tracing / NewsVerify
> Harness development milestone. The project is now **FactCircuit**; use the
> [canonical repository](https://github.com/superwesleyhys-ux/factcircuit) for
> the current package, documentation, releases, and contributions. Historical
> names below are intentionally retained as part of the archived record.

Version 0.2.0: a bounded, auditable news provenance loop with **decomposition on every retrieval return**, a separate verification feedback stage, and a fixed-target evaluation toolkit.

**Status: local harness with offline replay and two model execution paths.** Semantic judgments in the demo are hand-authored annotations. The default decomposer preserves original text and leaves source questions unresolved. Model-backed tracing supports local Codex execution and an optional OpenAI API tunnel. No live news adapter, independently reviewed real-news benchmark or measured real-world accuracy improvement is included.

Repository Discussions are enabled, and the repository includes a prepared **Accuracy decline** reporting form for reproducible metric regressions or weaker trace outcomes. Reports should identify the affected metric or behavior, include the run configuration, and avoid treating synthetic fixtures as real-world performance evidence.

## Run

Python 3.11+; standard library only. From this project directory:

```bash
python -m newsverify trace examples/local_trace.json --output reports/local-trace.json
python -m newsverify trace-demo --output reports/trace-demo-v0.2.json
python -m newsverify score examples/evaluation_gold.json examples/evaluation_predictions.json --output reports/all-metrics-v0.2.json
python -m newsverify compare examples/evaluation_gold.json examples/comparison_baseline.json examples/comparison_candidate.json --bootstrap-samples 100 --seed 0 --output reports/comparison-v0.2.json
python -m unittest discover -s tests -v
```

The trace demo follows four material versions over three retrieval rounds, reopens affected old analyses, and routes a verification-requested correction through decomposition. It preserves the original target and separates lineage from semantic contradiction.

The metric example is a deliberately imperfect set of four **handwritten predictions**, used to verify arithmetic against independent expected values. The comparison example uses identical handwritten runs to check paired differences. Neither example is a model performance result.

## Local harness execution

`trace <input.json>` runs directly in the local Python process. It reads a JSON
object with `target`, `rounds` (lists of material-version objects), and optional
`config`; see [local_trace.json](examples/local_trace.json). Source URLs are audit
metadata only and are never fetched. No API key, HTTP service, model SDK, or
remote inference is needed. Reports are written locally with `--output`.

This command preserves supplied text using `ConservativeDecomposer` and leaves
fact status as `not_checked` and original-source judgments unresolved. It does not turn a
snapshot into an automatic fact check. For semantic work, the hosting local
harness can pass its own Python `Decomposer` and `Verifier` objects directly to
`run_provenance`; a remote API is not part of the required integration.

The [public model comparison](reports/model-evaluation-20260908/README.md)
records Astra alone versus Astra inside the full harness. The local CLI uses a
hosted model through the existing Codex login; this is not offline inference,
an equal-compute experiment, or a held-out real-news accuracy result.

## Two model execution tunnels

Both tunnels run the same decomposition and verification adapters in the local
harness. **Local is the default** for `trace-model`. Select API explicitly:

```bash
# Tunnel 1: local Codex CLI, using the existing Codex login
python -m newsverify trace-model examples/model_trace.json --output reports/model-local.json

# Tunnel 2: OpenAI Responses API, using OPENAI_API_KEY from the environment
python -m newsverify trace-model examples/model_trace.json --tunnel api --output reports/model-api.json
```

`--model` and `--reasoning-effort` override the configured Codex model/settings;
if no model is configured, supply `--model`. `--timeout` sets the per-call timeout
in seconds (default 180). The API tunnel uses the standard library and requires
`OPENAI_API_KEY`; the local tunnel does not use an API key. Local Codex execution
can still use a hosted model, so it is distinct from offline inference.

Reports contain `execution.tunnel`, model settings and measured model-call usage.
Both paths use the same output schemas, exact-quote checks and historical
eligibility rules. Ineligible materials receive local preservation and do not
reach either model. Failed calls remain errors in the selected path; there is
no automatic fallback. Exit status is 1 for an audited execution failure and 2
for invalid input or unavailable configuration.

`trace-model` extracts claims and verifies facts over supplied snapshots. These
adapters do not yet infer a source graph or perform active follow-up retrieval;
a fact verdict does not mean provenance is complete. `trace` remains the fully
offline snapshot command described above. See [the tunnel contract](docs/MODEL_TUNNELS.md)
for configuration, reporting and validation details.

## Opt-in double-loop model runner

`newsverify.double_loop` adds model-generated source relations, evidence gaps,
gap resolutions and requests to reopen earlier analyses. Its provider selects
additional eligible documents from a fixed local snapshot pool in response to
the actual open questions. Verification follow-up enters that same retrieval
and decomposition path. It does not search the open web.

```bash
python -m newsverify.double_loop CASE.json --output REPORT.json --max-model-calls 10
```

The input contains `target`, `materials`, one `initial_version_ids` entry, and
optional round/document/decomposition `config` limits. Local is the default;
`--tunnel api` selects the separate API route. Reports preserve all model-stage
inputs and outputs, call usage, source-selection requests and analysis revisions.
The call cap includes selection, decomposition and verification. There is no
enforced total-token ceiling.

[Experiment code and reproducibility limits](experiments/README.md) describe
the public receipts and locally retained evidence archive. The 176 automated
tests use controlled fixtures; real model outcomes and actual loop execution
are reported separately. Verification questions reopened by newer evidence
cannot be silently closed by an older resolution, and provenance gap identities
remain protected after retirement. Local model subprocesses exclude installed
skill catalogs while retaining normal Codex instructions.

The [completed local Astra comparison](reports/model-evaluation-20260908/README.md)
records six constructed cases across three research topics. Original registered
label matches were 6/6 for Astra alone and 5/6 with the harness. The difference
exposed a corpus defect: the harness correctly flagged a news-date qualifier
missing from the supplied text. Both matched the five undisputed cases and a
separately reported corrected follow-up. The harness used 5.72 times the tokens
in the original batch. All 49 original and follow-up model calls succeeded.
Neither the flawed original tally nor the selected repair establishes general
accuracy superiority. Full source captures remain local; public numeric
receipts can be independently checked without redistributing publisher text.

The separate [historical-cutoff comparison](reports/historical-evaluation-20260908/README.md)
tests two pre-2024 research papers with public fabrication findings in 2025.
Only historical paper text available by December 31, 2023 enters the model;
later findings are held separately for scoring. Named cases and identity-masked
variants are reported separately, with true attribution controls. This is a
small retrospective test of supplied evidence, not a way to remove later
knowledge from the model's training. Abstaining on authenticity does not count
as detecting fabrication.

Both paths left both named authenticity claims unresolved and correctly answered
both attribution controls. The harness used 363,147 tokens versus 92,818 for
Astra alone (3.91 times as many). The masked cases retained one timeout in
each arm; its missing usage prevents an exact whole-batch token total. A separate
[Inspect AI replay](reports/historical-inspect-audit-20260908/README.md)
checks the saved outcomes without new model calls. These results show no advance
fabrication-detection benefit on this two-event sample.

## Trace engine

`run_provenance(target, provider, decomposer=None, verifier=None, config=None)` uses typed plug-ins documented in [TRACE_ADAPTER.md](docs/TRACE_ADAPTER.md).

- Immutable material versions, exact source spans and observation records.
- Every valid return is saved and decomposed before graph or verifier admission.
- Same-URL revisions keep distinct identities; an ID/content collision fails unresolved.
- Candidate relations distinguish direct, declared, inferred, unresolved and excluded evidence.
- Original-source completion requires an explicit finding and a direct lineage path from the target's source version. Support/contradiction edges do not substitute for that path.
- `revisit_versions` triggers affected earlier analyses; current results are rebuilt while history remains available.
- Verification gaps follow the same retrieval/decomposition route.
- Round, material and decomposition budgets, plus explicit no-progress and error results.
- Historical admission requires an exact version availability declaration and basis. There is no arbitrary age cutoff for old original records.

Historical graph admission is not proof against all future-information leakage: a stateful adapter might retain excluded content, and a pretrained model may already know later events. Strict historical inference isolation, live timeouts and model token accounting remain adapter work.

## Evaluation

Gold labels and predictions are separate files. Cases are fixed before inference. Missing/extra/duplicate target IDs, mismatched cutoffs, unjudged evidence IDs and invalid probabilities fail validation.

| Metric | Measures |
|---|---|
| VP | Precision of claims admitted to the trusted feed |
| FR | Fraction of false claims withheld from the feed |
| TR | Fraction of true claims admitted |
| SR | Correct original-root sets with valid provenance paths on traceable targets |
| EN | Precision of evidence asserted to support its target |
| CA | One minus half the four-class Brier score; probability quality, not pure calibration |
| HFAR | High-risk false claims incorrectly admitted |

Also reports source precision, false promotion of unknown origins, edge precision/recall, evidence recall, duplicate-pair F1, confusion matrix, coverage and ECE. A zero denominator is `null`. Missing probability vectors make CA and the aggregate unavailable. Scores never establish truth by themselves.

The experimental `NVScore` preserves the weights discussed in the design. It is not Terminal-Bench or an official benchmark, and its weights are not empirically validated. `compare` checks **declared** equal model/corpus/budget settings and supplied usage, then produces paired event-cluster bootstrap intervals. It cannot attest that external model usage logs are authentic.

The trace engine and scorer have separate schemas. A production exporter and independently reviewed data are still required; no implicit conversion turns plug-in judgments into gold labels.

## Documents

- [Chinese design conclusion and all metric definitions](docs/ACCURACY_TRACING_SPEC.md)
- [Codex execution plan and remaining implementation sequence](docs/CODEX_EXECUTION_PLAN.md)
- [Trace adapter API](docs/TRACE_ADAPTER.md)
- [Evaluation schema](docs/EVALUATION_SCHEMA.md)
- [Observed validation report](reports/VALIDATION_V0.2.md)

## Legacy compatibility

`python -m newsverify demo`, `verify`, and `benchmark` retain the v0.1 annotated-evidence policy runner in `core.py`. Its publisher/origin grouping and 72-hour default window are legacy policy choices, not the v0.2 provenance algorithm. Its 22 synthetic scenarios remain regression tests, not real-news accuracy estimates. The earlier [adapter contract](docs/ADAPTER_CONTRACT.md) applies to that runner only.

Released under the [MIT License](LICENSE). Current project:
[superwesleyhys-ux/factcircuit](https://github.com/superwesleyhys-ux/factcircuit).
