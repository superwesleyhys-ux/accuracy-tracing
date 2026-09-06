# FactCircuit specification

FactCircuit is an auditable claim-and-evidence verification loop. It preserves
the exact claim, immutable evidence versions, source spans, lineage findings,
unresolved work, revisions, resource use, and termination reason so a verdict
can be inspected and replayed instead of accepted as an unexplained label.

## Normative contracts

The current contract is split across focused documents:

- [Trace adapter API](TRACE_ADAPTER.md) defines immutable material, provenance,
  decomposition, verification, retrieval feedback, and fail-closed admission.
- [Staged validation loop](STAGED_VALIDATION_LOOP.md) defines the seven
  single-purpose semantic stages and deterministic assembly boundary.
- [Evaluation schema](EVALUATION_SCHEMA.md) defines fixed gold, predictions,
  metrics, and validation failures.
- [Historical 2023 benchmark](HISTORICAL_2023_BENCHMARK.md) defines cutoff,
  evidence, gold-isolation, and reproducibility rules.
- [v0.3 repair contract](REPAIR_V0.3.md) supersedes conflicting details in the
  original v0.2 handoff.

## Invariants

1. A claim and its assessment cutoff are frozen before inference.
2. Every retrieved material return is versioned and decomposed before it may
   influence a decision.
3. Provenance, document entailment, and real-world truth remain separate.
4. Evidence spans must point to exact stored text; source lineage is not
   inferred from similarity alone.
5. New evidence may reopen affected earlier analyses without erasing history.
6. Missing evidence becomes an explicit bounded task, not invented support.
7. Invalid state fails closed and remains visible in the audit trace.
8. Scores measure agreement with supplied gold; they do not establish truth.

## Naming compatibility

The project and Python distribution were renamed from Accuracy Tracing /
NewsVerify Harness to **FactCircuit** in v0.3.1. New code should import
`factcircuit` and invoke the `factcircuit` command. The `newsverify` import and
command remain supported for compatibility. Earlier reports, executed-code
snapshots, schema identifiers such as `NVScore`, and the original
[v0.2 design specification](ACCURACY_TRACING_SPEC.md) are preserved as
historical evidence rather than rewritten.
