# Preregistered same-task historical holdout

This benchmark compares an ordinary model prompt with the FactCircuit
decomposition prompt. Both arms use the same local Codex-login tunnel, the same
model and reasoning setting, one call per case, and the same closed evidence
packet. API credentials, web access, tools, plugins, skills, persistent memory,
and route fallback are disabled by the tunnel.

## Question and time boundary

Every case asks the same question: using only evidence public by
2024-12-31, does the paper merit **elevated** or **ordinary** research-integrity
follow-up? The papers were published before 2024. Four were subject to official
fabrication or falsification findings first published in 2025–2026; four are
matched papers for which no such public finding was located through 2026-09-11.

The later findings are held in a sealed gold file. They are not present in the
model packet. Author names, titles, DOI values, institutions, journals, URLs,
and later outcomes are also excluded from the packet. Source receipts remain in
the corpus for human audit, but the runner sends only `public_packet` to the
isolated model process.

Eligibility is based on public availability, not the date on which an event
privately occurred. A fact first disclosed by a 2025–2026 investigation is
excluded even if it describes an action before the cutoff. A pre-cutoff public
comment may be included, with later sources used only to audit its date.

## Fixed design

- Eight independent paper families: four later-positive and four controls.
- All cases use the same question, fields, output schema, and binary labels.
- The case order and arm order are fixed before inference.
- The direct arm gets a short, generic integrity-screening instruction.
- The harness arm must separately inspect source traceability, internal
  anomalies, correction history, independent checks, and innocent
  explanations before applying a fixed evidence threshold.
- Missing raw data alone is insufficient for an elevated label in either arm.
- No prompt, packet, label, scorer, or threshold may change after inference.
- Failed calls count as incorrect. There are no retries.

## Registered metrics

The primary metric is balanced accuracy over the four later-positive and four
control papers. Secondary metrics are ordinary accuracy, sensitivity,
specificity, completed calls, evidence-ID validity, and input-plus-output
tokens. The harness succeeds only if its balanced accuracy is strictly greater
than the direct arm's, all 16 calls complete with valid outputs, and its token
total is no more than twice the direct arm's token total.

This is a small exploratory holdout. A control label means no public official
finding was located by the audit date; it is not proof that the paper is free of
problems. Identity masking reduces direct recall of later events but cannot
remove facts embedded in model parameters. The result is descriptive and does
not establish statistical significance.
