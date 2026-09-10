# Luna single-pass evidence-ledger policy — invalidated before scoring

This was a substantive policy change after the reliability-gated run: the harness would make one independent evidence-ledger judgment per case, fail closed, and remove intermediate model stages.

The fixed eight-case Luna comparison completed 16 planned rows, with direct rows returning and each harness row making one call. The batch is **invalidated before scoring** because the custom harness path omitted the required historical cutoff instruction prefix from its actual request. The authoritative scorer stopped at that request-audit check before reading private gold. No accuracy, later-falsity, or superiority credit is valid. The outputs remain at `experiments/luna-single-pass-20260910/results-v3/`; this exact policy is not rerun.
