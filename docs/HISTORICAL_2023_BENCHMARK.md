# 2023 historical forecast benchmark

This author-curated pilot compares the original monolithic semantic adapter with the staged validation loop on propositions published in 2023 and settled in official records no later than 2024-12-31.

## What is isolated

- Every normalized target originates in a dated 2023 official primary source.
- Every adjudicating outcome source was published and available no later than `2024-12-31T23:59:59Z`.
- Inference uses a frozen, offline corpus. It cannot browse the live web.
- Only the claim snapshot is seeded in round one. The frozen outcome snapshot must be acquired through the validation loop.
- Gold labels are stored separately. The `run` command has no `--gold` argument and verifies only the inference-file hashes.
- The inference validator recursively rejects any explicit four-digit year from 2025 onward in model-visible input text. Honest `retrieved_at` capture metadata is audit-only and exempt because both adapters remove it from every model payload.
- Each accepted non-abstaining decision must cite an exact span in the frozen outcome scope. The engine rejects conclusive evidence judgements that cite outside that scope.
- Each source entry binds its excerpt to an official URL, accession/citation/report identifier, cutoff-eligible observation time, raw-artifact byte count, and raw-artifact SHA-256.

The excerpts were collected after the historical cutoff, so `retrieved_at` honestly records the 2026 capture in the audit trail. It is removed from every model payload instead of being rewritten to a historical date. Historical eligibility is based on the versioned official publication/availability record. Dynamic navigation, related links, and current recommendations were removed; only the relevant dated body excerpt is admitted to inference.

This is historical **evidence isolation**, not a cryptographic time machine. A current model may contain knowledge learned after 2024. The protocol prevents that memory from becoming accepted evidence, but it cannot delete it from model parameters. Therefore results must not be described as proving that the model itself was unaware of later events.

## Fixed cases

| Case | 2023 proposition | Official outcome available by cutoff | Gold |
|---|---|---|---|
| `tesla-cybertruck-2023` | Tesla begins Cybertruck customer deliveries by 2023 year-end | Tesla's filed 10-K says first deliveries occurred in November 2023 | true |
| `virgin-galactic-commercial-service-2023` | Virgin Galactic begins commercial service in 2023 Q2 | Its filed 10-K identifies Galactic 01 in June as the start of commercial service | true |
| `nasa-osiris-rex-2023` | OSIRIS-REx releases its capsule and lands it at UTTR on 2023-09-24 | A versioned NASA NTRS paper records both events at UTTR that day | true |
| `sec-t1-2024` | Covered U.S. securities markets move to T+1 on 2024-05-28 | A cutoff-archived SEC speech says the relevant markets successfully moved that day | true |
| `lucid-production-2023` | Lucid manufactures more than 10,000 vehicles in 2023 | Its filed results report 8,428 | false |
| `boeing-starliner-cft-2023` | Boeing completes Starliner CFT in 2023 | Its filed 10-Q says CFT launched on 2024-06-05 | false |
| `wto-merchandise-trade-2023` | 2023 world merchandise trade volume grows 1.7% | WTO reports a 1.2% decline | false |
| `noaa-atlantic-storms-2023` | The 2023 Atlantic season finishes with 12–17 named storms | NOAA reports 20 named storms | false |

The target is always the **future outcome**, not the historical statement that an organization once made a forecast. Each gold rationale and exact adjudicating quotation is stored separately from inference.

Primary sources are linked in [`experiments/historical-2023/inputs.json`](../experiments/historical-2023/inputs.json). Source roles, version records, excerpt hashes, and raw-artifact identities are in [`sources.json`](../experiments/historical-2023/sources.json); author-curated labels, rationales, and exact outcome quotations are in [`gold.json`](../experiments/historical-2023/gold.json). Raw binaries are not vendored, so the version-proof fields are recorded dataset-owner declarations and the offline audit checks only their schema, cutoff eligibility, committed records, and internal excerpt/hash bindings. It does not refetch or independently authenticate remote bytes. The EDGAR/NTRS identifiers, dated-PDF metadata, and timestamped web-archive locators are provided so an external reviewer can perform that separate verification.

[`freeze.json`](../experiments/historical-2023/freeze.json) is an internal consistency checksum. A clean Git commit containing every input is the separate pre-call binding; the runner records that commit and rejects a dirty or uncommitted benchmark before any model call.

## Fair comparison contract

Both arms must use the `equal-v1` execution profile. It fixes the same:

- requested model and reasoning effort;
- frozen input/corpus hash and material order;
- per-case call, output-token, per-call-output, and wall-time ceilings;
- maximum rounds, documents, and decomposition calls.

Input tokens are measured and reported but are not capped, so this is an equal **outer-cap** comparison rather than an equal-token-cost comparison. Actual usage is reported separately and is not expected to be equal: prompt splitting deliberately uses more calls. Budget exhaustion and all other per-case failures remain in the denominator as `unverifiable`; no case may be dropped. Staged mode keeps its one bounded repair because that repair loop is part of the candidate system, while both systems remain under the same outer resource ceiling.

The main historical path forbids replay. After a run, scoring reopens the two arms' configs, raw results, call logs, statuses, and checksummed artifact manifest; it verifies the same requested and actual model, reasoning effort, code/input/source hashes, budget, trace contract, and clean commit before reading gold. It also replays logged outputs locally to ensure each trace, prediction, and declared failure follows from those bytes. These checks prove internal consistency only. The API does not sign this local log, so a self-consistent log cannot prove that its recorded output was actually returned by the API; independent API provenance would require an external signed or append-only anchor.

Four predeclared full-evidence controls help distinguish retrieval failure from reasoning failure. They are diagnostic and excluded from the main eight-case accuracy.

## Commands

Audit the frozen benchmark without model access:

```bash
python3 experiments/historical_compare.py audit \
  --inputs experiments/historical-2023/inputs.json \
  --sources experiments/historical-2023/sources.json \
  --gold experiments/historical-2023/gold.json \
  --freeze experiments/historical-2023/freeze.json
```

For a live comparison, first commit the frozen benchmark, revoke any credential ever pasted into chat, and configure a fresh credential outside chat. The runner additionally requires an explicit local opt-in and never prints or persists the credential:

```bash
# OPENAI_API_KEY must already be present in the process environment.
export FACTCIRCUIT_ALLOW_MODEL_CALLS=1
python3 experiments/historical_compare.py run \
  --inputs experiments/historical-2023/inputs.json \
  --sources experiments/historical-2023/sources.json \
  --freeze experiments/historical-2023/freeze.json \
  --output reports/historical-2023-run-001 \
  --model MODEL_NAME \
  --reasoning-effort medium
unset FACTCIRCUIT_ALLOW_MODEL_CALLS
```

`ACCURACY_TRACING_ALLOW_MODEL_CALLS=1` remains accepted for scripts created
before the FactCircuit rename.

Only after both arms finish, score against the separately checksummed gold:

```bash
python3 experiments/historical_compare.py score \
  --inputs experiments/historical-2023/inputs.json \
  --sources experiments/historical-2023/sources.json \
  --gold experiments/historical-2023/gold.json \
  --freeze experiments/historical-2023/freeze.json \
  --run reports/historical-2023-run-001
```

The score report includes paired exact-label accuracy, true-case recall, false-case recall, abstention, completion, resource usage, and a per-case win/loss table. With only eight cases, this is a smoke benchmark for catching regressions and guiding iteration, not evidence of general deployment accuracy or a guarantee that prompt splitting always improves accuracy.
