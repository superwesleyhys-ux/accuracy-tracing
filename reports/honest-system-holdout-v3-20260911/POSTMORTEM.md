# Holdout v3 postmortem: infrastructure-invalid run

Run `run-001` is retained exactly as produced. It must not be presented as a
valid benchmark win.

The registered JSON schema allowed up to six cited evidence passages, but the
frozen Python validator rejected more than five. The `v301` harness call
completed successfully and returned six citations, then the local validator
discarded its result. The preregistered rule counts invalid output as wrong and
forbids retries, so `scored-v1` records that case as incorrect and the
all-valid-output success criterion is false.

The descriptive score was direct 50.0% and harness 87.5%, with a 1.07x token
ratio. Because only 15 of 16 outputs passed validation, the run is classified
as infrastructure-invalid regardless of that score.

The frozen v3 experiment files and failed run remain unchanged for audit. A
follow-up must fix the schema/validator mismatch before registration and use
new cases and a changed policy; it may not retry `v301`.
