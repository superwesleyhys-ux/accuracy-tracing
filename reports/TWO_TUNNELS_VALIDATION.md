# Two-tunnel validation

Local is the default for `trace-model`; `--tunnel api` selects the API explicitly.
Both live smoke runs completed with no execution errors. **132 automated tests passed.**

Both paths requested `gpt-6-astra` with `medium` reasoning over the same
`examples/model_trace.json` synthetic snapshot.

| Tunnel | CLI exit | Model calls | Fact verdict | Total call seconds | Input tokens | Output tokens |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| local | 0 | 2 | unresolved | 39.44 | 21,641 | 380 |
| api | 0 | 2 | unresolved | 18.14 | 2,254 | 594 |

The `unresolved` verdict is a valid semantic abstention on the fictional source,
not a failed model invocation. Each run performed decomposition and verification.
These two calls per path establish integration only; they are not an accuracy
benchmark or a statistically controlled speed comparison. The local CLI has
additional instructions and overhead compared with the direct API.

The first API attempt stopped before inference because this Python installation
had no default CA bundle. The transport now loads an already installed certifi
bundle only when default roots and explicit trust overrides are absent. TLS
certificate/hostname verification stays enabled. Explicit certificate directory
settings support lazy loading. The failure record is retained in
[model-api-smoke-initial-error.json](model-api-smoke-initial-error.json).
The subsequent API run returned HTTP 200 for both model calls. No automatic
cross-tunnel fallback or retry occurred.

Automated tests cover default routing, explicit API selection, shared prompt and
schema content, excluded-material isolation, exact quote validation, credential
redaction, refusals, incomplete responses, timeouts, TLS trust, missing credentials,
input-file preservation and failure exit codes. Network and subprocess operations
are replaced in unit tests. Actual live requests are recorded separately above.

Reproduce with:

```bash
python3 -m unittest discover -s tests
python3 -m newsverify trace-model examples/model_trace.json --output reports/model-local-smoke.json
python3 -m newsverify trace-model examples/model_trace.json --tunnel api --output reports/model-api-smoke.json
```

The API command uses `OPENAI_API_KEY`; the local command uses the existing Codex
login. The harness operates locally in both cases; model inference is hosted.

Full reports: [local](model-local-smoke.json), [API](model-api-smoke.json).
Machine-readable validation: [two-tunnels-validation.json](two-tunnels-validation.json).
