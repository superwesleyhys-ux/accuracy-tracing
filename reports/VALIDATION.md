# Validation record

Prepared September 5, 2026 on Python 3.12.13.

- `python3 -m unittest discover -s tests -v`: 25 tests passed. The suite includes all 22 synthetic benchmark scenarios as subtests.
- `python3 -m newsverify benchmark examples/benchmark.json`: all 22 expected policy outcomes matched.
- Demo: a provisional supported first pass becomes conflicting when the second pass supplies a correction.
- An offline wheel build succeeded. The packaged demo ran from outside the source directory and returned conflicting after two rounds.
- The GitHub Actions workflow is provided but has not been run on GitHub. Its additional Python versions have not been tested locally.

These results verify software behavior on supplied synthetic annotations. They do not measure live retrieval, source authenticity, semantic factuality, real-world news accuracy, or improvement under equal budgets. No paid APIs or live news providers were called. The original private tracker is not integrated, and no public repository or program application has been submitted.

The reproducible benchmark report is `benchmark.json`; detailed test output is `tests.txt`; the full demonstration audit is `demo.json`.

The CI workflow follows [GitHub's Python workflow documentation](https://docs.github.com/actions/guides/building-and-testing-python).
