# Honest local comparison: direct model vs FactCircuit

The final compliant run found that the direct model performed better than the
FactCircuit prompt on this eight-paper same-task historical holdout.

| Registered measure | Direct model | FactCircuit harness |
|---|---:|---:|
| Balanced accuracy | **87.5%** | 75.0% |
| Overall accuracy | **7/8** | 6/8 |
| Later-positive recall | **3/4** | 2/4 |
| Control specificity | 4/4 | 4/4 |
| Valid completed outputs | 8/8 | 8/8 |
| Input + output tokens | **53,302** | 55,378 |
| Harness / direct tokens | 1.00x | 1.04x |

**Winner by the preregistered primary metric: direct model.** The harness did
not meet the registered requirement to exceed the direct arm. It did meet the
completion and token-budget requirements.

The full final report is in [scored-v2/README.md](scored-v2/README.md), with
machine-readable metrics in [scored-v2/SUMMARY.json](scored-v2/SUMMARY.json),
raw predictions and token receipts in [run-003](run-003), and the outcome labels
revealed after inference in [scored-v2/REVEALED_GOLD.json](scored-v2/REVEALED_GOLD.json).

## What failed

- `h01`: both arms returned `ordinary`. The public pre-cutoff packet contained
  no correction, anomaly, investigation, or other specific warning. Its 2026
  finding was not inferable from the supplied historical evidence without
  guessing.
- `h05`: the direct arm returned `elevated`, while the harness returned
  `ordinary`. The harness treated the 2022 public allegation of image
  manipulation as one unconfirmed moderate signal. Its fixed rule required one
  documented strong signal or two moderate signals, so the rule was too
  conservative for this screening task.

Changing the policy around these two answers now would tune on the holdout. A
future policy can be developed on separate cases, then evaluated on a new,
untouched holdout.

## Run history

| Artifact | Status | Reason |
|---|---|---|
| `run-001` | failed, unscored | The preregistered `gpt-5.4-mini` model is unsupported through the local ChatGPT-login route; all 16 launches failed before producing answers. |
| `run-002` / `scored-v1` | invalid | A publication audit found that one h05 sentence described a private 2023 action first disclosed after the cutoff. The sentence was removed; prompts, labels, scorer, and thresholds were unchanged. |
| `run-003` / `scored-v2` | final compliant run | All 16 calls completed, only eligible public pre-cutoff information entered inference, and scoring used the preregistered sealed-gold hash. |

The setup and amendment history is committed under
[`experiments/honest-holdout-20260911`](../../experiments/honest-holdout-20260911).
The final test uses a hosted model through the existing Codex login. “Local”
describes the CLI route and absence of an API key; it does not mean offline
model weights.
