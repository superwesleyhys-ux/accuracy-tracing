# Historical Astra versus updated news-tracing harness

On the two named authenticity cases per arm, **Astra alone: 0 called false, 2 unresolved, 0 failed or invalid**; **Astra + updated harness: 0 called false, 1 unresolved, 1 failed or invalid**. Failed or invalid pipelines receive no abstention or detection credit. Calling a claim false does not establish justified advance fraud detection.

This fresh run compares the same Astra model on eight fixed historical cases from two event families. Four named cases are the primary analysis; four identity-masked derivatives are a separate sensitivity check. Evidence was available by **2023-12-31**. The held-out 2025 findings were scored only after inference.

Both arms use GPT-6 Astra with medium reasoning. **Local means Codex CLI with hosted model inference**, not local model weights. The direct arm receives the entire allowed pool in one call; the updated treatment adds research stages before its formal double loop, with a 24-call shared cap and a ten-call formal cap. This is a new treatment on the old cases, not an exact rerun of the older ten-call double-loop-only harness.

## Named primary cases

Each arm has two authenticity cases and two attribution controls. Authenticity outcomes below partition all two requested cases; failed or invalid runs receive no abstention or detection credit.

| Workflow | Valid cutoff matches / 4 | Later-false: called false / 2 | Unresolved / 2 | Accepted / 2 | Conflict / 2 | Failed or invalid / 2 | Control matches / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Astra alone | 4/4 | 0/2 | 2/2 | 0/2 | 0/2 | 0/2 | 2/2 |
| Astra + updated harness | 1/4 | 0/2 | 1/2 | 0/2 | 0/2 | 1/2 | 0/2 |

## Masked sensitivity cases

Each arm has two authenticity cases and two attribution controls. Authenticity outcomes below partition all two requested cases; failed or invalid runs receive no abstention or detection credit.

| Workflow | Valid cutoff matches / 4 | Later-false: called false / 2 | Unresolved / 2 | Accepted / 2 | Conflict / 2 | Failed or invalid / 2 | Control matches / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Astra alone | 4/4 | 0/2 | 2/2 | 0/2 | 0/2 | 0/2 | 2/2 |
| Astra + updated harness | 1/4 | 0/2 | 0/2 | 0/2 | 0/2 | 2/2 | 1/2 |

Calling a later-false authenticity claim false is a match to the eventual outcome, not proof of justified advance fraud detection. The registered cutoff answer for those claims is unresolved. Exact quotation checks do not establish that a quotation supports every part of a conclusion. Abstaining is not detecting fabrication.

## Completion and formal-only diagnostic

Primary scores require the complete research-and-verification pipeline to succeed. The inner formal check is shown separately; it does not rescue a failed primary run.

| Workflow | Whole pipeline completed / 8 | Primary evidence-valid / 8 | Formal-only evidence-valid / 8 | Both loops executed / 8 |
| --- | ---: | ---: | ---: | ---: |
| Astra alone | 8/8 | 8/8 | 8/8 | 0/8 |
| Astra + updated harness | 2/8 | 2/8 | 6/8 | 4/8 |

### Displayed provenance in the updated harness

These counts use the active claim status after its observed-link check, not the nested trace's raw origin label. Located provenance remains a model-assisted source-path assessment; it does not authenticate experimental data.

| Case set | Original located | Partial | Unresolved | Unavailable |
| --- | ---: | ---: | ---: | ---: |
| Named (4) | 1 | 2 | 1 | 0 |
| Masked (4) | 1 | 2 | 1 | 0 |

## Model calls and tokens

Every logical invocation, including research and failed calls, is retained. A total stays unknown if any invocation lacks usage; the known portion is shown as a lower bound. Cached input is already included in input tokens. Tokens are not monetary cost, and the arms are not compute-matched.

| Scope | Workflow | Successful / all calls | Usage-known / all calls | Total tokens | Cached input tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| All 8 cases | Astra alone | 8/8 | 8/8 | 185,938 | 15,104 |
| All 8 cases | Astra + updated harness | 98/108 | 100/108 | unknown (known ≥ 1,553,444) | unknown |
| Named 4 cases | Astra alone | 4/4 | 4/4 | 93,116 | 7,552 |
| Named 4 cases | Astra + updated harness | 51/53 | 52/53 | unknown (known ≥ 805,794) | unknown |

### Phase usage

| Workflow | Phase | Calls | Total tokens | Share of arm tokens |
| --- | --- | ---: | ---: | ---: |
| Astra alone | direct | 8 | 185,938 | 100.0% |
| Astra + updated harness | research | 71 | unknown (known ≥ 948,527) | unknown |
| Astra + updated harness | formal | 37 | unknown (known ≥ 604,917) | unknown |

