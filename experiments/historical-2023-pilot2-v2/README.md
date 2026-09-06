# Historical 2023 two-case pilot v2

This frozen pilot keeps the same ordered one-true/one-false subset from the
full historical-2023 benchmark:

- `virgin-galactic-commercial-service-2023` (true)
- `boeing-starliner-cft-2023` (false)

Both claims were published during 2023, use SEC EDGAR outcome evidence
available by the end of 2024, and have no full-evidence control variant. This
keeps the paid A/B to exactly two propositions and four arm/case runs. The same
cutoff, gold isolation, equal outer caps, no-replay rule, and retained error
denominator used by the full benchmark remain in force.

## Disclosed v2 corpus correction

This v2 corpus was created after the v1 audit showed that the Boeing outcome
excerpt did not contain enough local text to bind the abbreviation `CFT` to
the target event. V2 preserves the same filing and raw-artifact identity but
expands the excerpt with contiguous Commercial Crew context naming the CST-100
Starliner and expanding `Crewed Flight Test (CFT)`. The cases, order, labels,
cutoff, and source artifact are unchanged. V1 remains preserved for audit.
