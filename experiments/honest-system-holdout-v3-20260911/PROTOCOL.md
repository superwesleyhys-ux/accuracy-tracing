# Preregistered source-tracing system holdout v3

This is a fresh system-level comparison of an original-model baseline with the
FactCircuit source-tracing harness. Both arms use `gpt-5.6-luna` through the
local Codex-login route at low reasoning, one call per case, no retries, and no
API key. Model subprocesses cannot use web search, tools, plugins, skills,
workspace files, or persistent memory.

## Fresh cases and sealed outcomes

Eight paper families unused by the earlier holdouts are frozen before
inference. Four received formal publisher retractions in 2025–2026 after
specific public traces already existed by 2024-12-31. Four controls have real
pre-cutoff correction or source-data traces and no retraction located through
2026-09-11. The model packets omit titles, authors, DOI values, institutions,
journals, URLs, and all post-cutoff outcomes.

`SOURCE_AUDIT.json` records only original and cutoff-eligible trace sources. The
later outcomes and labels live in a sealed file outside the repository during
inference; only its SHA-256 hash is registered. The gold file is revealed after
all 16 calls finish.

## What differs between arms

The direct arm receives four frozen passages summarizing the original article
record. The harness arm receives the same four passages plus two frozen source
trace passages already public by the cutoff. This measures the full tracing
system, not a same-evidence prompt-only ablation.

The v3 policy is new. It checks identity linkage, cutoff eligibility,
representation conflict, independent resolution, and severity. It distinguishes
an unresolved exact mapping across incompatible labels from a corrected error
whose underlying record is available and reconciled.

## Fixed execution and scoring

- Four later-positive and four right-censored control cases.
- Fixed case order and alternating arm order.
- Failed or schema-invalid calls count as incorrect; no retries or fallbacks.
- Corpus, trace audit, prompts, schedule, scorer, model, thresholds, and sealed
  gold hash are committed and pushed before inference.
- Primary metric: balanced accuracy.
- The harness succeeds only if balanced accuracy is strictly greater than the
  direct arm, all 16 outputs are valid, and its measured input-plus-output token
  total is no more than twice the direct arm.

This small exploratory benchmark tests whether the added source-tracing stage
helps this historical screening task. It does not establish population-level
performance or statistical significance.
