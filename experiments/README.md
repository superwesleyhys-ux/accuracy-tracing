# Experiment code and local evidence archives

The public [Astra comparison report](../reports/model-evaluation-20260908/README.md)
retains every case outcome and call count, token receipts, source identifiers and
hashes, the original c03 test-data defect, and its separate post-hoc follow-up.
It contains no full publisher articles, model evidence packets or machine logs.

Source captures, complete corpus/gold files, raw model responses, per-call inputs,
frozen snapshots and local setup diagnostics remain in the original local archive.
This follows the repository's distribution rules in [CONTRIBUTING.md](../CONTRIBUTING.md).
The public receipts support arithmetic checks; they do not independently reproduce
the original semantic judgments or prove that captured source bytes remain online.

The Python files here preserve the experiment implementation. Historical driver
scripts require their original **local** corpus, review records and result files;
those files are deliberately not distributed in a fresh checkout. The local
experiment drivers also use macOS `caffeinate`. They are research recipes, not
the package's portable command-line interface. No inference runs on import.

`gstack-harness-eval-20260908/summarize_test.py` is also used by the regression
tests. Its tests generate synthetic inputs and require no captured sources,
credentials, model access or third-party packages:

```bash
python -m unittest discover -s tests -v
python tools/export_model_evaluation.py --verify-public
```

To use the actual harness on your own eligible materials, follow the input
contract in [MODEL_TUNNELS.md](../docs/MODEL_TUNNELS.md) and the root README's
double-loop example. Local Codex execution is the default, with an explicit
API option. Live execution uses your configured model access and consumes tokens.
