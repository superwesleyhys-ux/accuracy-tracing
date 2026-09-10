# Harness optimization: development results

These are repeated tests on previously inspected cases from **two event families**, not an unseen accuracy test. Masked variants are correlated sensitivity checks. [Registered protocol](../../experiments/harness-optimization-20260909/PROTOCOL.md).

Latest scored batch, confirmation (claim): on the four named cases, Astra alone had 4/4 (100%) valid cutoff-correct answers; the harness had 4/4 (100%). Of the two named claims later established as fabricated, Astra called 0 false and abstained on 2; the harness called 0 false and abstained on 2. Failed/invalid authenticity outcomes were 0 and 0, respectively.

Abstention is not advance fabrication detection. A false verdict unsupported by the supplied cutoff evidence is not justified detection either. The original Astra comparison already scored 8/8; this development set cannot establish an accuracy improvement over that result.

## Paired outcomes

Workflow labels describe the harness arm; the direct Astra setup stays fixed. **Full** enables the broader research workflow; **claim** focuses on the one explicit claim and intentionally omits causal expansion, causal grounding review, timeline, perspective analysis and the separate narrative response. Claim mode retains decomposition, targeted source research, synthesis and formal evidence verification. Comparisons across rounds reflect these workflow changes, not identical harness settings.

Valid cutoff agreement requires the complete research/formal pipeline and exact-source evidence checks. Formal-only agreement is diagnostic and cannot rescue a failed whole pipeline.

| Round | Arm | Set | Valid cutoff agreement | Pipeline completed | Evidence valid | Failed/invalid | Unsupported definite | Formal-only agreement | True controls correct |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| round-1 (full) | Astra alone | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| round-1 (full) | Harness | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| round-2 (claim) | Astra alone | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| round-2 (claim) | Harness | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| confirmation (claim) | Astra alone | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| confirmation (claim) | Harness | Named DEV | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| confirmation (claim) | Astra alone | Masked sensitivity | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |
| confirmation (claim) | Harness | Masked sensitivity | 4/4 (100%) | 4/4 | 4/4 | 0 | 0 | 4/4 | 2/2 |

## Later-false claims: separate outcomes

Only valid outcomes enter the first four categories; failures remain in the denominator. The two named targets concern reported measurement/data authenticity, not whether every scientific hypothesis is false.

| Round | Arm | Set | Claims | Called false | Abstained | Accepted | Conflicting | Failed/invalid |
|---|---|---|---:|---:|---:|---:|---:|---:|
| round-1 (full) | Astra alone | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| round-1 (full) | Harness | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| round-2 (claim) | Astra alone | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| round-2 (claim) | Harness | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| confirmation (claim) | Astra alone | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| confirmation (claim) | Harness | Named DEV | 2 | 0 | 2 | 0 | 0 | 0 |
| confirmation (claim) | Astra alone | Masked sensitivity | 2 | 0 | 2 | 0 | 0 | 0 |
| confirmation (claim) | Harness | Masked sensitivity | 2 | 0 | 2 | 0 | 0 | 0 |

## Tokens and calls

All attempted calls, including failures, are counted. Unknown totals stay unknown; known counts are lower bounds when any usage is missing. Cached input is already included in input tokens, not added again. These figures cover recorded benchmark target-model invocations only. They exclude this Codex task's orchestration, audit and research-agent usage, which is not measured here; they are not total account usage or spend.

| Round | Arm | Set | Calls | Known input | Known output | Known cached input | Total tokens | Calls with unknown usage |
|---|---|---|---:|---:|---:|---:|---:|---:|
| round-1 (full) | Astra alone | Named DEV | 4 | 92,402 | 688 | 7,552 | 93,090 | 0 |
| round-1 (full) | Harness | Named DEV | 45 | 748,743 | 16,669 | 38,528 | 765,412 | 0 |
| round-2 (claim) | Astra alone | Named DEV | 4 | 92,400 | 707 | 7,552 | 93,107 | 0 |
| round-2 (claim) | Harness | Named DEV | 35 | 592,415 | 13,913 | 62,720 | 606,328 | 0 |
| confirmation (claim) | Astra alone | Named DEV | 4 | 92,404 | 666 | 7,552 | 93,070 | 0 |
| confirmation (claim) | Harness | Named DEV | 35 | 593,225 | 13,919 | 61,824 | 607,144 | 0 |
| confirmation (claim) | Astra alone | Masked sensitivity | 4 | 92,100 | 715 | 15,104 | 92,815 | 0 |
| confirmation (claim) | Harness | Masked sensitivity | 35 | 591,728 | 14,278 | 116,608 | 606,006 | 0 |

