# NewsVerify Harness: project brief

## Purpose

News trackers often retrieve, rank, and summarize stories. NewsVerify Harness adds a repeatable check between retrieval and downstream use: does a specific claim have eligible evidence, what conflicts with it, what is missing, and why did the system stop searching?

The research question is whether targeted re-retrieval improves claim verification compared with a single pass under the same evidence budget. The starter provides an inspectable policy engine and fixtures for developing that experiment. It does not yet answer the research question.

## Relationship to the earlier project

The author previously described a news-tracking system associated with AGIPOT. Its source repository and revision were not available when this starter was created. No historical implementation, private data, API integrations, or model weights are included or claimed to have been recovered.

The intended integration is narrow: the existing tracker produces candidate claims and retrieves documents; an adapter converts those outputs to the harness contract. The harness returns a policy decision and audit record that the tracker can display, queue for review, or revisit when evidence changes. Integration is pending access to and inspection of the actual tracker.

## Public project boundary

| Component | Current starter | Planned extension |
| --- | --- | --- |
| Claims | One supplied claim with a time cutoff | Claim extraction and entity/event normalization |
| Retrieval | Deterministic fixture provider | Live feed/search adapters and archived replay |
| Evidence checks | Citation-field, quote-presence, timestamp, and duplication checks | Publisher lineage, source corrections, semantic entailment review |
| Loop | Bounded search rounds with a requested search intent | Measured query selection and provider execution |
| Decision | Supported, contradicted, conflicting, or unresolved | Calibrated models only if justified by labeled data |
| Evaluation | Synthetic policy regression cases | Blind, event-separated and time-separated news evaluation |

An existing tracker's credentials, user accounts, subscriptions, proprietary ranking, and deployment remain outside this reusable package. A future public adapter should expose a configuration contract without bundling secrets or private datasets.

## Evidence flow

The input is an atomic claim and `as_of` time. A provider returns evidence. Mechanical checks admit or reject each record, then provenance groups prevent related documents from inflating independent source counts. The next search intent follows the remaining gaps or disagreement. The loop ends with a logged reason when its policy or resource limits require it.

The loop changes which evidence is requested. It does not repeatedly train a model, update weights, or treat repeated agreement from the same model as fresh evidence. Stance labels and provenance metadata remain explicit external judgments in this version.

## Definition of a useful public release

A contributor should be able to run the demonstration offline, understand every decision from its audit output, reproduce policy cases, and implement a provider without receiving the author's private tracker. The README and release notes should say exactly which checks are mechanical and which annotations are trusted.

The first release should establish those capabilities. Claims about accuracy improvements, adoption, or ecosystem impact require later measurements and public evidence.
