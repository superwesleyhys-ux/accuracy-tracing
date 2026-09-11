# Historical comparison with the updated news-tracing harness

This is a fresh experiment on the same eight historical cases shown in
`reports/historical-evaluation-20260908/README.md`. Earlier results, corpus,
gold, and registered scoring artifacts remain unchanged. The new treatment
is the updated news-tracing workflow, followed by its per-claim double loop.
It is not an exact rerun of the older double-loop-only treatment.

## Fixed evidence and outcomes

Reuse the original corpus bytes and the independently reviewed source-version
availability records. All case cutoffs are 2023-12-31T23:59:59Z. Four named
cases are the primary analysis; four identity-masked derivatives are a separate
sensitivity analysis. These eight cases represent two research-event families,
not eight independent events.

The registered 2025 findings are used only by the separate post-run evaluator.
Inference receives no future sources, labels, selection rationale, blinding map,
earlier results, or private review documents. Each allowed pool contains the
historical paper text and an excerpt from that same paper; they are not
independent corroboration. No additional live article or source can be admitted.
Publication dates alone do not establish historical availability. The original
dataset's exact-version availability review is reused without modification.

## Conditions and budgets

Both conditions use GPT-6 Astra, medium reasoning, local Codex login through
the same explicit HTTP profile, and a 90-second deadline per model invocation.
Both get the same historical evidence contract and explicit historical target
context on every call. Model tools and installed skill catalogs remain disabled.

- `direct`: one model call with the entire allowed source pool.
- `news_tracing`: the active imported research stages, followed by the active
  per-claim double loop. There is one explicit claim per case, identical to the
  registered target; generated claims cannot replace it. The case cutoff,
  source-version anchor and all material bytes remain fixed. Research depth is
  1, with at most two planned search angles. Search stays inside the supplied
  snapshot pool; live search and live origin-link discovery are disabled.
  The formal double loop retains its ten-call allowance. All research and formal
  stages share a **24-call per-case cap**, including failed invocations.

The active research adapter exposes at most the first 16,000 characters of each
retained URL and 60,000 characters overall, with explicit excerpt markers. For
these same-URL excerpt/full-paper versions, research retains the last version
for that URL. The direct condition gets the full allowed pool; the formal double
loop can also inspect full selected versions. These are the implementation's
actual access differences, not additional independent sources.

The updated treatment's 24-call cap differs from the previous treatment's
ten-call cap, because it includes additional research stages. Tokens are not
equalized. The report must show total usage and stage-level usage, retaining
unknown usage as unknown. This is a comparison of two workflows under declared
limits, not an equal-compute experiment.

All sixteen runs are scheduled once. Cases run sequentially, with condition
order alternating by case. No selective rerun, retry of failed logical calls,
API fallback or data repair is allowed within this batch. Internal CLI network
retries are not counted separately. A synthetic transport-readiness call is
recorded separately and is not a benchmark result.

## Isolation and registration

Before any benchmark inference, bind the corpus, unchanged gold, scoring helper,
input review, gold review, new driver and new scorer with a timestamped hash
registration. The inference supervisor validates only metadata and permitted
input hashes. It never loads future gold. It freezes all required executable
code and copies only that code and the allowed corpus into a temporary worker.

The worker must verify that the original repository, corpus directory and
registration files cannot be read under macOS filesystem isolation. It receives
no protocol narrative, scorer, gold, previous outputs or research notes. No
unsandboxed fallback is permitted. The new output directory must not already
exist. Exact inputs, outputs, receipts, errors and code hashes are retained.

The installed model's prior knowledge cannot be erased by these controls.
Named and masked results therefore do not prove a clean training-data cutoff.
Every research stage must still receive the actual cutoff; a generic instruction
to obey an unspecified cutoff is insufficient.

## Scoring and interpretation

Score only after inference finishes, against the original registered labels.
Check successful final output, exact quotations, source identity, target identity,
cutoff admission, actual stage receipts and all scheduled denominators. Keep
research-stage errors as pipeline failures; a failed or invalid run receives no
successful-abstention credit. Retain unsupported certainty and conflict outcomes
separately from supported detection and abstention.

Report named and masked results separately: authenticity claims called false,
left unresolved, accepted as true, conflicting, failed or invalid; attribution
control matches; actual loop execution; calls and measured token usage. Calling
a later-false claim false without adequate cutoff evidence is not evidence of
successful advance fabrication detection. Abstaining is not detecting fraud.

The news-research stages produce explicitly unverified analysis. With these
fixed explicit targets and frozen pools, they do not feed new evidence into the
formal verifier. Tracing to an original paper cannot establish the authenticity
of that paper's experiments. Missing laboratory records, unavailable figure
sheets and text-only image limitations remain the original dataset's limits.
Public reports contain categorical outcomes, accounting and source metadata;
full source passages, prompts and raw model outputs remain local.
