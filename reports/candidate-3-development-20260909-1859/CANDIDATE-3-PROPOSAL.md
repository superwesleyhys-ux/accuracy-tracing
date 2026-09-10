# Proposed Candidate 3: align the verdict with the unchanged target

Status: source-blind proposal only, refined after the parent relayed the independent semantic audit's generic finding. The candidate remains unimplemented and untested. This file does not install a prompt, change a frozen trial, register an experiment, or report an improvement. No private corpus, gold, source passage, or model response was read for this proposal.

The parent reports 15 recorded calls and four supported outcomes in the new pilot: each arm received automatic cutoff/future credit on one of two cases, accepted the later-corrected false claim, and accepted the true control. The parent subsequently relayed the independent semantic finding: all four final quotations were exact and eligible, but only two supported the registered real-world target. In the two erroneous answers, both arms explicitly narrowed their rationale to what a source reported and acknowledged missing independent support, while still emitting supported for the real-world target. The true control was supported correctly. This identifies a verdict/rationale scope inconsistency, not a general defect in first-party evidence. A later correction establishes factual error, not fabrication or intent.

## One falsifiable hypothesis

Candidate 2 already explicitly separates “the source reports X” from “X actually happened.” The confirmed inconsistency suggests that distinction was not enforced at the final verdict: a narrower proposition was judged established, but its supported status was assigned to the unchanged stronger target. A brief verdict-to-target consistency check could prevent that promotion and handle an explicitly acknowledged unresolved necessary step without distrusting adequate ordinary occurrence evidence.

The proposed intervention has one mechanism: before assigning the final status, compare the exact target with the proposition the rationale says the evidence establishes. It does not add independent corroboration as a universal requirement. A caveat about unavailable corroboration may coexist with supported when the supplied first-hand evidence already adequately establishes the actual target; the failure occurs when the answer itself only settles a weaker attribution proposition or leaves a necessary part of the target unestablished.

This is now motivated by a relayed audited failure, but its effectiveness remains a hypothesis. No model prose or private evidence was read here, and no claim is made that the same failure mechanism explains other cases. If a later audit finds adequate contemporary occurrence evidence with no accessible falsifier, this check cannot be credited with recovering an unavailable later correction. It may correct an inconsistent verdict without detecting the future factual error.

## Proposed literal suffix

The proposed placement is one exact suffix after unchanged Candidate 2, on harness `decompose` and `verify` instructions only. Direct, research prompts, schemas, evidence, eligibility, budgets, and verdict standards remain unchanged. Use existing notes/qualifiers/rationale fields and stay within Candidate 2's existing check limit; this adds no calls or required output keys.

```text
During decomposition, keep each fragment's proposition and attribution level
distinct from the original target; a fragment's status applies to its own
proposition. Before the final verdict, compare the unchanged original target
with the exact proposition your cited evidence and explanation establish. Do
not substitute “the source reports X” for a target asserting X happened, or
transfer a supported attribution fragment's status to a stronger real-world
target. Keep the target's scope and modality intact.

A supported verdict must agree with your stated evidence assessment for that
same target. If your explanation establishes only attribution, or explicitly
leaves a necessary part of the actual target unestablished, do not label the
stronger target supported. Either identify eligible evidence that resolves that
specific step and correct the explanation, or preserve unresolved for the
unsettled target. Acknowledge the narrower proposition that is established.
Contradict the target only when eligible evidence excludes it after the existing
scope and alternative checks; an unresolved step is not evidence of falsehood.

Do not turn this consistency check into blanket distrust. An adequate supplied
first-hand observation, record or derivation may support an ordinary occurrence
claim without a second independent source. Self-reporting, a single source, or
missing additional corroboration alone does not require unresolved. Distinguish
an optional confidence caveat from a necessary part of the target that your
assessment actually leaves unsettled. Preserve affirmative occurrence evidence
and settle an explicit attribution target when its wording is established.

Record only the brief evidence-to-target conclusion in existing notes or
rationale, with canonical citations. Keep the verdict and that conclusion
consistent. Add no output keys, calls or checks beyond the preceding limits,
and preserve all preceding evidence and temporal constraints.
```

