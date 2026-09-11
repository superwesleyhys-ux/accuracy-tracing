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

### Pre-inference launch failure

The first launch stopped before any model call because the runner passed a text
path rather than a `Path` object to its own hash helper. The empty attempt is
retained under `run-iteration-1`; it contains no prediction and consumed zero
model tokens. This is an infrastructure correction, so the registered semantic
policy remains unchanged for `run-iteration-1b`.

### Result

- Strict cutoff fact accuracy: 8/8 (100%).
- Later-false provenance claims flagged high risk: 4/4.
- Attribution controls flagged high risk: 0/4.
- Model calls: 8/8 successful, exactly one per case.
- Fully accounted tokens: 64,444, or 0.39× the 164,490-token direct
  baseline.
- All three registered pass conditions were met. No prompt revision or
  selective rerun was needed after inference began.

### Post-run validity audit — result invalidated

The apparent 4/4 detection result is not a valid fabrication test. The candidate
policy deterministically assigns high risk to unauthenticated real-world
provenance claims, while all four controls are source-attribution questions.
Claim type therefore leaks the class. There are no nonfabricated real-world
provenance controls, the cases were already observed during development, and
the four variants cover only two families. The raw receipts remain preserved,
but this iteration is classified as a failed evaluation design and cannot prove
the detection or accuracy goals. The next iteration must make a large change:
new event families, same-task controls, frozen inputs, and no policy update after
outcomes from that batch are visible.
