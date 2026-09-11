# Historical harness prompt optimization

This is an iterative development experiment requested by the user. Its eight
historical cases have already been evaluated and inspected. They are development
and regression data, not an unseen test set. The four masked cases share the
same two event families as the four named cases.

## Fixed comparison

Every round pairs a fresh direct Astra call with the candidate news-tracing and
formal double-loop harness. Both use gpt-6-astra, medium reasoning, through the
local Codex-login HTTP route. Inference remains hosted. No API-key route or
fallback is permitted. Both receive the same eligible source versions and claim.
The evidence cutoff remains 2023-12-31T23:59:59Z. Live source collection is
disabled. Later gold outcomes, labels, reviews, plans, reports and the repository
are denied to the inference worker. A present-day model's memorized knowledge
cannot be erased; this is an evidence-cutoff test, not a training-cutoff claim.

Each model call has a 90-second timeout. Direct receives one call. The harness
receives at most 24 calls total, including at most 10 formal-loop calls. There
are no orchestration retries or selective reruns. All completed, failed and
incomplete calls are retained. Unknown token usage remains unknown. CLI-internal
retry behavior is not independently measured.

## Iteration and stopping rules

At most three development candidates may be tested. Each development round uses
h01, h02, h05 and h06, in that order, with conditions direct and news_tracing.
At least two rounds are intended unless a real transport or accounting blocker
prevents safe comparison. A candidate may change only after its preceding batch
has completed and been scored. Candidate changes must address observed DEV
failures or general evidence-processing deficiencies. No case-name rules,
future-outcome instructions, forced false verdicts, weaker quotation validation,
or removal of failed runs are allowed.

The selected candidate receives one final paired confirmation over h01 through
h08. This remains a development-data confirmation, including a sensitivity
check using masked variants; it is not independent family-level validation.
The chosen candidate is the one with most whole-pipeline-valid cutoff-correct
answers, then fewest unsupported definite answers, then fewer fully accounted
tokens. Missing token usage cannot establish a cost advantage. A round may be
stopped for an infrastructure failure, but its partial records remain reported
and cannot be replaced as if the attempt never occurred.

Before each inference batch, register hashes of the candidate executable
inventory, driver, scorer, protocol, round plan, unchanged corpus, unchanged
gold, helper and input/gold reviews. Freeze executable copies for that batch.
Scoring starts only after the planned inference batch ends and input/output
bindings are audited. The scorer then reads the committed gold.

## Outcomes and interpretation

The primary measure is exact cutoff verdict agreement with valid source evidence
and a valid whole pipeline. Formal-loop-only validity is a separate diagnostic.
Report future-false claims called false, left unresolved, accepted as true,
called conflicting, or invalid separately. Abstaining is not detecting
fabrication. Matching future labels without sufficient eligible evidence is not
a justified advance detection. A paper being the original report does not prove
its reported measurements are authentic.

Report every attempted call, execution status, known input/output/cached tokens,
unknown usage count, and research/formal stage totals. Fully accounted total
tokens include failed attempts. Do not report an exact speed advantage when
elapsed clocks disagree. Preserve the earlier reports unchanged and compare
candidate changes against both a fresh paired baseline and the previous harness.

The existing direct baseline scored 8/8 valid cutoff-correct answers. It is
mathematically impossible to exceed its accuracy on these eight cases. Equal
valid accuracy with at least 20% fewer fully accounted total tokens would be a
prespecified efficiency improvement on DEV only, not an accuracy win. Improved
completion or reduced cost versus the previous harness is separately useful.
An accuracy-superiority claim requires genuinely new event families with
pre-2024 evidence and first relevant public fabrication findings in 2025–2026,
frozen before exposure to their outcomes. Independent screening currently has
zero eligible new families; do not substitute ineligible cases to manufacture
a win. If neither criterion is achieved, explicitly report that the harness
has not exceeded Astra.

## Candidate 1 rationale

Replace research-stage JSON-inside-string envelopes with native bounded schemas;
retain every eligible source version in fairly allocated, explicit excerpts;
pass bounded research findings/questions to formal stages as untrusted advice,
never accepted evidence; remove duplicate full-text transmission of the current
material in decomposition; directly visit a sole eligible same-URL version
without a model selection call; and request concise, claim-focused annotations
and evidence-driven revisits. Preserve full formal source texts, exact quote
validation, temporal eligibility and strict whole-pipeline failure accounting.
