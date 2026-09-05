# Roadmap

Milestones are ordered by dependency, not promised dates. The current deliverable is an offline starter prepared for public release.

## 1. Publish a reproducible starter

- Review the package, MIT license, deterministic demo, tests, and adapter contract.
- Publish a public repository and tagged release with exact reproduction commands.
- Record known limitations prominently: trusted stance labels, supplied lineage, no live retrieval, and synthetic evaluation only.

Done when a new contributor can reproduce the demo and inspect why each fixture received its outcome.

## 2. Connect one live provider

- Inspect the actual earlier tracker before writing its integration.
- Add one adapter with explicit query intent handling, timeouts, rate limits, retry caps, spend limits, and safe logging.
- Capture retrieval timestamps, original publication times, publisher identifiers, origin identifiers, and retrieval failures.
- Support reproducible replay of permitted snapshots. Document how snippets differ from full-page text.
- Test corrections, redirects, missing timestamps, updates to an existing URL, and syndicated reports.

Done when the same archived input reproduces the same core decision and live failures produce a visible incomplete result.

## 3. Build a blind news benchmark

- Define atomic claims, event identifiers, claim cutoffs, inclusion criteria, and an annotation guide before collecting results.
- Separate development and test cases by event and time. Keep duplicate, syndicated, and follow-up coverage together to prevent leakage.
- Ask independent reviewers with relevant expertise to label claim status and evidence stance as of each cutoff, with adjudication for disagreements.
- Retain source lineage, corrections, retractions, inaccessible documents, and unresolved claims. Version labels when later facts change; preserve the original cutoff-based evaluation.
- Use distributable material and publish provenance and retrieval metadata sufficient to reproduce the experiment.

Done when a held-out set and its evaluation procedure are fixed before thresholds or retrieval strategies are tuned on it.

## 4. Test whether the loop helps

Compare a single-pass baseline with the bounded loop using the same provider, claim set, time cutoff, document budget, and scoring rules. For model-backed adapters, also match or explicitly report token and monetary budgets. Share configurations and all exclusions.

Measure more than overall agreement:

| Metric | Question it answers |
| --- | --- |
| Precision of supported/contradicted decisions | How often are committed decisions right against the held-out labels? |
| Decision coverage and unresolved rate | How often does the system decide or abstain? |
| Contradiction and conflict recall | How often does it find known contrary evidence? |
| Citation and entailment validity | Do references exist, and do reviewed passages justify the assigned stance? |
| Lineage and duplicate errors | Does shared reporting falsely count as independent evidence? |
| Time-cutoff leakage | Was any evidence unavailable at the evaluated time? |
| Retrieval, latency, and cost | What does each incremental decision cost? |

Report per-class sample counts, confidence intervals, and representative failures. A higher decision rate without adequate precision is not an improvement. Confidence scores should not be introduced until they can be calibrated and evaluated separately from policy labels.

Done when an equal-budget ablation reports the loop's measured benefit or lack of benefit without hiding difficult or unresolved cases.

## 5. Support real users

Use feedback from independent integrators to improve the contract and failure handling. Track actual releases, issues resolved, external contributions, and downstream uses with public links. Apply for maintainer support using that evidence; the project should remain useful regardless of an application's outcome.
