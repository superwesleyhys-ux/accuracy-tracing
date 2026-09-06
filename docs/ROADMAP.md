# Roadmap

Milestones are ordered by evidence dependency, not promised dates. Version
0.3.0 establishes the public, reproducible research base; the next milestones
focus on independent data and fairer comparisons.

## 1. Reproducible open-source core — complete for 0.3.0

- MIT-licensed Python package with a standard-library core.
- Deterministic trace demo, evaluation CLI, typed adapters, and audit schemas.
- Immutable evidence versions, provenance paths, reanalysis, bounded feedback,
  and explicit termination reasons.
- Seven-stage optional semantic adapter with fail-closed Python assembly.
- CI across Python 3.11–3.13 and a release manifest covering tracked artifacts.

The release is complete as an inspectable research harness, not as a production
fact-checking service.

## 2. Connect one live provider

- Add an adapter with explicit query intent handling, timeouts, retry and spend
  limits, safe logging, and stable source identities.
- Support reproducible replay of permitted snapshots and distinguish snippets
  from full-page text.
- Test corrections, redirects, missing timestamps, URL revisions, syndication,
  rate limits, and partial outages.
- Keep provider credentials, private feeds, and licensed corpora outside public
  artifacts.

Done when an archived input reproduces the same core decision and live failures
produce a visible incomplete result rather than silent success.

## 3. Build a blind historical benchmark

Version 0.3.0 includes eight frozen 2023 propositions and a cutoff/gold-isolated
harness, but only two post-hoc cases have completed the published model
comparison. The next benchmark must:

- define claims, event groups, cutoffs, source rules, and annotation guidance
  before inference;
- separate development and test data by event and time;
- use independent reviewers and adjudication for disputed labels;
- retain corrections, inaccessible evidence, unresolved outcomes, and source
  lineage; and
- publish distributable evidence with enough provenance to reproduce the run.

Done when the held-out set and evaluation procedure are frozen before prompt,
threshold, or retrieval tuning.

## 4. Isolate where the loop helps

Compare monolithic and staged verification under multiple resource regimes:

- equal outer caps, matching the current harness;
- equal calls and equal total tokens;
- decomposition-only and critic-only ablations;
- single-pass versus continued retrieval using a shared first-round prefix; and
- source-complete controls that distinguish reasoning failures from missing
  evidence.

Report per-class counts, confidence intervals, abstention, failures, exclusions,
latency, and cost. A higher decision rate without adequate precision is not an
improvement.

Done when a preregistered held-out comparison identifies benefit, cost, and
failure cases without pooling exploratory pilots as confirmatory evidence.

## 5. Harden the experimental adapter

- Resolve the known full-evidence staged diagnostic failure.
- Expand multilingual, passive-voice, nominalization, numeric, temporal,
  negation, and multi-event red-team coverage.
- Add production concurrency, cancellation, network-failure, and long-run cost
  tests.
- Define stable installed entry points for the optional experimental runtime.

Done when failures are typed, reproducible, and recoverable across supported
providers and model transports.

## 6. Support real users

Use evidence from independent integrations to improve the contract and docs.
Track releases, issues, external contributions, and downstream use with public
links. Accuracy and ecosystem claims will be made only when backed by measured,
reviewable data.
