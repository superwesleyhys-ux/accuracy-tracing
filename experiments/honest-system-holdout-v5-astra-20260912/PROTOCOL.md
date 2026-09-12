# Preregistered Astra source-tracing system holdout v5

This is one fresh comparison round of an Astra original-model baseline with the
FactCircuit source-tracing harness. Both arms use `gpt-6-astra` through the
local Codex-login route at low reasoning, one call per case, no retries, and no
API key. Model subprocesses cannot use web search, tools, plugins, skills,
workspace files, or persistent memory.

## Fresh cases and sealed outcomes

Eight paper families unused by the earlier holdouts are frozen before
inference. Four received formal publisher retractions in 2025 or 2026 after
precise public traces already existed by 2024-12-31. Four controls have real
pre-cutoff publisher corrections with corrected representations or source data
and no retraction located through 2026-09-12. The model packets omit titles,
authors, DOI values, institutions, journals, URLs, and all post-cutoff outcomes.

`SOURCE_AUDIT.json` records only original and cutoff-eligible trace sources. The
later outcomes and labels live in a sealed file outside the repository during
inference; only its SHA-256 hash is registered. The gold file is revealed after
all 16 calls finish.

## What differs between arms

The direct arm receives four frozen passages summarizing the original article
record. The harness arm receives the same four passages plus two source-trace
passages public by the cutoff. This measures the complete tracing system, not a
same-evidence prompt-only ablation.

The v5 policy differs from v4. It constructs a claim-to-artifact matrix and
uses a counterfactual consistency check: it asks whether the same artifact can
legitimately carry every supplied experimental identity. It then tests whether
a dated correction replaces the affected representation or source data and
leaves no incompatible mapping unresolved.

## Fixed execution and scoring

- Four later-positive and four right-censored control cases.
- Fixed case order and alternating arm order.
- Failed or schema-invalid calls count as incorrect; no retries or fallbacks.
- Schema and runtime validator both permit one to six unique evidence IDs.
- Corpus, trace audit, prompts, schedule, scorer, model, thresholds, and sealed
  gold hash are committed and pushed before inference.
- Primary metric: balanced accuracy.
- The harness succeeds only if balanced accuracy is strictly greater than the
  direct arm, all 16 outputs are valid, and its measured input-plus-output token
  total is no more than twice the direct arm.

This eight-case benchmark is exploratory. It does not establish a stable
population estimate or prove the authenticity of right-censored controls.