This is a proposed evidential explanation requirement, not a new automatic verdict rule. It does not presume that every record is authentic, that every self-report is inadequate, that several sources are necessary, or that the selected claim is false. It contains no case identity, quantity, domain rule, later finding, or selected-label hint.

## Tests that could refute the hypothesis

First prereview entirely fictional evidence/target fixtures, with labels fixed independently of the candidate's outputs. Test matched targets over identical packets so that the intended distinction, rather than wording alone, changes what is being judged:

| Fixture contrast | Required distinction or safeguard |
|---|---|
| An explicit attribution target and a stronger occurrence target, with a passage clearly recording an unverified allegation | Attribution may be supported; the allegation's existence alone must not settle the stronger occurrence claim. The explicit evidential status, not the mere fact of self-reporting, drives the distinction. |
| An ordinary occurrence target with an adequate contemporaneous first-hand record matching its scope | Keep affirmative support without demanding a second source. This is the safeguard against blanket abstention. |
| Multiple retellings explicitly dependent on the same original record | Do not manufacture independent confirmation. Judge the original record's actual adequacy; dependence alone does not force unresolved. |
| A quantity or outcome explicitly presented as an estimate or forecast, compared with an attribution target about that estimate | Preserve modality. Establishing that an estimate was reported does not automatically establish the realized value. |
| Eligible evidence explicitly excluding the target, with the relevant scope and any benign alternative already determined in the fixture | A grounded contradiction remains available; the candidate must not convert every difficult case into abstention. |
| A source asserting the target plus an adequate supplied derivation or observation elsewhere | Use the affirmative evidence rather than stopping at the assertion or treating all source-authored evidence as circular. |
| An adequate occurrence record with an explicitly unavailable optional corroborating source, versus a record that explicitly leaves a necessary element unestablished | The optional caveat must not automatically downgrade support; the acknowledged necessary gap must not coexist with unsupported certainty. |

Syntax and placement tests can establish that the suffix is exact, appears only where intended, and leaves the baseline and schema unchanged. They cannot establish that a model made these distinctions or gained accuracy. A blinded semantic review must inspect the actual decisive citations and the evidence-to-target assessment, specifically whether supported is inconsistent with an expressly unestablished necessary part of the original target. Merely naming evidence types or replacing the rationale with stronger unsupported wording earns no substantive credit.

Following the relayed independent review of this failure, the already observed pilot may be reused only as an explicitly labeled development diagnostic. Even though this proposal is source-blind, its hypothesis was selected using that pilot's aggregate feedback; a rerun is not a new untouched holdout. Preserve the original results, retain every attempt, and freeze the next plan before any invocation. A broader claim requires additional independently admitted event families with labels and evidence settled before inference, rather than repeated selection on the same two outcomes.

Measure cutoff-evidence correctness first, with complete audited pipelines and every planned row in the denominator. Separately report later-false contradiction, later-false acceptance, abstention, conflict, failure, true-control acceptance and false accusation. A switch from unsupported acceptance to justified abstention can improve cutoff correctness when the fixed cutoff label is unresolved; it is not detection of the later falsehood. A future-correct false guess without cutoff grounding is not an accuracy win. A decrease in true-control acceptance or an increase in unsupported false accusations can refute the proposed safeguard even if later-false acceptance falls. Keep formal-only correctness diagnostic after a failed research stage and keep unknown usage unknown.

The hypothesis fails if the new explanation is decorative, the same unsupported inference persists, adequate true evidence is downgraded, or gains exist only on already exposed cases. If all independently justified cutoff labels were already achieved, explanation quality alone would not create score headroom; report that ceiling rather than claiming superiority. Here the reported one-of-two cutoff scores leave possible headroom and the independent semantic finding supplies a concrete inconsistency to target. Whether this candidate corrects it while preserving true-control support remains untested.

## Inputs used for this proposal

- Frozen Round 2 generic `GUIDANCE` from `experiments/prompt-iteration-20260909/round-2/run_test.py`; existing combined guidance SHA-256 `4c6936fe1e18426a00125a800fa98808bc583ccf7ef9b50d8af54773b866ef79`.
- Public `experiments/prompt-iteration-20260909/mixed-pilot-0735/PROTOCOL.md`.
- Parent-provided aggregate counts and the later source-free summary of the independent semantic audit stated above.

No additional evidence, private labels, model prose, network retrieval, or model call was used.
