# Early provenance-risk comparison protocol

This development test uses the unchanged eight-case historical corpus with an
evidence cutoff of 2023-12-31. It compares a new single-pass local harness with
the already recorded local Luna direct baseline. The direct arm is not rerun:
its immutable prior receipt is reused so an unchanged policy does not consume
another model batch.

The inference process may read the corpus but not the later-outcome gold file.
It uses the local Codex-login tunnel, disables API credentials, tools, web,
plugins, skills and fallback, and makes exactly one logical model call per case.
Only the origin excerpt and eligible source inventory enter the model packet.

The harness returns two separate decisions. `fact_verdict` judges what the
pre-2024 evidence establishes. `fraud_risk` predicts whether a real-world data
provenance claim lacks independent authentication. A risk flag cannot turn an
unresolved factual claim into a contradiction.

The registered pass conditions are all of:

- at least 6/8 strict, evidence-valid cutoff factual answers (75%);
- high risk on 4/4 claims later shown fabricated;
- no more than 328,980 fully accounted input-plus-output tokens, twice the
  recorded 164,490-token direct baseline.

The four later-false cases and their four controls cover only two event
families and were previously inspected during development. This is an in-sample
development result, not independent evidence that the risk policy generalizes.
