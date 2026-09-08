# FactCircuit

> **Trace every claim. Close the evidence loop.**

[![Policy tests](https://github.com/superwesleyhys-ux/factcircuit/actions/workflows/ci.yml/badge.svg)](https://github.com/superwesleyhys-ux/factcircuit/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Research preview](https://img.shields.io/badge/status-research_preview-orange.svg)](#project-status)

**FactCircuit turns claim verification from a one-shot label into a replayable
evidence circuit.** Most verification systems return an answer. FactCircuit
preserves the path: immutable source versions, exact evidence
spans, staged semantic checks, unresolved gaps, bounded retrieval tasks, stop
reasons, hashes, and resource usage.

It is an MIT-licensed, adapter-driven Python harness for building and evaluating
auditable verification loops over changing news evidence. The standard-library
core runs offline; the optional model adapter adds a seven-stage validation loop
with deterministic Python assembly and fail-closed contracts.

## Why FactCircuit?

News verification fails in ways that a final `true` or `false` label cannot
show. URLs are revised. Syndicated stories look independent. A nearby number,
date, negation, or actor can silently attach to the wrong event. A retrieval
loop can also forget why it searched, reuse stale feedback, or leak material
published after the evaluation cutoff.

FactCircuit makes those failure surfaces explicit:

- **Evidence is versioned, not overwritten.** Same-URL revisions retain
  separate identities, exact source spans, timestamps, and content hashes.
- **Every material return is decomposed.** A document cannot influence the
  evidence graph merely because a retriever found it.
- **Evidence and reality are judged separately.** “Does this snapshot support
  the claim?” is isolated from “Did the event happen in the world?”
- **One giant prompt does not control the pipeline.** Seven single-purpose
  stages handle atoms, lineage, critics, evidence, and world assessment; Python
  validates and assembles the final judgement.
- **Uncertainty becomes work.** Missing information is emitted as an exact
  fetch, search, or reanalysis task and re-enters the same bounded loop.
- **Bad state fails closed.** Invalid schemas, ungrounded spans, duplicate
  probes, stale task receipts, cross-event bindings, and exhausted budgets are
  recorded instead of being partially committed.
- **Evaluation is a first-class feature.** Fixed targets, cutoff checks, gold
  isolation, paired comparisons, bootstrap intervals, and machine-readable
  traces are part of the harness rather than an afterthought.

## The loop

```text
Frozen claim + evidence cutoff
             │
             ▼
    Deterministic TargetPlan
             │
             ▼
retrieval → immutable snapshot → cutoff admission
   ▲                                  │
   │                                  ▼
   │                    atoms → lineage → decomposition critic
   │                                  │
   │                                  ▼
   │                       atomic Python assembly
   │                                  │
   │                    ┌─────────────┴─────────────┐
   │                    ▼                           ▼
   │                 evidence                    world
   │                    ▼                           ▼
   │             evidence critic              world critic
   │                    └─────────────┬─────────────┘
   │                                  ▼
   └──── exact unresolved tasks ← decision + audit trace
                   bounded by rounds, calls, output, and time
```

The graph keeps source lineage distinct from semantic support or contradiction.
Finding ten copies of one wire story therefore does not become ten independent
sources, and finding a contradiction does not magically identify the original
publisher.

## Early evidence: original vs PR1

The repository includes a frozen historical comparison using propositions made
in 2023 and official outcome evidence available by the end of 2024. On the
completed two-case post-hoc pilot, the PR1 staged loop resolved both
propositions correctly while the original monolithic loop resolved one:

| Frozen pilot | Original monolithic | PR1 staged |
| --- | ---: | ---: |
| Accuracy | 1/2 (50%) | **2/2 (100%)** |
| True-claim recall | 0/1 | **1/1** |
| False-claim recall | 1/1 | **1/1** |
| Abstention | 1/2 | **0/2** |
| Model calls | 6 | 33 |
| Total tokens | 15,693 | 49,804 |

This is a promising engineering signal, not a population-level accuracy claim.
The pair contains only two retrospectively selected cases. PR1 used 5.5× as
many model calls and 3.17× as many total tokens, so the result does not isolate
prompt structure from compute. A separate Lucid full-evidence diagnostic also
exposed a staged-path error and left the overall run status as `has_errors`;
that control is excluded from the two scored main cases but is retained in the
public artifacts.

Read the [human summary](reports/historical-2023-pilot2-v3-live-001/SUMMARY.md)
or inspect the [machine-readable scores](reports/historical-2023-pilot2-v3-live-001/scores.json),
raw calls, retrieval records, traces, frozen inputs, and checksums.

## Quick start

Python 3.11 or newer is required. The core has no runtime dependency outside
the standard library.

```bash
git clone https://github.com/superwesleyhys-ux/factcircuit.git
cd factcircuit
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .

python3 -m factcircuit trace-demo --output reports/trace-demo-local.json
python3 -m unittest discover -s tests -v
```

The trace demo follows four material versions across three retrieval rounds,
reopens affected earlier analyses, routes a correction through decomposition,
and records why the loop terminates.

### Score and compare fixed predictions

```bash
python3 -m factcircuit score \
  examples/evaluation_gold.json \
  examples/evaluation_predictions.json \
  --output reports/all-metrics-local.json

python3 -m factcircuit compare \
  examples/evaluation_gold.json \
  examples/comparison_baseline.json \
  examples/comparison_candidate.json \
  --bootstrap-samples 100 \
  --seed 0 \
  --output reports/comparison-local.json
```

These bundled predictions are deliberately imperfect handwritten fixtures for
checking arithmetic. They are not model-performance results.

### Audit the historical cutoff contract

This step is offline and does not call a model or open the web:

```bash
python3 experiments/historical_compare.py audit \
  --inputs experiments/historical-2023-pilot2-v3/inputs.json \
  --sources experiments/historical-2023-pilot2-v3/sources.json \
  --freeze experiments/historical-2023-pilot2-v3/freeze.json \
  --gold experiments/historical-2023-pilot2-v3/gold.json \
  --output reports/historical-2023-audit-local.json
```

### Re-execute archived comparisons locally

This source-checkout command runs the current verification code against saved
model responses. It requires no API key, SDK, network connection, or local model.
It is deterministic response replay and does not generate new model answers.

```bash
python3 experiments/local_replay.py \
  --archive reports/historical-2023-pilot2-v3-live-001 \
  --inputs experiments/historical-2023-pilot2-v3/inputs.json \
  --sources experiments/historical-2023-pilot2-v3/sources.json \
  --freeze experiments/historical-2023-pilot2-v3/freeze.json \
  --gold experiments/historical-2023-pilot2-v3/gold.json \
  --output reports/local-replay-my-run
```

API status is `not_used` with zero requests. `execution_status` reports whether
the archived calls could be replayed; `verification_status` separately retains
semantic failures. This pilot replays all six case/arm/control combinations,
including the known staged Lucid full-evidence error. Exit code 1 means replay
or verification errors were retained; exit code 2 means setup or archive
validation failed. Use a fresh output directory for each run.

Call hashes and exact requests are checked before accepting saved responses.
Optional gold labels are opened after replay, and scores are explicitly marked
`archived_response_replay`. They do not constitute a new accuracy measurement.
An invalid API key cannot block this local path. Fresh model inference still
requires a separately configured model runtime.

### Run a model-backed comparison

The experimental runtime is source-checkout-only. Install the pinned optional
dependencies and provide `OPENAI_API_KEY` through the process environment—never
through a tracked file:

```bash
python3 -m pip install -e '.[model]'

python3 experiments/loop_compare.py run \
  --inputs experiments/inputs-v03.json \
  --output reports/my-run \
  --model MODEL_NAME \
  --semantic-mode staged \
  --max-repairs 1 \
  --max-rounds 5
```

Use `--semantic-mode monolithic --max-repairs 0` for the earlier adapter. The
two modes have separate caches and different internal repair budgets; compare
their resource use as well as their scores.

## Integration surface

The core entry point is:

```python
from factcircuit.provenance import run_provenance

run_provenance(target, provider, decomposer=None, verifier=None, config=None)
```

Typed provider, decomposer, and verifier contracts are documented in
[`docs/TRACE_ADAPTER.md`](docs/TRACE_ADAPTER.md). A tracker supplies claims and
retrieved snapshots; the harness returns a decision, provenance graph,
reanalysis history, unresolved gaps, resource accounting, and termination
reason. It does not require a particular search engine, model, or publisher
ranking policy.

## Evaluation toolkit

Gold labels and predictions live in separate files. Missing, extra, or
duplicate target IDs; cutoff mismatches; unjudged evidence; and malformed
probability vectors fail validation.

| Metric | What it measures |
| --- | --- |
| VP | Precision of claims admitted to a trusted feed |
| FR | Fraction of false claims withheld |
| TR | Fraction of true claims admitted |
| SR | Correct original-root sets with valid provenance paths |
| EN | Precision of evidence asserted to support a target |
| CA | Probability quality using a normalized four-class Brier score |
| HFAR | High-risk false claims incorrectly admitted |

The scorer also reports source precision, evidence recall, edge
precision/recall, duplicate-pair F1, confusion matrices, coverage, ECE, and an
experimental `NVScore`. Scores measure agreement with supplied gold; they do
not establish truth by themselves.

## Project status

Version 0.3.1 is a **research preview**, not a production fact-checking service.
The release gate contains 254 regression tests, and GitHub Actions exercises
Python 3.11, 3.12, and 3.13. The core CLI, offline trace engine,
evaluation toolkit, staged model adapter, frozen historical corpus, and raw
pilot artifacts are included.

### Name and compatibility

Version 0.3.1 renames the project and Python distribution from Accuracy
Tracing / NewsVerify Harness to **FactCircuit**. New integrations should use
the `factcircuit` import package and command. The existing `newsverify` imports
and command remain supported as compatibility entry points, and the original
v0.2/v0.3 reports retain their historical names and contents.

Current boundaries are deliberate and visible:

- The bundled provider searches supplied snapshots; it does not browse the open
  web or authenticate remote pages independently.
- Present-day model weights cannot be rolled back to an earlier knowledge
  cutoff. The historical harness isolates supplied evidence, not model memory.
- Internal hashes prove repository consistency, not third-party authenticity of
  a remote source or API response.
- The staged adapter remains experimental and has a known full-evidence control
  failure documented in the pilot report.
- The current real-source result is far too small and too post-hoc for a general
  accuracy claim. A blind, event-separated benchmark and equal-compute ablation
  remain roadmap work.

## Documentation

- [FactCircuit specification index](docs/FACTCIRCUIT_SPEC.md)
- [Original design specification and metric definitions](docs/ACCURACY_TRACING_SPEC.md)
- [Staged validation loop](docs/STAGED_VALIDATION_LOOP.md)
- [Trace adapter API](docs/TRACE_ADAPTER.md)
- [Historical 2023 benchmark contract](docs/HISTORICAL_2023_BENCHMARK.md)
- [v0.3.1 validation record](reports/VALIDATION_V0.3.1.md)
- [v0.3 repair and migration contract](docs/REPAIR_V0.3.md)
- [Roadmap](docs/ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Community

Small, reproducible contributions are welcome. Start with
[`CONTRIBUTING.md`](CONTRIBUTING.md), open an issue for a defect or proposal, or
use the dedicated [Accuracy decline discussion category](https://github.com/superwesleyhys-ux/factcircuit/discussions/categories/accuracy-decline)
to report a measurable regression with its corpus, configuration, budgets, and
trace artifacts.

Security-sensitive findings should follow [`SECURITY.md`](SECURITY.md) rather
than being posted with credentials or private data.

## License

Released under the [MIT License](LICENSE). Use it, inspect it, challenge it, and
help make evidence-driven AI systems easier to audit.
