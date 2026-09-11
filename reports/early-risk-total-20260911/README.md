# INVALIDATED: local single-pass provenance-risk diagnostic

**Do not use this run as evidence that the harness detected fabrication in
advance.** A post-run audit found target leakage in the evaluation design: the
harness policy directly maps unauthenticated real-world provenance claims to
high risk, all four positive cases use that claim type, and all four controls
instead ask what a source reports. The test can be solved by distinguishing the
two claim types. It contains no nonfabricated real-world provenance controls.

The candidate separates cutoff fact verification from an early provenance-risk forecast.

| Measure | Direct Luna | Luna + single-pass harness | Goal |
|---|---:|---:|---:|
| Strict cutoff fact accuracy | 2/8 | 8/8 (100.0%) | ≥6/8 |
| Later-false cases identified early | 0/4¹ | 4/4 | 4/4 |
| Control cases flagged high risk | — | 0/4 | diagnostic |
| Model calls | 8 | 8 | ≤ one/case |
| Input + output tokens | 164,490 | 64,444 | ≤328,980 |
| Harness / direct token ratio | 1.00× | 0.39× | ≤2.00× |

**The numerical thresholds were reached, but the benchmark is invalid and the
registered detection goal is not established.**

¹ The direct baseline had no separate risk output. None of its cutoff fact verdicts identified the four later-false claims; the harness adds a dedicated predictive risk channel.

## Per-case results

| Case | Role | Fact expected | Fact result | Scope | Risk | Strict |
|---|---|---|---|---|---|---:|
| h01 | authenticity | unresolved | unresolved | real_world_provenance | high | yes |
| h02 | attribution_control | supported | supported | source_attribution | low | yes |
| h04 | attribution_control | supported | supported | source_attribution | low | yes |
| h03 | authenticity | unresolved | unresolved | real_world_provenance | high | yes |
| h05 | authenticity | unresolved | unresolved | real_world_provenance | high | yes |
| h06 | attribution_control | supported | supported | source_attribution | low | yes |
| h08 | attribution_control | supported | supported | source_attribution | low | yes |
| h07 | authenticity | unresolved | unresolved | real_world_provenance | high | yes |

## Interpretation

A high risk output records that a real-world provenance claim is supported only by the subject publication and lacks independent authentication in the bounded packet. It does not claim that pre-2024 evidence proved fabrication.

This is an in-sample diagnostic over two event families. The attribution
controls test whether the policy preserves literal report claims, but they do
not measure false-positive risk on genuine provenance claims. A valid
replacement must use unseen event families and same-task controls frozen before
inference.

## Reproducibility

The inference batch used the local Codex-login route with `gpt-5.6-luna` at low reasoning. API credentials were removed and no route fallback was allowed. The eight calls all completed in 50.0 seconds. Raw predictions SHA-256: `3aedf79cc69241daf12abd514225b9d45b40ef29dc2c05c46ba2b3e65eb3586e`; scored summary SHA-256 before publication: `747c0caa8c652d85af5dbfb936bc10769326b765a38f17675068a943d53e5abe`.
