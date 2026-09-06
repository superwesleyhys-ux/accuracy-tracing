# FactCircuit development archive

> This public repository preserves the early Accuracy Tracing / NewsVerify
> Harness development milestone. The project is now **FactCircuit**; use the
> [canonical repository](https://github.com/superwesleyhys-ux/factcircuit) for
> the current package, documentation, releases, and contributions. Historical
> names below are intentionally retained as part of the archived record.

Version 0.2.0: a bounded, auditable news provenance loop with **decomposition on every retrieval return**, a separate verification feedback stage, and a fixed-target evaluation toolkit.

**Status: executable offline reference implementation.** Semantic judgments in the demo are hand-authored annotations. The default decomposer preserves original text and leaves source questions unresolved. No live news adapter, general-purpose model API, independently reviewed real-news benchmark or measured real-world accuracy improvement is included.

Repository Discussions are enabled, and the repository includes a prepared **Accuracy decline** reporting form for reproducible metric regressions or weaker trace outcomes. Reports should identify the affected metric or behavior, include the run configuration, and avoid treating synthetic fixtures as real-world performance evidence.

## Run

Python 3.11+; standard library only. From this project directory:

```bash
python -m newsverify trace-demo --output reports/trace-demo-v0.2.json
python -m newsverify score examples/evaluation_gold.json examples/evaluation_predictions.json --output reports/all-metrics-v0.2.json
python -m newsverify compare examples/evaluation_gold.json examples/comparison_baseline.json examples/comparison_candidate.json --bootstrap-samples 100 --seed 0 --output reports/comparison-v0.2.json
python -m unittest discover -s tests -v
```

The trace demo follows four material versions over three retrieval rounds, reopens affected old analyses, and routes a verification-requested correction through decomposition. It preserves the original target and separates lineage from semantic contradiction.

The metric example is a deliberately imperfect set of four **handwritten predictions**, used to verify arithmetic against independent expected values. The comparison example uses identical handwritten runs to check paired differences. Neither example is a model performance result.

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
