# Luna evidence-trace v4 — 2026-09-10

The fresh trace policy ran 16 arms and passed independent audit. Both arms used GPT-5.6 Luna, low reasoning, local Codex-login, with the historical cutoff contract.

## Result

| Measure | Direct | Harness trace |
|---|---:|---:|
| Evidence-valid cutoff matches (8 cases) | 2/8 | **3/8** |
| Original variant | 1/4 | 1/4 |
| Blinded variant | 1/4 | **2/4** |
| Later-false claims accepted | 0 | 0 |

The harness exceeds the unassisted model on the primary aggregate evidence-valid cutoff-match measure (3/8 vs 2/8), with no increase in later-false acceptance. It required 17 logical calls versus 8 direct calls and used 216,070 versus 163,738 known tokens. This is an accuracy-first win; token reduction remains a separate follow-up.
