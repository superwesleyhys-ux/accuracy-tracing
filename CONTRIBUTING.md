# Contributing to Accuracy Tracing

NewsVerify Harness welcomes small, reproducible changes that make evidence handling easier to inspect and harder to misuse.

Useful first contributions include a failing evidence fixture, a source-lineage edge case, clearer rejection messages, or an adapter that follows the documented contract. Discuss a new external dependency or a policy change in an issue before building it.

## Local workflow

Use Python 3.11 or later. From the repository directory, run:

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 -m newsverify benchmark examples/benchmark.json --output reports/benchmark.json
```

Before opening a pull request, also run `python3 scripts/validate_release.py`
when your change affects tracked release files. CI repeats the regression suite
on Python 3.11, 3.12, and 3.13.

Include the behavior you changed, why it matters, and a minimal fixture or test that would fail without the fix. For policy changes, explain which existing outcomes change and why. Keep fixtures deterministic and use explicit, timezone-aware timestamps.

## Evidence and claims

- Label synthetic material clearly. Do not present fixture results as real-world accuracy.
- Use material you have permission to distribute, or small excerpts with provenance where appropriate. Never commit private feeds, credentials, or personal data.
- Preserve both sides of a disagreement and the rejection history. Do not tune thresholds on the final evaluation set.
- State when a stance label or publisher relationship is human-supplied, inferred, or independently reviewed.
- Keep actual metric denominators, failures, exclusions, and run configuration available with reported results.

Contributions are made under the project's [MIT License](LICENSE). Report a defect with enough information to reproduce it, without publishing secrets from your environment.

Use a regular issue for code defects and proposals. Use the dedicated
[Accuracy decline discussion category](https://github.com/superwesleyhys-ux/accuracy-tracing/discussions/categories/accuracy-decline)
for before/after metric regressions or weaker trace outcomes. Report security
issues privately as described in [SECURITY.md](SECURITY.md).
