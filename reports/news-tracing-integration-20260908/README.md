# News-tracing integration test

The uploaded project is integrated into the local-default harness. The real run traced a ScienceDaily story to NASA and the cited paper, but did not verify the underlying scientific claim. This is one current-web integration case, not an accuracy benchmark or a replacement for the pre-2024 historical evaluation.

## Real result

- Model route: local Codex CLI, GPT-6 Astra, medium reasoning; 16 of 16 model invocations returned successfully.
- Elapsed time: 330.8 seconds; measured tokens: 354,952 (346,096 input, 8,856 output; 30,848 cached input included).
- One requested claim, one retained result: factual verdict **unresolved**, provenance **partial**, verified originals **0**.
- Overall run: **partial**. Successful model calls do not imply successful factual verification.

Observed chain: [ScienceDaily](https://www.sciencedaily.com/releases/2025/02/250204132023.htm) → [NASA](https://science.nasa.gov/missions/hubble/hubble-investigates-galaxy-with-nine-rings/) → [cited research paper](https://doi.org/10.3847/2041-8213/ad9f5c). The first two pages were fetched. The paper was an observed citation selected for retrieval, but its extracted text exceeded the 50,000-character page limit.

The claim concerned Hubble finding eight rings and Keck observations confirming a ninth. The verifier recognized that ScienceDaily reused NASA material. It required the paper and observational analysis to settle the claim, rather than counting the two articles as independent confirmation.

## Failures and fixes

- The research paper remains uncollected. A complete, dated text snapshot or additional document-reading support is needed to close that evidence gap. No false/true judgment was substituted for missing evidence.
- The live timeline stage returned a structured causal-link object where a string was expected. The active adapter now preserves the exact supported legacy shape as unverified display text, and the prompt specifies the format. Two regression tests cover valid and malformed objects.
- Review also fixed navigation links hiding late article citations and unnecessary model calls when document capacity was exhausted. Source summaries now expose unsuccessful upstream retrieval candidates.
- Two earlier collector-only preflights reached readable ScienceDaily stories but could not fetch their linked NASA/JPL pages. They are preserved in SUMMARY.json and are not model test outcomes.

## Validation and scope

All **213 deterministic tests pass**, including 37 news-integration tests. Tests cover copied source chains, an original release contradicted by its raw record, unrelated older originals, missing citations, historical exclusions before every model stage, failed claims retained in denominators, whole-batch call limits, redirects, and CLI behavior. All 10 uploaded files match the archive bytes and hash manifest. The wheel builds and the packaged CLI imports without the uploaded API/UI dependencies.

The full live result remains unchanged. Final catalog, budget, URL, timeline and summary refinements were tested deterministically after that run; these tests are not additional model accuracy results. A separate local connection check used one call and 8,778 tokens, excluded from the 16-call run above.

Current pages were captured in 2026. This exercise does not establish a pre-2024 information boundary, erase later knowledge from model weights, demonstrate improved fake-news accuracy, or compare against a bare-model control. The existing historical benchmark artifacts were not changed.

## Measured stage usage

| Stage | Calls | Input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| origin_links | 1 | 20,053 | 120 |
| deconstruct | 1 | 18,462 | 148 |
| search_plan | 1 | 18,599 | 96 |
| source_trace | 1 | 18,559 | 560 |
| source_verify | 1 | 19,095 | 319 |
| timeline_build | 1 | 19,235 | 1,037 |
| perspective | 1 | 19,193 | 173 |
| direct_response | 1 | 20,234 | 253 |
| synthesis | 1 | 20,955 | 1,245 |
| decompose | 3 | 83,362 | 3,975 |
| verify | 3 | 78,743 | 868 |
| select | 1 | 9,606 | 62 |

[Machine-readable summary](SUMMARY.json) · [Usage and input format](../../docs/NEWS_TRACING.md) · [Example](../../examples/news_tracing.json)

Full fetched pages, prompts and model outputs remain in the ignored local experiment directory. This public-facing report contains source links and measured results, not full third-party source text.
