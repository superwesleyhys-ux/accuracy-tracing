# Offline mixed-truth scoring preparation

This standalone component scores **declarations of already-audited outcomes**. It does not read files, sources or gold, call a model, run a benchmark, verify requests, establish source admission, or prove isolation. The tests use completely fictional IDs and labels. No real control or false-case source values were consulted.

The files remain preparation for independent review. Integration into a future runner, case admission, registration and inference are separate steps. In particular, a true control without an independently admitted false case does not authorize a mixed holdout.

Run the fictional checks from the repository root:

```sh
python3 -B -m unittest discover -s experiments/prompt-iteration-20260909/mixed-eval-preparation -p test_scoring.py -v
```

Call `score(plan, outcomes, labels, batch_status="completed")`. All objects have exact fields; extra fields reject. Invalid contracts raise `ValueError`. `batch_status` is mandatory. Inputs are not modified, and no token accounting is performed.

| Input | Exact contract |
|---|---|
| `plan` | `schema_version: 1` as an integer, `case_ids` containing exactly two distinct opaque strings, `conditions: ["direct", "news_tracing"]`, and `arm_order: "alternating"` as a plain string. |
| `labels` | `schema_version: 1` and `cases`, with exactly one label per planned ID in plan order. Each label has `case_id`, `assertion_scope`, `cutoff_expected`, `future_expected`, and `independently_adjudicated`. |
| Label scope | `assertion_scope` is `real_world` or `attribution`. `cutoff_expected` is `supported`, `contradicted`, `unresolved`, or `conflicting`. `future_expected` is a settled `supported` or `contradicted`. `independently_adjudicated` must be the boolean `true`. |
| `outcomes` | Exactly four rows: first ID direct/harness, second ID harness/direct. Each row has `case_id`, `condition`, `execution_status`, `audit_passed`, `pipeline_valid`, `formal_valid`, `observed_verdict`, and `formal_verdict`. |
| Row status | `execution_status` is `completed`, `failed`, or `unexecuted`. `audit_passed` must be boolean `true`; both validity fields must be actual booleans. A verdict is one of the four allowed verdict strings, or `null` when no verdict is retained. |
| Batch status | Exactly `completed` or `fatal_worker_failure`. Missing, duplicate, unknown or reordered rows always reject, including for a fatal batch. |

The labels belong exclusively to the scorer. A boolean adjudication or audit declaration is not evidence that review happened. A future integration must independently bind reviewed claims, scope, canonical evidence, private gold and actual request audits to registered commitments. This module only checks the shape and consistency of the declarations. It permits different truth-stratum compositions for testing; it does not enforce or certify admission of a one-true/one-false holdout.

A primary-valid row must have completed processing, a valid formal result, and equal non-null observed/formal verdicts. Any unequal non-null observed/formal verdicts reject, even on an invalid pipeline. A valid formal result needs a formal verdict. Invalid rows may retain known verdicts, but cannot earn primary correctness or detection credit. For a direct row, the formal fields describe the same audited direct verdict; for a harness row, they describe its final formal verification.

`completed` at the batch level means the batch finished recording all planned rows; ordinary recorded failures remain in the denominator. A row can complete processing while failing evidence validation. A failed research stage followed by a valid formal answer has `execution_status="failed"`, `pipeline_valid=false` and `formal_valid=true`: its formal correctness remains a diagnostic, while its primary row counts as failed/invalid.

`fatal_worker_failure` makes `primary_comparison_available=false`. Every primary aggregate, rate and truth-stratum metric is `null`/unavailable, even if some recorded rows were valid. All four rows, planned denominators, execution counts and observed/formal diagnostics remain present. Explicit `unexecuted` rows are permitted only for fatal batches, and require both validity flags false and both verdicts null. The caller must audit that they were unexecuted; the module never fabricates missing rows. Row match flags and `recorded_*` counts in a fatal batch are diagnostics, not a completed primary comparison.

The output separates three strata:

- `real_world_false`: an independently declared false real-world claim. Only a valid contradicted verdict counts as `called_false`; valid support counts as `false_acceptances`. `cutoff_grounded_false_calls` additionally requires contradicted cutoff gold. A correct future-false call against unresolved cutoff gold therefore does not earn cutoff agreement or a grounded-false-call count.
- `real_world_true`: an independently declared true real-world claim. Valid support counts as `true_acceptances`; a valid contradicted verdict counts as `false_accusations` and never as false-case detection.
- `attribution`: a proposition about what a source states. Support or contradiction is tracked in its own stratum, with no real-world false-detection or false-acceptance credit.

Each stratum separately retains abstention, conflict and failed/invalid outcomes. An abstention is never detection. Cutoff matches and future matches have distinct counts and rates; empty strata have null rates rather than zero-denominator scores. `row_settled_cutoff_mismatch` and `recorded_settled_cutoff_mismatches` identify primary-valid supported/contradicted predictions that disagree with cutoff gold, in both truth strata and attribution. A `conflicting` verdict is not a settled assertion. These are cutoff-label mismatch diagnostics, not independent semantic proof that a statement lacks support.

Token usage is deliberately outside this contract. Token/usage fields on rows reject; nothing here converts unknown usage into zero or estimates spend. Future integration must retain the existing independent receipt accounting. There is no winner, superiority claim, source quote, model rationale or automatic selection of another experiment in this output.

The fictional tests cover false accusations on true claims; false acceptance; failed research with correct formal verification; future-false guesses without cutoff support; abstention and conflict; attribution boundaries; fatal/incomplete batches; malformed and contradictory flags; exact order and scope; unknown/extra fields; and strict boolean-versus-integer validation. They validate this component's accounting only, not factual accuracy or the readiness of any real holdout.
