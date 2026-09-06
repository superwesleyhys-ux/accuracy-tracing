# Historical 2023 two-case pilot v3

This is a newly frozen, post-hoc correction of the two-case pilot. It selects
one true and one false proposition from the already frozen full
`historical-2023-resolved-by-2024-v1` corpus:

- `virgin-galactic-commercial-service-2023` (true)
- `lucid-production-2023` (false)

V1 and v2 remain unchanged for audit. Results from those versions must not be
pooled with v3 as though the v3 selection had been preregistered.

## Disclosed post-hoc benchmark correction

V3 replaces the Boeing proposition used by v1 and v2. The selected Boeing
outcome directly dated the crewed flight-test launch, but adjudicating whether
the test had been *completed* by an earlier deadline additionally required the
unstated prerequisite inference that completion cannot precede launch. That
inference is sensible, but it was not explicitly stated in the frozen evidence
and therefore made the case a poor test of evidence-grounded verification.

The replacement Lucid proposition has a direct numeric resolution: the 2023
claim said Lucid was on track to manufacture more than 10,000 vehicles, while
the official full-year result reports production of 8,428. No unstated event
prerequisite is needed to compare the target with the outcome evidence.

Lucid retains the full corpus's `full_evidence_control=true` diagnostic. The
runner therefore executes two main loop cases plus one Lucid control in each
arm (six case/variant/arm executions total). Only the two main loop cases enter
the paired accuracy result; the full-evidence run is reported separately.

Before any v3 model call, the Virgin outcome excerpt was expanded within the
same sentence of the same immutable SEC filing to retain the explicit `we` and
`our` issuer binding. Its proposition, source artifact, publication date, and
gold label are unchanged; the edit only removes reliance on a quoted flight
brand as an actor proxy.

Both propositions were published in 2023. All claim and outcome materials are
official SEC EDGAR records published and available no later than the fixed
`2024-12-31T23:59:59Z` cutoff. The Virgin proposition and source artifact are
unchanged from v1/v2, with the pre-run excerpt expansion disclosed above. The
Lucid case, including its full-evidence control flag, is copied from the full
eight-case corpus.

Gold remains in `gold.json`, which is unavailable to inference. Inference may
read only `inputs.json`, `sources.json`, and `freeze.json`. Honest 2026
`retrieved_at` capture timestamps are audit-only fields stripped from every
model payload; every other model-visible input string is rejected if it
contains an explicit year from 2025 onward.
