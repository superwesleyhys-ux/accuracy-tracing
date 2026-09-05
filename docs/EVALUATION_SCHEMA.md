# Evaluation schema v1

`evaluate(gold, predictions)` accepts JSON dictionaries. The scorer has no access to model prompts and never generates gold labels. See `examples/evaluation_gold.json` and `examples/evaluation_predictions.json` for complete working input.

## Gold

Top-level `schema_version: 1`, `dataset_kind: synthetic | reviewed`, nonempty `cases` array. The `reviewed` label is a dataset owner's declaration, not an authentication mechanism.

Each case contains:

- `id`: fixed target identifier, unique across cases.
- `event_id`: group for event-level resampling and splitting.
- `as_of`: timezone-aware ISO cutoff, exactly matched in predictions.
- `truth`: `true`, `false`, `disputed` or `unverifiable`, adjudicated at cutoff.
- `high_risk`: boolean assigned before looking at predictions.
- `source.traceable`: whether the benchmark can establish an original-source answer at cutoff.
- `source.acceptable_root_sets`: list of nonempty alternative acceptable root ID sets, or empty for untraceable cases. A multi-root set requires all its members. Root IDs refer to adjudicated material versions, not mutable URLs.
- `source.valid_edges`: dictionaries with `from`, `to`, `relation`. Direction is target/downstream to upstream. Each acceptable root must be reachable from the case ID in this graph.
- `evidence`: dictionaries with unique per-target `id`, adjudicated `stance` (`supports`, `contradicts`, `neutral`) and nonempty `origin` group. All candidate evidence that a scored run emits must be adjudicated in this universe.

Allowed provenance relations are `cites`, `quotes`, `derived_from`, `translated_from`, `revised_from`. Semantic `supports` is not a provenance relation. Stance measures what evidence states relative to the claim; text can support a false claim without becoming reliable proof of truth. Truth labels are adjudicated separately.

## Predictions

Top-level `schema_version: 1`, `cases` with exactly the same IDs as gold. Each case contains:

- `id`, `as_of` as above.
- `decision`: one of the four labels. Only `true` is admission to the trusted feed.
- `probabilities`: optional/null, or exactly all four labels with finite numeric values in [0,1] summing to 1. The scorer does not synthesize these from verdicts. Probability quality and final policy decisions are measured separately.
- `source.status`: `resolved`, `earliest_accessible`, `unresolved`.
- `source.roots`: confirmed original root IDs only for `resolved`; otherwise empty. Candidate or earliest URLs belong in a separate investigation report, not this confirmed-root field.
- `source.edges`: claimed established provenance edges using the same schema as gold. Duplicates are invalid. Extra unsupported edges penalize source correctness even if one valid route exists.
- `evidence`: same shape as gold evidence, containing the system's stance and origin clustering. Group names may differ from gold; pairwise membership is scored.

For SR, a root must match an acceptable set and have a valid predicted path. Returned roots are not considered correct merely because an ID happens to match. All fixed traceable targets stay in SR's denominator; omissions become misses rather than disappearing. Unknown evidence IDs invalidate scoring until adjudicated. This is a closed, pre-adjudicated evaluation universe; open-web deployment needs an adjudication update process.

## Comparison-only run and usage metadata

Both prediction files additionally require:

```json
{
  "run": {
    "name": "redecomposition",
    "model_id": "exact-model-and-prompt-version",
    "corpus_id": "exact-material-snapshot",
    "per_target_budget": {
      "retrieval_calls": 3,
      "model_tokens": 1000,
      "wall_seconds": 60
    }
  }
}
```

Every case requires a `usage` object with those same three resource keys. Counts are nonnegative, finite and cannot exceed the per-target ceiling. Call/token counts must be integers. Model, corpus and ceilings must match between runs. These are supplied execution records; validation cannot independently prove external usage.

## Outputs

All ratio metrics include numerator, denominator and a 95% Wilson reference interval. Zero denominators return `null`. Main CA and ECE require probabilities for every target. Any missing main metric makes the experimental aggregate `null`; weights are not renormalized.

`compare` resamples whole event groups jointly for both systems, reassigning cloned target IDs and graph anchors to preserve fixed-case semantics in each draw. Intervals are exploratory percentile intervals. If any draw makes a metric undefined, that interval is unavailable and valid draw counts are reported. With one event, all cluster intervals are unavailable. Do not interpret these intervals as simultaneous proof that seven endpoints improved.
