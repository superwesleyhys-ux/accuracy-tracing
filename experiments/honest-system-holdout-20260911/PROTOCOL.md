# Preregistered source-tracing system holdout

This experiment compares an original-model baseline with the FactCircuit
source-tracing harness. Both arms use the same `gpt-5.6-luna` model through the
local Codex-login route at low reasoning, one call per case, no retries, and no
API key. Model subprocesses cannot use web search, tools, plugins, skills, files,
or persistent memory.

## What differs between the arms

The direct arm receives a frozen, anonymized summary of the original article
record. The harness arm receives the same base record plus frozen trace findings
that FactCircuit located in sources already public by 2024-12-31. This is a
system comparison of original model versus model plus source tracing. It is not
a same-evidence prompt-only comparison; the earlier prompt-only holdout remains
reported separately.

The harness trace can add a dated correction, expression of concern,
post-publication review, source-data record, or independent replication record.
It cannot add a retraction, investigation, or any fact first published after the
cutoff. Full titles, authors, DOI values, institutions, journals, URLs, and later
outcomes are audit metadata and are never sent to either model.

## Cases and labels

Eight previously unused paper families are frozen before inference. Four papers
were retracted in 2025-2026 after publisher findings involving image duplication
or reuse. Each of those four already had a specific public trace before the
cutoff. Four domain-matched controls have durable data records or independent
cohort checks, and no retraction was located through 2026-09-11.

`elevated` is a prospective follow-up label, not a claim of misconduct. The
later publisher outcome is held in a sealed gold file and revealed only after
both arms finish. A control label is right-censored absence of a located
retraction, not proof that every claim is correct.

## Fixed design

- One frozen packet per arm and case; direct always has four passages and the
  harness always has the same four plus two trace passages.
- Fixed case order and alternating arm order.
- Specific, dated cross-condition image duplication or reuse is sufficient for
  an elevated screening result.
- A routine metadata correction, scholarly disagreement, missing replication,
  or missing raw data without a specific anomaly is ordinary.
- Failed or invalid calls count as incorrect. There are no retries.
- Packets, prompts, scorer, schedule, model, thresholds, and the sealed-gold
  hash are committed before inference.

## Registered metrics

The primary metric is balanced accuracy over four later-positive and four
control papers. Secondary metrics are accuracy, sensitivity, specificity,
valid-output completion, and measured input-plus-output tokens. The harness
succeeds only if its balanced accuracy is strictly greater than the direct arm,
all 16 calls complete with valid outputs, and harness tokens are no more than
twice direct tokens.

This is a small exploratory benchmark. The paired cases test whether the added
source-tracing stage helps this particular historical-screening task; they do
not estimate broad real-world prevalence or prove statistical significance.
