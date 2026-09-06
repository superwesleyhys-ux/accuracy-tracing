# Historical 2023 pilot v3: original vs PR1

## Result

On this frozen two-case pilot, the PR1 staged validation loop scored **2/2
(100%)**, while the original monolithic loop scored **1/2 (50%)**. The paired
difference is **+50 percentage points** for PR1. This is a descriptive smoke
test, not a population-level accuracy estimate.

| Metric | Original monolithic | PR1 staged | Difference |
| --- | ---: | ---: | ---: |
| Accuracy | 1/2 (50%) | 2/2 (100%) | +50 pp |
| True recall | 0/1 (0%) | 1/1 (100%) | +100 pp |
| False recall | 1/1 (100%) | 1/1 (100%) | 0 pp |
| Abstention rate | 1/2 (50%) | 0/2 (0%) | -50 pp |
| Main-case completion | 2/2 (100%) | 2/2 (100%) | 0 pp |

## Case-level comparison

| 2023 proposition | Gold | Original | PR1 | Outcome |
| --- | --- | --- | --- | --- |
| Virgin Galactic starts commercial service in Q2 2023 | true | unverifiable | true | PR1 correct; original abstained |
| Lucid manufactures more than 10,000 vehicles in 2023 | false | false | false | both correct |

The Virgin outcome is grounded in Virgin Galactic's February 2024 Form 10-K:
the filing says in the issuer's first person that its June 2023 Galactic 01
flight marked the start of its commercial service. The Lucid outcome is
grounded in the February 2024 full-year result of 8,428 vehicles, which is not
greater than 10,000.

## Main-case resource use

| Resource | Original monolithic | PR1 staged | PR1/original |
| --- | ---: | ---: | ---: |
| Model calls | 6 | 33 | 5.50x |
| Input tokens | 10,902 | 44,591 | 4.09x |
| Output tokens | 4,791 | 5,213 | 1.09x |
| Total tokens | 15,693 | 49,804 | 3.17x |
| Sum of case wall time | 98.05 s | 146.83 s | 1.50x |

PR1 improved the result on this pilot at a substantial call and input-token
cost. Both arms used `gpt-6-astra`, null/omitted reasoning effort, the same
`equal-v1` per-case caps, at most five rounds, and no response replay. Arms ran
sequentially in the fixed order original then PR1. The staged algorithm allows
one inner semantic repair while the monolithic algorithm allows none; this is
part of the compared designs. Because PR1 actually used much more computation,
the pilot does not isolate prompt structure from compute as the cause of the
accuracy difference.

## Separate full-evidence diagnostic

The Lucid `full_evidence_once` control is diagnostic and is excluded from the
two scored main cases. The original control completed and returned the correct
`false` decision. The PR1 control exhausted its one allowed semantic repair and
ended with `StagedSemanticError: conclusive probe cannot carry a stop reason`.
Consequently the overall run status is `has_errors`, even though all four
scored main-arm results completed and `scores.json` has status `scored`. This
control failure is evidence of remaining staged-path brittleness and must not
be hidden by the main accuracy result.

## Protocol and limits

- Both propositions were published in 2023 and had settled official outcomes
  by the fixed `2024-12-31T23:59:59Z` evidence cutoff.
- Gold labels were unavailable during inference and opened only by the scoring
  step after both arms finished.
- Every model request and recorded model output was checked for explicit years
  from 2025 onward; none was present. Honest 2026 retrieval timestamps were
  audit-only and stripped from model payloads.
- The run used clean committed code and frozen inputs at Git commit
  `c722888bb4be0c31caedf0de3654267e935eb064`.
- A present-day model's weights cannot be made to forget post-cutoff training
  knowledge, so this protocol isolates supplied evidence, not model memory.
- The v3 pair is retrospectively selected and disclosed as post-hoc. It must
  not be pooled with v1/v2 as if preregistered. Two cases are far too few for a
  general accuracy claim.

Machine-readable results are in `scores.json`; raw call, trace, retrieval,
configuration, status, and checksum artifacts are retained beside this file.
