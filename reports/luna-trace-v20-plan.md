# v20 strategy

Replace the current split finalization path with one immutable `VerificationResult` object. The same object will be used for the report, `raw_response`, response receipt, and scorer input. The policy change is structural: no late reconstruction of verdict or basis from history. Failure criterion: any mismatch between these four serialized views invalidates the run before scoring.
