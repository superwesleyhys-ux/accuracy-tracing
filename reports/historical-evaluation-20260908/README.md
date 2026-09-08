# Historical evidence test: Astra and the harness

Of the **two named authenticity claims later shown to involve fabrication**, Astra alone called 0 false, abstained on 2, and accepted 0 as true. Astra with the harness called 0 false, abstained on 2, and accepted 0 as true. Conflicts and failed or invalid outcomes are retained separately below.

**Refusing to endorse a claim is not detecting fabrication in advance.** The pre-2024 packets lack independent laboratory records. A rejection that matches later findings can also lack support at the historical cutoff.

Eight cases cover two real research events. Four named cases are the primary comparison; four identity-masked derivatives are a separate sensitivity check. Both arms use the same Astra model through local Codex login, with medium reasoning. Local refers to the CLI route: model inference remains remote. Installed skill catalogs are disabled in both arms; normal Codex instructions remain.

For the fully measured four named cases, Astra alone used **92,818 tokens** and the harness used **363,147 tokens — 3.91× as many**. No additional fabrication-detection benefit was observed in these named cases.

## Named cases: primary analysis

| Measure | Astra alone | Astra + harness |
|---|---:|---:|
| Later-false authenticity claims called false | 0/2 | 0/2 |
| Authenticity claims left unresolved | 2/2 | 2/2 |
| Later-false authenticity claims accepted | 0/2 | 0/2 |
| Unsupported supported/contradicted answers | 0/2 | 0/2 |
| Unsupported conflict answers | 0/2 | 0/2 |
| Authenticity outcomes failed or invalid | 0/2 | 0/2 |
| Completed runs | 4/4 | 4/4 |
| Evidence-valid runs | 4/4 | 4/4 |
| Failed or invalid outcomes | 0/4 | 0/4 |
| Matches to cutoff-evidence labels | 4/4 | 4/4 |
| True attribution controls matched | 2/2 | 2/2 |
| Both loops executed, local audit | 0/4 | 2/4 |
| Logical attempts, including failures | 4 | 20 |
| Known total tokens | 92818 | 363147 |
| Calls with known input/output usage | 4 | 20 |
| Run errors | 0 | 0 |
| Timeout errors | 0 | 0 |
| Timing discrepancy flags | 0 | 0 |

## Masked cases: sensitivity analysis

| Measure | Astra alone | Astra + harness |
|---|---:|---:|
| Later-false authenticity claims called false | 0/2 | 0/2 |
| Authenticity claims left unresolved | 1/2 | 1/2 |
| Later-false authenticity claims accepted | 0/2 | 0/2 |
| Unsupported supported/contradicted answers | 0/2 | 0/2 |
| Unsupported conflict answers | 0/2 | 0/2 |
| Authenticity outcomes failed or invalid | 1/2 | 1/2 |
| Completed runs | 3/4 | 3/4 |
| Evidence-valid runs | 3/4 | 3/4 |
| Failed or invalid outcomes | 1/4 | 1/4 |
| Matches to cutoff-evidence labels | 3/4 | 3/4 |
| True attribution controls matched | 2/2 | 2/2 |
| Both loops executed, local audit | 0/4 | 1/4 |
| Logical attempts, including failures | 4 | 20 |
| Known total tokens | 71841 | 333730 |
| Calls with known input/output usage | 3 | 19 |
| Run errors | 1 | 1 |
| Timeout errors | 1 | 1 |
| Timing discrepancy flags | 1 | 1 |

The batch retained **2 timeout errors**: h07 / Astra + harness (failed verify call 6); h07 / Astra alone (failed direct call 1). The failed harness result's visible unresolved status is not counted as a successful abstention.

Across all eight cases, known usage is **164,659 tokens for Astra alone** and **696,877 for the harness**. These are lower bounds: timed-out calls have unknown usage, so both aggregate total-token fields remain null. No all-case token ratio is reported; the comparison above uses the fully known named-case totals.

The timing audit flags wall-clock/monotonic discrepancies in 2 runs. Those flags are retained; no end-to-end latency advantage is inferred from these measurements.

The registered broad year screen for h06 / double_loop flagged 2068. Local inspection identifies this as a citation offset rather than later-year prose. The raw screen flag remains unchanged; this annotation is a post-run clarification, not proof that learned knowledge was absent.