The efficiency threshold preserves baseline accuracy: both arms must have valid cutoff-correct answers for every planned case (4/4 in DEV; 8/8 in confirmation), and the harness must use at least 20% fewer fully accounted tokens. Equal reduced scores or matching failures cannot meet it. Missing usage cannot establish this advantage.

- round-1 (full), named cases: harness/Astra token ratio **8.22×**. DEV efficiency threshold: not met.
- round-2 (claim), named cases: harness/Astra token ratio **6.51×**. DEV efficiency threshold: not met.
- confirmation (claim), named cases: harness/Astra token ratio **6.52×**. This is a repeated-case confirmation ratio, not independent validation.
- confirmation, all eight planned cases: harness/Astra token ratio **6.53×**; full-accuracy efficiency threshold not met. This remains a development-data result.

Harness development change from round-1 (full) to round-2 (claim): valid cutoff-correct outcomes were 4/4 and 4/4; fully accounted tokens changed from 765,412 to 606,328 (**20.78% fewer**). This compares two harness workflows on DEV. It does not establish an efficiency win over Astra or advance fabrication detection.

## Research versus formal phases

Phase totals cover all cases in that batch (four named cases in development; eight named/masked cases in confirmation). They count actual invocations; deterministic source selection requires no model call. Successful calls mean transport completion; their outputs can still fail validation.

| Round | Arm | Phase | Calls | Successful calls | Known input | Known output | Total tokens | Unknown-usage calls |
|---|---|---|---:|---:|---:|---:|---:|---:|
| round-1 (full) | Astra alone | direct | 4 | 4 | 92,402 | 688 | 93,090 | 0 |
| round-1 (full) | Harness | formal | 17 | 17 | 322,725 | 10,849 | 333,574 | 0 |
| round-1 (full) | Harness | research | 28 | 28 | 426,018 | 5,820 | 431,838 | 0 |
| round-2 (claim) | Astra alone | direct | 4 | 4 | 92,400 | 707 | 93,107 | 0 |
| round-2 (claim) | Harness | formal | 17 | 17 | 319,379 | 10,017 | 329,396 | 0 |
| round-2 (claim) | Harness | research | 18 | 18 | 273,036 | 3,896 | 276,932 | 0 |
| confirmation (claim) | Astra alone | direct | 8 | 8 | 184,504 | 1,381 | 185,885 | 0 |
| confirmation (claim) | Harness | formal | 34 | 34 | 640,258 | 20,540 | 660,798 | 0 |
| confirmation (claim) | Harness | research | 36 | 36 | 544,695 | 7,657 | 552,352 | 0 |

## Earlier integrated-harness baseline

Before these optimization rounds, the four named cases had 4/4 valid cutoff-correct outcomes for Astra alone and 1/4 for the integrated harness. The harness recorded at least 805,794 tokens; one invocation had unknown usage, so its exact total and an exact cost ratio are unavailable. [Preserved earlier report](../historical-news-tracing-20260908/README.md).

## Screening for unseen cases

Screening covered **19 deduplicated event families**. It produced **0 ready new families and 0 ready new cases**, with **0 active follow-ups pending**. No held-out dataset was created and no held-out model evaluation was conducted. Zero pending means no queued follow-ups; earlier uncertain leads remain unapproved.

This was bounded screening under the required historical-evidence and first-public-finding dates, not proof that no eligible families exist. [Verified metadata-only screening totals](SCREENING_TOTALS.json).

## Scope and audit commitments