### Stage usage

| Workflow | Stage | Calls | Known input | Known output | Total tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| Astra alone | direct | 8 | 184,500 | 1,438 | 185,938 |
| Astra + updated harness | causal_dig | 8 | 111,835 | 1,472 | 113,307 |
| Astra + updated harness | decompose | 19 | 323,494 | 20,762 | unknown (known ≥ 344,256) |
| Astra + updated harness | deconstruct | 8 | 110,742 | 1,110 | 111,852 |
| Astra + updated harness | direct_response | 8 | 88,743 | 1,453 | unknown (known ≥ 90,196) |
| Astra + updated harness | grounding_check | 4 | 42,874 | 1,422 | unknown (known ≥ 44,296) |
| Astra + updated harness | perspective | 1 | 14,155 | 183 | 14,338 |
| Astra + updated harness | search_plan | 8 | 111,647 | 1,101 | 112,748 |
| Astra + updated harness | select | 6 | 57,849 | 393 | 58,242 |
| Astra + updated harness | source_trace | 12 | 167,107 | 4,285 | 171,392 |
| Astra + updated harness | source_verify | 7 | 85,286 | 1,650 | unknown (known ≥ 86,936) |
| Astra + updated harness | synthesis | 8 | 121,843 | 6,347 | 128,190 |
| Astra + updated harness | timeline_build | 7 | 72,875 | 2,397 | unknown (known ≥ 75,272) |
| Astra + updated harness | verify | 12 | 199,035 | 3,384 | 202,419 |

## What still fails

Formatting failure: h02 source_trace returned a valid outer response, but its result_json string was missing the final ]}. Parsing failed at character 567 after an otherwise completed 11-second call. newsverify/news_client.py:17 permits an arbitrary string; lines 149-155 validate the outer envelope and then parse the inner JSON. A future fix should enforce the stage-specific nested structure. This run was not repaired or rescored.

Execution failures: eight calls timed out at 90 seconds (h03: source_verify, timeline_build, direct_response; h06: decompose; h08: direct_response, decompose; h07: grounding_check, timeline_build). Two other turns failed or were incomplete (h05: source_trace; h07: direct_response), with usage retained. Six requested workflows therefore failed. The h06/h08 formal loops failed after earlier supported answers, so those earlier answers do not rescue completion. Remaining causal explanations for timeouts/incomplete turns are not established.

Research-to-verification handoff: with explicit claims, newsverify/news_tracing_runner.py:252 uses those fixed claims, and lines 288-295 send only the target, materials, initial source IDs and configuration into the formal loop. The research findings, gaps and timeline are not passed as advisory context. In this setup, added research cannot directly change the formal evidence or planning; it adds work and possible failures. The measured research and formal token subtotals are 948,527 and 604,917, respectively, with missing usage in both.

Evidence access and origin: newsverify/news_tracing_runner.py:79 collapses research snapshots sharing a URL; newsverify/news_client.py:67-77 exposes only each retained source's first 16,000 characters. All eight cases share URLs across excerpt/full-paper versions, so the targeted excerpt is not separately preserved for research; formal verification retains both versions. The two displayed original_material_located outcomes (h02/h04) are named/masked variants of one attribution control, not two independently authenticated experiments. No added fabrication detection was observed; the frozen packets lack independent laboratory records.


## Interpretation and verification

The research stages cannot add new raw evidence to the formal verifier in this experiment. Each pool contains a historical paper and an excerpt of that same paper, not independent corroboration. Research receives bounded prefixes and may collapse duplicate URLs; the direct arm receives the full pool. The installed model's prior knowledge is not erased, and masking does not prove temporal isolation of model weights.

This is a development comparison on two event families, not a general accuracy estimate. Internal CLI network retries are not independently counted. The separate transport-readiness probe is excluded from these receipts and totals.

The public check recomputes outcomes, denominators and token totals from categorical rows and receipts, verifies hashes, and checks the publication boundary. It cannot independently rescore private quotations or reproduce semantic judgments without the retained source packets and raw model outputs.

```sh
python3 experiments/historical-news-tracing-20260908/publish_report.py --verify --public-dir reports/historical-news-tracing-20260908
```

[Registered protocol](PROTOCOL.md) · [Summary and categorical rows](SUMMARY.json) · [Sanitized call receipts](SANITIZED_RECEIPTS.json) · [Registration](REGISTRATION.json) · [Hash manifest](MANIFEST.json)
