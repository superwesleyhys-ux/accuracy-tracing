# Honest system holdout v3: original model vs FactCircuit source tracing

This is a preregistered system comparison on eight previously unused papers. The direct
arm received the anonymized original-article record. The harness arm received the same
record plus source traces that were already public by the end of 2024. Later publisher
outcomes were sealed and revealed only after inference.

Both arms used the local Codex-login route with `gpt-5.6-luna` at low reasoning, one call per case.

| Registered measure | Direct model | FactCircuit harness |
|---|---:|---:|
| Balanced accuracy | 50.0% | 87.5% |
| Overall accuracy | 4/8 (50.0%) | 7/8 (87.5%) |
| Later-positive recall | 0/4 (0.0%) | 3/4 (75.0%) |
| Control specificity | 4/4 (100.0%) | 4/4 (100.0%) |
| Valid completed outputs | 8/8 | 7/8 |
| Input + output tokens | 53,355 | 57,094 |
| Harness / direct tokens | 1.00x | 1.07x |

**Winner by the preregistered primary metric: harness.**

**All registered success criteria met: no.**

## Per-case blind results

| Case | Later outcome | Direct | Harness |
|---|---|---|---|
| v301 | elevated | ordinary (wrong) | None (wrong) |
| v302 | ordinary | ordinary (correct) | ordinary (correct) |
| v303 | elevated | ordinary (wrong) | elevated (correct) |
| v304 | ordinary | ordinary (correct) | ordinary (correct) |
| v305 | elevated | ordinary (wrong) | elevated (correct) |
| v306 | ordinary | ordinary (correct) | ordinary (correct) |
| v307 | elevated | ordinary (wrong) | elevated (correct) |
| v308 | ordinary | ordinary (correct) | ordinary (correct) |

## What the labels mean

`elevated` means a publisher first issued the registered retraction outcome in 2025–2026.
`ordinary` means the source audit located no retraction concerning the control through
2026-09-11. The latter is a right-censored control label, not a claim that the work is
authentic in every respect.

## Guardrails and limitations

The corpus, both arm packets, prompts, order, model, scorer, sealed-gold hash, and pass
conditions were committed before the first call. The isolated runner sent only the
registered anonymized packet for each arm. There were no retries or post-result changes.

This eight-case result is exploratory and is not statistically conclusive. Model
pretraining may contain later facts even though names, titles, DOI values, institutions,
journals, URLs, and outcome reports were removed from the packet.

## Reproduce

See `experiments/honest-system-holdout-v3-20260911/PROTOCOL.md`, `REGISTRATION.json`,
`corpus.json`, `SOURCE_AUDIT.json`, and the run receipts in this directory. The revealed
gold file contains the post-cutoff publisher outcomes and matches the hash committed
before inference.