Both arms use gpt-6-astra at medium reasoning through the local Codex-login HTTP route; inference is hosted. Direct gets one call, the harness at most 24 calls including at most 10 formal calls, each capped at 90 seconds. Only supplied versions available by the end of 2023 are eligible; no live source search is used. Later labels are scored after the batch. Research advice remains untrusted and cannot establish evidence or source originality. Original publication is not proof of authentic measurements.

The evidence pool is finite. One historical accepted-manuscript text packet lacks its referenced table/figure sheets; this is text-only evaluation, not visual or laboratory forensics. A present-day model's learned knowledge cannot be erased. Repeated cases and masked identities do not provide independent generalization evidence. No latency advantage is inferred from potentially inconsistent clocks. Only completed, scored batches supplied to this exporter are included; partial attempts require separate reporting and cannot be silently replaced.

The tables are reconstructed from outcome rows and checked against condition and stage totals. The exporter emits no source text, model prose, prompts or personal paths.

| Round | Registration SHA256 | Candidate inventory SHA256 | Scorer SHA256 |
|---|---|---|---|
| round-1 (full) | `cd90d895208d75a97f5b0fd0275e7a489ee8994738938e51edaf228df3b486b7` | `02120501d898bd3e95d728e59e79288149c640e10147c7700d742f9d3540b474` | `b2487d1c3f0fb135e8c576679bbb9819baefbad2c04bdfc0725cbccd0bdead0b` |
| round-2 (claim) | `ed45a2f5f2feba28f6a9796ab7fe1bf80a92d0f2f1ce8548bb4ea057272c4934` | `34d6410b1c16e0b372ee290d83aa188467b65cd73eaa70a335d850e895160598` | `41c9231559c68fc359be0985ca551a4f4a194f94ea29bc9e66ef5384fb742e47` |
| confirmation (claim) | `0612a229b9ff9aa63221277eb0c09744952dae8a590cc322a389196c547585b7` | `34d6410b1c16e0b372ee290d83aa188467b65cd73eaa70a335d850e895160598` | `41c9231559c68fc359be0985ca551a4f4a194f94ea29bc9e66ef5384fb742e47` |

## Complete publication totals

Across both development rounds and the confirmation, **32 case-run outcomes** passed the registered validity and cutoff-correctness checks. All **166 recorded benchmark calls** completed successfully. Measured usage was **2,956,972 tokens**, with **0 failed calls and 0 unknown-usage calls**. Repeated cases are not additional independent events, and these totals exclude orchestration/audit/research-agent usage.

The final confirmation had 8/8 valid cutoff-correct answers in each arm. Astra alone used **185,885 tokens**; the selected harness used **1,213,150 tokens**, or **6.53×** as many. Both abstained on the two named later-false claims; masked variants had the same outcomes. Neither an accuracy win nor an efficiency win over Astra was established.

Observed named-case valid cutoff-correct outcomes improved from 1/4 in the earlier integrated harness to 4/4 in each development candidate. The measured 20.78% token reduction compares candidate 2 with candidate 1, not with Astra. These are observed development results, not an isolated causal experiment.

[Implementation changes and remaining limits](CHANGES.md) · [Machine-readable comparison totals](comparison.json).

| Batch | Sanitized outcome rows | Sanitized call receipts |
|---|---|---|
| Round 1, full | [SUMMARY.json](round-1/SUMMARY.json) | [SANITIZED_RECEIPTS.json](round-1/SANITIZED_RECEIPTS.json) |
| Round 2, claim | [SUMMARY.json](round-2/SUMMARY.json) | [SANITIZED_RECEIPTS.json](round-2/SANITIZED_RECEIPTS.json) |
| Confirmation, claim | [SUMMARY.json](confirmation/SUMMARY.json) | [SANITIZED_RECEIPTS.json](confirmation/SANITIZED_RECEIPTS.json) |

Outcome rows retain every denominator, including failed/invalid categories (zero in these three batches). Public metadata copies preserve the scorer's original bytes and their hashes; source texts, prompts and model explanations are excluded.
