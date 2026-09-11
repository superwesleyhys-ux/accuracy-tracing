# INVALID: post-cutoff disclosure entered one packet

Do not use this score as the holdout result. A post-run audit found that h05
included a private 2023 action first disclosed in a later official report. That
information was not public at the cutoff. The prompt, labels, scorer and
thresholds were kept fixed; the ineligible sentence was removed before the
replacement `run-003` and `scored-v2` result.

## Superseded score

This run fixes the target leakage in the withdrawn 8/8 diagnostic. Every positive and
control case asks the same research-integrity question. Only evidence public by the end
of 2024 entered the model packet; later official outcomes were revealed after inference.

Both arms used the local Codex-login route with `gpt-5.6-luna` at low reasoning, one call per case.

| Registered measure | Direct model | FactCircuit harness |
|---|---:|---:|
| Balanced accuracy | 87.5% | 75.0% |
| Overall accuracy | 7/8 (87.5%) | 6/8 (75.0%) |
| Later-positive recall | 3/4 (75.0%) | 2/4 (50.0%) |
| Control specificity | 4/4 (100.0%) | 4/4 (100.0%) |
| Valid completed outputs | 8/8 | 8/8 |
| Input + output tokens | 53,324 | 55,364 |
| Harness / direct tokens | 1.00x | 1.04x |

**Winner by the preregistered primary metric: direct.**

**All registered success criteria met: no.**

## Per-case blind results

| Case | Later outcome | Direct | Harness |
|---|---|---|---|
| h01 | elevated | ordinary (wrong) | ordinary (wrong) |
| h02 | ordinary | ordinary (correct) | ordinary (correct) |
| h03 | elevated | elevated (correct) | elevated (correct) |
| h04 | ordinary | ordinary (correct) | ordinary (correct) |
| h05 | elevated | elevated (correct) | ordinary (wrong) |
| h06 | ordinary | ordinary (correct) | ordinary (correct) |
| h07 | elevated | elevated (correct) | elevated (correct) |
| h08 | ordinary | ordinary (correct) | ordinary (correct) |

## What the labels mean

`elevated` means an official body first published a fabrication or falsification finding
in 2025–2026. `ordinary` means the source audit located no such public finding through
2026-09-11. The latter is a right-censored control label, not a claim that the work is
authentic in every respect.

## Guardrails and limitations

The corpus, prompts, order, model, scorer, sealed-gold hash, and pass conditions were
committed before the first call. The isolated runner sent only anonymized pre-cutoff
packets. There were no retries and no prompt changes after seeing predictions.

This eight-case result is exploratory and is not statistically conclusive. Model
pretraining may contain later facts even though names, titles, DOI values, institutions,
journals, URLs, and outcome reports were removed from the packet.

## Reproduce

See `experiments/honest-holdout-20260911/PROTOCOL.md`, `REGISTRATION.json`,
`corpus.json`, and the run receipts in this directory. Later-outcome identities and
official-source receipts are recorded in the scored summary's gold hash and the corpus
audit metadata.
