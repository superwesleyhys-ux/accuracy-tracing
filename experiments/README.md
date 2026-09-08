# Experiment code and local evidence archives

The public [Astra comparison report](../reports/model-evaluation-20260908/README.md)
retains every case outcome and call count, token receipts, source identifiers and
hashes, the original c03 test-data defect, and its separate post-hoc follow-up.
It contains no full publisher articles, model evidence packets or machine logs.

The separate [historical-cutoff experiment](historical-cutoff-20260908/PROTOCOL.md)
uses original evidence available before 2024 and holds later fabrication findings
outside the inference worker. Its [public results](../reports/historical-evaluation-20260908/README.md)
separate evidence-at-cutoff judgments from later truth, attribution controls and
identity-masking sensitivity checks. The two experiments are never pooled.

A separate [Inspect AI audit](../reports/historical-inspect-audit-20260908/README.md)
recomputes outcomes from the saved historical responses and registered evidence.
It performs no inference and does not count as another model trial. The optional
[replay script](historical-cutoff-20260908/inspect_replay.py) documents the pinned
Inspect dependency; its standard-library self-test needs no installation or
private source archive. Inspect is evaluation tooling, not a runtime dependency
of the harness.

Source captures, complete corpus/gold files, raw model responses, per-call inputs,
frozen snapshots and local setup diagnostics remain in the original local archive.
This follows the repository's distribution rules in [CONTRIBUTING.md](../CONTRIBUTING.md).
The public receipts support arithmetic checks; they do not independently reproduce
the original semantic judgments or prove that captured source bytes remain online.

The Python files here preserve the experiment implementation. Historical driver
scripts require their original **local** corpus, review records and result files;
those files are deliberately not distributed in a fresh checkout. The local
experiment drivers have macOS dependencies (`caffeinate` in the earlier pilots;
`sandbox-exec` for the historical worker). They are research recipes, not
the package's portable command-line interface. No inference runs on import.

The evaluation scoring scripts are also used by the regression tests.
Their tests generate synthetic inputs and require no captured sources,
credentials, model access or third-party packages:

```bash
python -m unittest discover -s tests -v
python tools/export_model_evaluation.py --verify-public
python tools/export_historical_evaluation.py --verify-public
```

To use the actual harness on your own eligible materials, follow the input
contract in [MODEL_TUNNELS.md](../docs/MODEL_TUNNELS.md) and the root README's
double-loop example. Local Codex execution is the default, with an explicit
API option. Live execution uses your configured model access and consumes tokens.
