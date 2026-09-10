# Luna calibrated evidence policy — execution failure

This round changed the decision policy again: one evidence-ledger judgment per harness case, with explicit scope calibration for settled and conflicting verdicts, and the required historical prefix included in the request.

The fixed 8-case comparison completed 16 planned rows. Direct calls returned, but every custom harness call failed at the Luna CLI boundary while validating the custom structured output. No final harness verdict was produced, so the scoring denominator has zero valid harness results and no accuracy or superiority credit. The exact policy is closed and will not be rerun. Future work must first use the model's already-proven output schema or add a preflight schema-compatibility check before any model dispatch.