## What the cases test

The Osaka authenticity target asks whether the immunoblots in Figures 5B–5D came from the samples and experimental conditions stated in the caption. Its control asks whether that caption describes the blots as representing two independent experiments. The [2023 article](https://doi.org/10.1073/pnas.2308260120) supplies the historical text. The [2025 institutional investigation](https://www.osaka-u.ac.jp/ja/news/topics/2025/02/files/4h3a9t/@@download/file) identifies those panels as fabricated using different samples; the [paper retraction](https://doi.org/10.1073/pnas.2501149122) is additional later evidence. This does not establish that the biological mechanism itself is false.

The wastewater authenticity target asks whether all reported measurements came from the study's stated sampling and analysis procedures. Its control asks whether the abstract reports final-effluent colloidal fractions of 52% Cu, 32% Pb, 44% Ni and 68% Zn. The [2017 article](https://doi.org/10.1016/j.chemosphere.2017.02.034) supplies the historical text. The [publisher notice](https://www.sciencedirect.com/science/article/abs/pii/S0045653517302126) records the first author's fabrication admission, with a [separate 2025 retraction notice](https://doi.org/10.1016/j.chemosphere.2025.144440). This contradicts the universal authenticity claim, without establishing that every value or environmental conclusion is false.

## Tokens by recorded stage

| Arm | Stage | Attempts | Calls with known usage | Known input tokens | Known output tokens | Known total tokens |
|---|---|---:|---:|---:|---:|---:|
| Astra alone | direct | 8 | 7 | 163418 | 1241 | 164659 |
| Astra + harness | decompose | 20 | 20 | 391828 | 23498 | 415326 |
| Astra + harness | select | 6 | 6 | 57386 | 404 | 57790 |
| Astra + harness | verify | 14 | 13 | 220231 | 3530 | 223761 |

Stage accounting includes all eight cases and every recorded attempt. Decomposition and verification stages are shown separately; a stage's token cost does not establish the benefit of a loop. The loop counts above come from the local operation-history audit, which cannot be reproduced from source-free receipts alone.

A cutoff match answers what the supplied evidence established by 2023-12-31. Later-world agreement is a separate descriptive measure. **Abstention is not preemptive detection of fabrication.** A later-correct rejection can still be unsupported by the historical packet. Failed or invalid runs receive no successful-abstention credit and remain in every scheduled denominator.

The authenticity targets are curator formulations of implied data-authenticity claims. The controls ask what the papers reported; they are not controls establishing genuine experimental data. Both event families were selected using later fabrication findings. Two correlated event families cannot establish general accuracy or fraud-detection superiority.

Each finite source pool consists of extracted text from a retained historical PDF and an excerpt from that same text, not two independent sources. Astra alone receives the entire allowed pool immediately; the harness starts from the excerpt and retrieves from that pool. The wastewater packet contains all extracted text from the retained 18-page accepted-manuscript PDF, which ends in references; referenced table and figure sheets are absent from the text packet. This limitation is retained with the registered results, without rerunning or changing their labels. Calls and tokens are not equalized. Every logical attempt, including failed calls and available usage, is retained; internal CLI transport retries are not separately counted.

This text-only test does not assess image forensics. Identity masking cannot erase learned knowledge; absence of an explicit future-year reference cannot prove that pretrained knowledge was unused. The primary metadata and held-out 2025 findings are listed in [SOURCES.json](SOURCES.json). Exact earliest public disclosure for the wastewater finding is uncertain, and the Osaka investigation began privately in 2024.

[RESULTS.json](RESULTS.json) contains the sixteen categorical/numeric run rows and scores. [RECEIPTS.json](RECEIPTS.json) preserves all call accounting. [MANIFEST.json](MANIFEST.json) binds the public files and source archive hashes. No source passages, model rationale, prompts, raw responses or local/session identifiers are included. Source and response hashes cannot independently establish semantic entailment or the locally audited quote/loop claims.

From a fresh public checkout:

```sh
python3 tools/export_historical_evaluation.py --verify-public
```

This verifies hashes, all eight-by-two scheduled outcomes, row flags, error/call denominators and token totals without private artifacts or model calls. It does not rerun inference or independently verify the omitted source text.
