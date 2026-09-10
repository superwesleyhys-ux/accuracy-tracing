# What changed and what remains unresolved

The earlier integrated run completed validly on only two of eight harness cases. Diagnosis
identified an unconstrained JSON string inside a structured outer response,
research findings that never reached formal verification, duplicate transmission
of the current full source, and optional report-writing stages on the critical
path for a single claim.

## Implemented repairs

- Research stages return native nested schema objects. Type, field and size
  violations remain explicit failures; malformed answers are not silently
  repaired or selectively retried.
- Research sees every eligible historical version, including versions sharing a
  URL, with fair excerpt allocation and exact offsets. Multiple versions of one
  source are not treated as independent corroboration.
- Bounded research questions and findings reach formal source selection,
  decomposition and verification as untrusted advice. They cannot supply
  quotations, change the claim, admit sources or resolve evidence gaps.
- Decomposition sends the full current material once and retains all other
  admitted materials. A sole eligible remaining version of the same source is
  inspected without a model selection call. Decomposition and verification still
  run, and evidence-driven revisits remain active.
- Prompts request concise, relevant quotations and distinguish a report's
  attribution from the authenticity of its underlying observations.
- Optional `research_mode: "claim"` keeps source research, synthesis and the
  formal double loop for exactly one explicit claim per item. Causal analysis,
  grounding, timelines, perspectives and the explanatory draft are recorded as
  intentionally omitted. Errors in retained stages still invalidate the complete
  item. Full mode remains available and is the default. The single-claim example
  now selects claim mode explicitly.

| Implementation | Changed responsibility |
| --- | --- |
| [Client](../../newsverify/news_client.py) and [schemas](../../newsverify/news_tracing/schemas.py) | Native research output contracts, validation and version-aware excerpts. |
| [News runner](../../newsverify/news_tracing_runner.py) | Retain source versions, pass untrusted advice, validate the selected research mode. |
| [Double loop](../../newsverify/double_loop.py) | Concise source prompts, remove duplicated current material and avoid unnecessary same-source selection calls. |
| [Research core](../../newsverify/news_tracing/core.py) and [prompts](../../newsverify/news_tracing/prompts.py) | Explicit claim scope, retained source research and recorded optional-stage skips. |

See [usage and limits](../../docs/NEWS_TRACING.md) and the
[single-claim example](../../examples/news_tracing.json).

## Validation and measured development effect

All 252 automated tests passed before the final confirmation. Independent
synthetic checks covered exact claims, both research modes, all version excerpts,
advice boundaries and a real injected transport failure that remained a failure.

On the four named development cases, both candidates produced 4/4 valid answers
consistent with the cutoff evidence. Candidate 1 used 765,412 benchmark tokens;
candidate 2 used 606,328, a 20.78% reduction. Their paired direct Astra baselines
used 93,090 and 93,107 tokens. Both arms left the two authenticity claims
unresolved and detected no fabrication in advance. These are improvements
against the earlier harness, not evidence of superiority over Astra.

The unchanged second candidate then completed the eight-case confirmation with
8/8 valid cutoff-correct answers in each arm. Its 70 recorded calls used
1,213,150 tokens; direct Astra's eight calls used 185,885, making the harness
6.53 times as expensive in measured tokens. Both still left the two named
authenticity claims unresolved, with no advance fabrication detection; masked
variants gave the same outcomes.

Across the three batches, all 166 recorded benchmark calls completed and all
32 run outcomes passed the registered whole-pipeline and citation checks. Total
measured benchmark usage was 2,956,972 tokens, with no unknown-usage calls.
The [comparison report](README.md) retains every scored batch. Repeated cases
are not additional independent events.

## Remaining limits

The fixed historical packets lack independent laboratory records sufficient to
establish the two later fabrication findings at the cutoff. Locating the
original paper identifies where a claim was reported; it does not authenticate
the experiment. Repeated reasoning over those same sources cannot create the
missing records.

The benchmark supplies a fixed historical source pool and disables live source
collection. It does not establish an improvement in finding sources on the live
web, PDF/image forensics, or decoding figures. Present-day model memory is not
erased. The eight cases were already exposed during development and represent
only two event families. Bounded screening of 19 additional candidate families
produced no approved new holdout cases; this does not prove none exist.

The remaining measured cost is substantial. In confirmation, formal processing
used 660,798 tokens: decomposition used 411,527 across 20 calls, and verification
used 249,271 across 14 calls. Source research used another 552,352 across 36
calls. Repeated evidence processing still costs much more than the direct
baseline's single call per case.

The local CLI route still performs hosted model inference. All measured model
calls and known/unknown usage are retained; this task's development and audit
agent usage is outside those benchmark totals.
