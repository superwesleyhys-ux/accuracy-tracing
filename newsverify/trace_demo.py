"""Synthetic annotated replay demonstrating both loops; not an accuracy study."""

from dataclasses import replace

from .provenance import (
    Analysis, Fragment, Gap, MaterialVersion, OriginFinding, Relation,
    ReplayTraceProvider, Resolution, Span, Target, TraceConfig, VerificationResult,
    run_provenance,
)


def _full(material):
    return Span(material.version_id, 0, len(material.content), material.content)


class AnnotatedDemoDecomposer:
    """Fixture-specific semantic annotations, deliberately not general NLP."""

    def __init__(self, materials):
        self.materials = {item.version_id: item for item in materials}

    def decompose(self, target, material, context):
        known = {item["version_id"] for item in context["materials"]} | {material.version_id}
        fragment = Fragment(material.version_id + ":statement", material.content,
                            _full(material), target.id)
        if material.version_id == "headline:v1":
            upstream = "dispatch:v1" if "dispatch:v1" in known else None
            edge = Relation("headline-to-dispatch", material.version_id, upstream, "cites",
                            "direct" if upstream else "declared", (_full(material),),
                            "The headline explicitly names the dispatch; availability is tracked separately.",
                            "https://dispatch.example/report")
            return Analysis(fragments=(fragment,), relations=(edge,), gaps=(
                Gap("dispatch", "Retrieve the dispatch named in the headline"),
            ) if upstream is None else ())
        if material.version_id == "dispatch:v1":
            upstream = "minutes:v1" if "minutes:v1" in known else None
            edge = Relation("dispatch-to-minutes", material.version_id, upstream, "cites",
                            "direct" if upstream else "declared", (_full(material),),
                            "The dispatch explicitly attributes the figure to meeting minutes.",
                            "https://records.example/meeting")
            return Analysis(fragments=(fragment,), relations=(edge,), gaps=(
                Gap("minutes", "Retrieve the meeting record and determine what 30% modifies"),
            ) if upstream is None else (), resolutions=(
                Resolution("dispatch", (_full(material),), "Located the explicitly named dispatch version."),
            ), revisit_versions=("headline:v1",) if "headline:v1" in known and not context["analyses"].get(material.version_id) else ())
        if material.version_id == "minutes:v1":
            qualifiers = ("discussing", "next year", "ceiling", "external-services budget")
            return Analysis(fragments=(replace(fragment, qualifiers=qualifiers),), resolutions=(
                Resolution("minutes", (_full(material),), "Located the producing meeting record."),
                Resolution("origin:" + target.id, (_full(material),),
                           "The fixture explicitly links the headline through the dispatch to this record."),
            ), origins=(OriginFinding(target.id, material.version_id, (_full(material),),
                                      "original_record", "Synthetic annotated meeting record is the producing source of the cited figure."),),
                notes="The original is about a future budget ceiling; the target remains an already-completed staff-cut claim.",
                revisit_versions=("dispatch:v1",))
        if material.version_id == "headline:v2":
            return Analysis(fragments=(fragment,), relations=(Relation(
                "correction-contradicts-headline", material.version_id, "headline:v1", "contradicts",
                "direct", (_full(material),), "Semantic contradiction is kept separate from citation lineage."
            ),), notes="Verification requested this correction; it entered psi before verification.")
        raise ValueError("Unknown synthetic fixture material")


class AnnotatedDemoVerifier:
    """Deterministic replay verdicts provided by the fixture's manual annotations."""

    def __init__(self, materials):
        self.materials = {item.version_id: item for item in materials}

    def verify(self, target, context):
        known = {item["version_id"] for item in context["materials"]}
        if "minutes:v1" not in known:
            return VerificationResult(rationale="Awaiting the producing record.")
        if "headline:v2" not in known:
            return VerificationResult(rationale="Budget wording does not establish whether staff cuts occurred; seek a correction.",
                gaps=(Gap("verification:staff", "Find the publisher correction or direct record of implemented staff cuts", "verification"),))
        correction = _full(self.materials["headline:v2"])
        return VerificationResult("contradicted", (correction,),
            "Synthetic correction explicitly says the reported staff cut did not occur.",
            resolutions=(Resolution("verification:staff", (correction,), "Correction addresses the outstanding implemented-cuts question."),))


def build_demo() -> dict:
    """Return keyword arguments accepted by run_provenance; no external I/O."""
    target = Target("staff-cut", "Northstar has already cut 30% of staff.", "2026-09-04T20:00:00Z", "headline:v1")
    def material(version_id, url, content, date):
        return MaterialVersion(version_id, url, content, "2026-09-05T01:00:00Z",
            date, date, "Synthetic fixture asserts the exact version was archived at this time.", "synthetic-publisher")
    headline = material("headline:v1", "https://news.example/headline",
        "Northstar has already cut 30% of staff. Source: https://dispatch.example/report", "2026-09-04T12:00:00Z")
    dispatch = material("dispatch:v1", "https://dispatch.example/report",
        "Northstar plans to cut 30% of staff. Source: https://records.example/meeting", "2026-09-04T11:00:00Z")
    minutes = material("minutes:v1", "https://records.example/meeting",
        "Meeting record: discussing next year's external-services budget; reduction ceiling 30%.", "2026-08-01T09:00:00Z")
    correction = material("headline:v2", "https://news.example/headline",
        "Correction: no staff cuts have been implemented. The earlier 30% figure was a proposed ceiling for next year's external-services budget.", "2026-09-04T18:00:00Z")
    materials = (headline, dispatch, minutes, correction)
    return {"target": target, "provider": ReplayTraceProvider(((headline,), (dispatch, minutes), (correction,))),
            "decomposer": AnnotatedDemoDecomposer(materials), "verifier": AnnotatedDemoVerifier(materials),
            "config": TraceConfig(max_rounds=4, max_documents=12, max_decomposition_calls=20)}


def run_demo() -> dict:
    report = run_provenance(**build_demo())
    report["evaluation_mode"] = "synthetic_annotated_replay"
    report["accuracy_claim"] = "None. This demonstrates orchestration contracts, not real-news accuracy."
    return report
