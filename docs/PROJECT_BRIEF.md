# Accuracy Tracing: project brief

## Purpose

Accuracy Tracing is an open-source verification harness for systems that need
more than a final label. Given a fixed claim and evidence cutoff, it records
which source versions were eligible, which exact spans supported or
contradicted the target, how sources relate, what remained unresolved, which
retrieval tasks were issued, and why the process stopped.

The core research question is whether bounded, task-directed re-retrieval and
staged semantic validation improve claim verification over a monolithic pass
without hiding the additional cost or failure modes. Version 0.3.0 supplies the
runtime, evaluation contracts, frozen historical corpus, and an initial
two-case comparison. It does not yet answer that question at population scale.

## What is public in 0.3.0

| Component | Included now | Next evidence needed |
| --- | --- | --- |
| Claims | Fixed atomic targets with explicit cutoffs and deterministic target plans | Independently sampled, blinded claim set |
| Retrieval | Typed providers, supplied-snapshot search, exact task attribution, bounded rounds | One production live provider with archived replay |
| Provenance | Immutable versions, exact spans, lineage candidates, revision history, content hashes | Independent remote-artifact authentication |
| Semantics | Monolithic compatibility adapter plus seven-stage validation loop and critics | Broader multilingual and adversarial evaluation |
| Decisions | Separate evidence/world assessments and deterministic final mapping | Calibrated confidence backed by held-out data |
| Evaluation | Fixed gold schemas, paired comparisons, bootstrap support, resource accounting | Event- and time-separated benchmark at useful scale |
| Historical testing | Eight frozen 2023 propositions; two completed live comparison cases | Preregistered full set and equal-compute ablations |

## Why the loop is different

Each retrieved material version is saved and admitted against the evidence
cutoff before it can affect the graph. Eligible material is decomposed into
atomic observations and lineage claims. Evidence entailment and world-state
assessment then run through separate stage/critic pairs. Python rejects
malformed, duplicated, ungrounded, or cross-event outputs and atomically
assembles the accepted state.

Unresolved probes are converted to exact fetch, search, or reanalysis tasks.
New material re-enters the same path, and earlier analyses affected by a
revision are reopened without erasing history. Every run has explicit round,
material, call, output, and wall-time bounds.

## Relationship to a news tracker

The integration boundary is narrow. A news tracker can produce candidate
claims and retrieved documents; an adapter converts those outputs to the
harness contract. Accuracy Tracing returns a policy decision and audit record
that the tracker can display, queue for review, or revisit when evidence
changes.

Credentials, subscriptions, private feeds, proprietary ranking, user accounts,
and deployment infrastructure remain outside this repository. The public
package does not claim to reconstruct or include any earlier private tracker.

## Evidence to date

The offline core and staged contracts are covered by 250 passing tests, with CI
on Python 3.11–3.13. In the frozen two-case historical pilot, the original
monolithic adapter scored 1/2 and the staged adapter scored 2/2. The staged arm
used substantially more calls and tokens, the cases were selected post-hoc,
and a separate full-evidence staged diagnostic failed. The result is therefore
an early engineering signal, not proof of a general accuracy gain.

## Definition of success

The project succeeds when an independent contributor can:

1. reproduce an offline trace and understand every transition;
2. plug in a permitted evidence provider without changing decision policy;
3. run a fixed, leakage-audited comparison with gold unavailable to inference;
4. inspect all failures, exclusions, resource use, and termination reasons; and
5. challenge a reported improvement using the same public artifacts.

Claims about general accuracy, adoption, or ecosystem impact require larger
preregistered measurements and public evidence. The harness is designed to make
that standard practical rather than to bypass it.
