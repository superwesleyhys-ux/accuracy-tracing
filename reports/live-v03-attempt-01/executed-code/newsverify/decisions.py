"""Deterministic final presentation shared by single-pass and loop experiments."""
from copy import deepcopy

LABELS = {"supported": "true", "contradicted": "false", "conflicting": "disputed",
          "unresolved": "unverifiable", "not_checked": "unverifiable"}


def present_decision(report):
    """Do not spend another model call silently changing a previously audited verdict."""
    mode = report["target"]["assessment_mode"]
    valid = report.get("assessment_valid", False) and not report["errors"]
    selected = report["decision_status"] if valid else "unresolved"
    return {"id": report["target"]["id"], "assessment_mode": mode,
            "as_of": report["target"]["as_of"], "decision": LABELS[selected],
            "assessments": deepcopy(report["assessments"]),
            "provenance_status": report["provenance_status"],
            "assessment_valid": bool(valid), "stop_reason": report["stop_reason"]}


def round_decisions(report):
    """Actual completed round checkpoints, with the same mapping as final output."""
    return [{"round": event["round"], "id": report["target"]["id"],
             "decision": LABELS[event["decision"]],
             "assessment_mode": report["target"]["assessment_mode"],
             "assessments": deepcopy(event["assessments"]),
             "provenance_status": event["provenance_status"]}
            for event in report["operations"] if event["action"] == "verification_completed"]
