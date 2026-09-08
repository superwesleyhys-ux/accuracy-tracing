"""Write a self-contained, offline walkthrough of the provenance loop."""

from dataclasses import asdict
import json
from pathlib import Path

from .provenance import TraceConfig, run_provenance
from .trace_demo import build_demo


def run_quickstart(output: Path, config: dict | None = None) -> dict:
    """Run annotated fixture adapters and preserve inputs, budgets and results.

    The output directory must be new. No model, network or credential is used.
    Only resource budgets are configurable; the fixture's semantic annotations
    are supplied by the adapters in trace_demo.py.
    """
    output = Path(output)
    if output.exists():
        raise ValueError("output directory already exists; choose a new directory")
    demo = build_demo()
    if config is not None:
        if not isinstance(config, dict):
            raise ValueError("quickstart config must be a JSON object")
        allowed = set(asdict(demo["config"]))
        if set(config) - allowed:
            raise ValueError("unknown quickstart config key")
        if any(type(value) is not int or value < 1 for value in config.values()):
            raise ValueError("quickstart budgets must be positive integers")
        demo["config"] = TraceConfig(**{**asdict(demo["config"]), **config})
    inputs = {
        "evaluation_mode": "synthetic_annotated_replay",
        "target": asdict(demo["target"]),
        "rounds": [[asdict(item) for item in items]
                   for items in demo["provider"].rounds],
        "annotations": "Fixture-specific decomposer and verifier in newsverify/trace_demo.py; not model predictions.",
    }
    trace = run_provenance(**demo)
    trace["evaluation_mode"] = "synthetic_annotated_replay"
    trace["accuracy_claim"] = "None. This demonstrates orchestration contracts, not real-news accuracy."
    trace["model_api_calls"] = 0
    trace["new_model_inference"] = False
    summary = "\n".join([
        "# FactCircuit first run", "",
        "This fictional example uses hand-authored semantic annotations. It runs",
        "the provenance loop offline, with zero model calls. It is not an accuracy test.", "",
        f"Claim: {demo['target'].text}", "",
        "| Result | Value |", "| --- | --- |",
        f"| Fact status | {trace['fact_status']} |",
        f"| Provenance | {trace['provenance_status']} |",
        f"| Stop reason | {trace['stop_reason']} |",
        f"| Assessment valid | {str(trace['assessment_valid']).lower()} |",
        f"| Retrieval rounds | {trace['usage']['rounds']} |",
        f"| Material versions | {trace['usage']['unique_versions']} |", "",
        "With the default budgets, the loop follows a headline through a dispatch",
        "to meeting minutes, then reads a correction. The correction says the staff",
        "cut did not happen: the percentage referred to a proposed budget ceiling.",
        "With smaller budgets, the loop may stop before obtaining that correction.", "",
        "- `inputs.json`: fictional claim, evidence snapshots and retrieval order.",
        "- `config.json`: the exact resource budgets used for this run.",
        "- `trace.json`: evidence spans, lineage, reanalysis, decisions and errors.", "",
        "To rerun with different budgets, pass this config.json to",
        "`python -m factcircuit quickstart --config PATH --output NEW_DIRECTORY`.",
        "Changing inputs.json does not change this built-in fixture. For your own",
        "claims, use the model-backed source-checkout workflow or adapter API in",
        "https://github.com/superwesleyhys-ux/factcircuit/blob/v0.3.2/docs/QUICKSTART.md.", "",
    ])
    # Validate and render everything before creating a new output directory.
    payloads = {
        "inputs.json": inputs,
        "config.json": asdict(demo["config"]),
        "trace.json": trace,
    }
    rendered = {name: json.dumps(value, ensure_ascii=False, indent=2,
                                allow_nan=False) + "\n"
                for name, value in payloads.items()}
    output.mkdir(parents=True, exist_ok=False)
    for name, content in rendered.items():
        (output / name).write_text(content, encoding="utf-8")
    (output / "SUMMARY.md").write_text(summary, encoding="utf-8")
    return trace
