# Real local Astra retest

The same news claim was rerun through the updated harness using local GPT-6 Astra, medium reasoning, a 75-second per-call timeout and a 24-call cap. The supplied input and configuration were unchanged. No application code changed during this rerun.

| Measure | Previous run | Fresh run |
| --- | ---: | ---: |
| Requested / retained claims | 1 / 1 | 1 / 1 |
| Overall result | partial | partial |
| Factual verdict | unresolved | unresolved |
| Provenance status | partial | partial |
| Verified originals | 0 | 0 |
| Timeline-format errors | 1 | 0 |
| Successful / total model calls | 16 / 16 | 16 / 16 |
| Measured total tokens | 354,952 | 358,445 |
| Elapsed seconds | 330.8 | 323.8 |

## Source retrieval and remaining gaps

The observed source chain is [ScienceDaily](https://www.sciencedaily.com/releases/2025/02/250204132023.htm) → [NASA](https://science.nasa.gov/missions/hubble/hubble-investigates-galaxy-with-nine-rings/) → [cited paper](https://doi.org/10.3847/2041-8213/ad9f5c). A selected citation is not a verified original record.

- source_collection: `invalid_url` — http://dx.doi.org/10.3847/2041-8213/ad9f5c

The previous timeline-format error did not recur in the real rerun.

A separate one-fetch diagnostic raised only the extracted-text allowance to 200,000 characters. It also failed with `invalid_url` after publisher redirection and returned no article body. That diagnostic made no model calls and did not supply evidence to the main run. It does not show that increasing the text allowance would solve the current retrieval problem.

## Interpretation

The fresh factual verdict is **unresolved**. All 213 deterministic tests pass. Successful model calls and passing software tests do not establish the underlying scientific claim or improved fake-news accuracy.

The two runs use live pages and model-generated judgments. Runtime or token differences in this single pair should not be treated as a reliable performance improvement. Source text equality is recorded in SUMMARY.json. This current-web case concerns a 2025 report and does not satisfy the separate pre-2024 historical-test requirement.

The original run is preserved unchanged. Full source text, prompts, responses and per-call receipts remain in the ignored local experiment folder.

[Machine-readable comparison](SUMMARY.json) · [Previous run](../news-tracing-integration-20260908/README.md) · [Usage](../../docs/NEWS_TRACING.md)
