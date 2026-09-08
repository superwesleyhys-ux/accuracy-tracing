# Astra versus the double-loop harness: public results

The local test used the same Astra model with and without the harness. Gstack
guided development review; its skill catalog was excluded from both model paths.
Normal Codex instructions remain. This is not raw base-model API inference.

| Original six cases | Astra alone | Astra + harness |
|---|---:|---:|
| Completed runs | 6/6 | 6/6 |
| Matches to registered labels | 6/6 | 5/6 |
| Logical calls | 6 | 36 |
| Input + output tokens | 104,986 | 600,318 |

The harness used **5.72×** the tokens. Decomposition and revisits consumed
**51.1%** (306,478); verification 41.0% (245,969); selection 8.0% (47,871).
Cached input is already included. These are not monetary cost ratios.

The score difference is not an established accuracy advantage. Case **c03 had
a corpus/gold defect**: its claim named the NIST article date, but the evidence
packet omitted that dateline and supplied the paper date. The harness left the
missing qualifier unresolved. Original labels, all six denominators and outputs
remain preserved. A separately reported, post-hoc five-case subset ties **5/5**.

The selected **c03r post-hoc repair** restores the captured dateline and changes
“each measurement” to “each experimental shot” together. Both paths returned
supported: Astra used one call/18,137 tokens; the harness six calls/98,216 tokens.
It is **never pooled into the original score**. Neither final citation list
explicitly quotes the restored news dateline, although it is available in the
repaired packet. Quote integrity does not establish exhaustive qualifier coverage.

All **49 logical calls succeeded**: 42 original plus seven separate follow-up
calls. Both loops executed in five original cases and in the repaired case.
Internal CLI HTTP retries are not independently counted. The six original cases
are clustered across three events with agent-authored, agent-reviewed labels.
Astra alone sees the full eligible pool immediately; the harness selects from
that finite pool over multiple calls. There is no equal-token budget, independent
human adjudication, or demonstrated general accuracy winner.

## Public files

- [RESULTS.json](RESULTS.json): constructed targets, separate registered labels,
  all run outcomes/error counts, locally audited loop flags and separate scores.
- [RECEIPTS.json](RECEIPTS.json): 49 sanitized usage receipts with SHA-256 hashes
  of local input, response and original receipt files. No prompt or response text.
- [SOURCES.json](SOURCES.json): canonical source URLs, attribution, capture times,
  license notices and raw/text hashes. No third-party document bytes.
- [MANIFEST.json](MANIFEST.json): public-file hashes and hashes identifying the
  retained local archives.

Full sources, prompts, freeform model responses, private runtime logs and frozen
archive copies remain local under the repository's [contribution policy](../../CONTRIBUTING.md).
The public bundle supports recomputing accounting; it cannot independently verify
semantic evidence, quoted spans or complete loop histories. Hashes identify omitted
artifacts but do not substitute for access to them. Current downloads and hosted
model outputs can differ from the frozen evaluation.

From the repository root, verify this public bundle without archives or inference:

```sh
python3 tools/export_model_evaluation.py --verify-public
```

The [exporter](../../tools/export_model_evaluation.py) can regenerate the same
bundle without inference when the original full local archives are available:

```sh
python3 tools/export_model_evaluation.py
```

No claim is made that a fresh public clone can reproduce the original model
answers or source-level audits using these receipts alone.
