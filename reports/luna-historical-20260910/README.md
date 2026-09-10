# Luna historical comparison — invalidated before scoring

The first real historical run after the cost-driven model switch used the existing eight-case cutoff package with both arms on `gpt-5.6-luna`, low reasoning, and the local Codex-login route. It completed 16 planned rows, but several double-loop calls failed and returned partial rows.

The run is **not scored**. The copied registration still committed the original Astra-era scorer hash, while the Luna snapshot necessarily changed the model profile in the copied scorer. The scorer stopped at its registration-hash check before reading private gold, so no cutoff or later-truth accuracy credit is valid. The outputs and failures remain preserved in `experiments/luna-historical-20260910/luna-results-1/`; they must not be used as a favorable sample or silently repaired.

This is a setup failure, not a model result. A future Luna run needs a fresh pre-inference registration whose scorer, helper, builder, input-review, and gold-review hashes all match the Luna snapshot. That fix must be frozen before any new dispatch. The failed run is not repeated in this continuation.

The direct and harness rows used the same fixed historical inputs and no API fallback. No Astra call was made in this run. Token totals and semantic scores are intentionally withheld because the authoritative scorer rejected the batch before gold parsing.

## Corrected Luna run

A fresh Luna snapshot with a matching pre-inference registration completed the fixed eight-case comparison: 16 planned rows. Direct completed 8/8 calls with 164,145 known tokens. The double-loop completed 12 calls with 135,682 known tokens; several harness rows failed during execution.

The authoritative summary shows no harness advantage. In the original variant, direct and double-loop each had 1 evidence-valid case and 1 cutoff match, but the harness completed only 1 case. In the blinded variant, direct had 0 evidence-valid cases and double-loop had 1, while the harness again completed only 1 of 4 cases. Later-false detection was 0 for both arms. This is a diagnostic result with execution loss, not evidence that the harness exceeds Luna. The corrected outputs are retained in `experiments/luna-historical-20260910-v2/luna-results-v2/`; the invalid first run remains preserved.
