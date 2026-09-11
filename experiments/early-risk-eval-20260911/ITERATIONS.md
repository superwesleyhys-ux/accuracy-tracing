# Strategy iteration ledger

## Iteration 0 — existing multiphase news-tracing harness

- Model/route: `gpt-5.6-luna`, low reasoning, local Codex login.
- Result: 1/8 strict cutoff-correct, 0/4 later-false detections, 1,157,052
  tokens (7.03× the direct baseline).
- Failure: six model-generated span offsets failed exact validation; one gap
  ownership conflict failed; repeated full source text dominated token use.
- Decision: performance is far from every target, so the next attempt changes
  the architecture rather than tuning wording.

## Iteration 1 — registered before execution

- One semantic call per case over the identified origin excerpt and complete
  eligible source inventory.
- Program-owned passage IDs and exact offsets replace model-generated offsets.
- Cutoff factual verdict and early provenance-risk prediction are separate.
- Generic rule: a publication can establish what it reports, but cannot by
  self-attestation authenticate that real data came from stated procedures.
- Pass conditions: ≥6/8 strict facts, 4/4 later-false risk flags, ≤2.00× direct
  baseline tokens.
