"""Regression cases for the observed failure mechanisms; no real-news accuracy claims."""
from dataclasses import replace
import unittest

from newsverify.provenance import (Analysis, Fragment, Gap, MaterialVersion, OriginFinding,
    ReplayTraceProvider, Relation, Resolution, RetrievalHit, Span, Target, TraceConfig,
    VerificationResult, run_provenance)
from newsverify.decisions import present_decision, round_decisions
from newsverify.retrieval import SnapshotSearchProvider


def document(id="notice", content="The bridge remains closed."):
    return MaterialVersion(id, "https://example.org/" + id, content,
        "2026-09-04T20:00:00Z", "2026-09-04T10:00:00Z", "2026-09-04T10:00:00Z", "Fixture snapshot")


def span(doc): return Span(doc.version_id, 0, len(doc.content), doc.content)


class Psi:
    def __init__(self, fn): self.fn = fn
    def decompose(self, *args): return self.fn(*args)


class Verify:
    def __init__(self, fn): self.fn = fn
    def verify(self, *args): return self.fn(*args)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.doc = document()
        self.target = Target("claim", "The bridge has reopened.", "2026-09-04T20:00:00Z",
                             assessment_mode="evidence", evidence_scope=("notice",))

    def run_check(self, check, mode="evidence"):
        return run_provenance(replace(self.target, assessment_mode=mode), ReplayTraceProvider(((self.doc,),)),
                              verifier=Verify(lambda *_: check))

    def gap(self, dimension="world", blocking=True, **changes):
        return replace(Gap("g", "Check actual bridge condition", "verification", dimension,
            blocking, "claim", (span(self.doc),), "Could change the actual-world claim", "search", "bridge actual condition"), **changes)

    def check(self, gaps=(), evidence="contradicted", world="unresolved"):
        return VerificationResult("unresolved", (span(self.doc),), "Notice contradicts reopening", gaps,
            evidence_verdict=evidence, world_verdict=world,
            world_basis=(span(self.doc),) if world != "unresolved" else (),
            world_rationale="Fixture world annotation" if world != "unresolved" else "No world authentication")

    def test_world_gap_does_not_erase_contradicting_evidence(self):
        report = self.run_check(self.check((self.gap(),)))
        self.assertEqual("contradicted", report["assessments"]["evidence"]["raw_verdict"])
        self.assertEqual("false", present_decision(report)["decision"])
        self.assertEqual("unresolved", report["fact_status"])

    def test_conflict_is_preserved_alongside_unknown_world_state(self):
        report = self.run_check(self.check((self.gap(),), evidence="conflicting"))
        self.assertEqual("disputed", present_decision(report)["decision"])
        self.assertEqual("unresolved", report["assessments"]["world"]["decision"])

    def test_critical_world_gap_still_blocks_a_positive_world_claim(self):
        report = self.run_check(self.check((self.gap(),), world="supported"), mode="world")
        self.assertEqual("unverifiable", present_decision(report)["decision"])
        self.assertEqual("supported", report["assessments"]["world"]["raw_verdict"])

    def test_nonblocking_gap_does_not_blanket_override(self):
        report = self.run_check(self.check((self.gap(blocking=False),), world="supported"), mode="world")
        self.assertEqual("true", present_decision(report)["decision"])

    def test_critical_evidence_gap_blocks_only_evidence_decision(self):
        report = self.run_check(self.check((self.gap(dimension="evidence"),)))
        self.assertEqual("unverifiable", present_decision(report)["decision"])
        self.assertEqual("contradicted", report["assessments"]["evidence"]["raw_verdict"])

    def test_unjustified_explicit_blocking_gap_is_rejected(self):
        report = self.run_check(self.check((self.gap(basis=()),)))
        self.assertEqual("verifier_error", report["stop_reason"])

    def test_gap_for_another_target_is_rejected(self):
        report = self.run_check(self.check((self.gap(target_id="another"),)))
        self.assertEqual("verifier_error", report["stop_reason"])

    def test_duplicate_gap_ids_fail_closed_in_either_order(self):
        evidence = self.gap(dimension="evidence", blocking=True)
        world = replace(self.gap(dimension="world", blocking=False),
                        question="Check world state")
        for gaps in ((evidence, world), (world, evidence)):
            with self.subTest(order=[gap.dimension for gap in gaps]):
                report = self.run_check(self.check(gaps, evidence="supported"))
                self.assertEqual("verifier_error", report["stop_reason"])
                self.assertFalse(report["assessment_valid"])

    def test_shared_gap_owner_cannot_weaken_another_live_owner(self):
        first, second = document("a"), document("b")
        shared = Gap(
            "shared", "Check the frozen record", "verification", "evidence",
            True, self.target.id, (span(first),), "Could change evidence.",
            "search", "bridge record")
        seen_a = []

        def decompose(target, material, context):
            if material.version_id == "a":
                seen_a.append(1)
                return Analysis(gaps=(shared if len(seen_a) == 1
                                      else replace(shared, blocking=False),))
            return Analysis(gaps=(shared,))

        report = run_provenance(
            replace(self.target, evidence_scope=("a",)),
            ReplayTraceProvider(((first, second), (first,))),
            Psi(decompose), config=TraceConfig(max_rounds=2))
        self.assertEqual("decomposer_error", report["stop_reason"])
        self.assertEqual(2, len(report["analysis_history"]))
        self.assertTrue(all(
            analysis["gaps"][0]["blocking"]
            for analysis in report["analyses"].values()))

    def test_verifier_cannot_weaken_its_active_gap_without_resolution(self):
        gap = self.gap(dimension="evidence", blocking=True,
                       locator="bridge record")
        provider = SnapshotSearchProvider([self.doc], [self.doc.version_id])
        calls = []

        class StatefulVerifier:
            uses_retrieval_feedback = True

            def verify(self, target, context):
                calls.append(1)
                current = gap if len(calls) == 1 else replace(gap, blocking=False)
                return self_check((current,), evidence="supported")

        self_check = self.check
        report = run_provenance(
            self.target, provider, verifier=StatefulVerifier(),
            config=TraceConfig(max_rounds=2))
        self.assertEqual("verifier_error", report["stop_reason"])
        self.assertFalse(report["assessment_valid"])

    def test_failed_candidate_projection_commits_no_partial_analysis(self):
        target = replace(self.target, source_version_id="missing-source")

        def decompose(target, material, context):
            return Analysis(
                gaps=(Gap("lineage:" + target.id, "Conflicting custom lineage task"),),
                origins=(OriginFinding(
                    target.id, material.version_id, (span(material),),
                    "original_record", "Fixture role."),))

        report = run_provenance(
            target, ReplayTraceProvider(((self.doc,),)), Psi(decompose))
        self.assertEqual("decomposer_error", report["stop_reason"])
        self.assertEqual([], report["eligible_version_ids"])
        self.assertEqual({}, report["analyses"])
        self.assertEqual([], report["analysis_history"])

    def test_independent_resolutions_of_same_gap_merge_basis(self):
        first, second = document("a"), document("b")

        def decompose(target, material, context):
            return Analysis(resolutions=(Resolution(
                "origin:" + target.id, (span(material),),
                "Resolved from " + material.version_id),))

        report = run_provenance(
            replace(self.target, evidence_scope=()),
            ReplayTraceProvider(((first, second),)), Psi(decompose))
        self.assertEqual([], report["errors"])
        resolution = next(item for item in report["resolutions"]
                          if item["gap_id"] == "origin:" + self.target.id)
        self.assertEqual({"a", "b"},
                         {item["version_id"] for item in resolution["basis"]})

    def test_newer_cross_material_gap_reopens_an_older_resolution(self):
        first, second = document("a"), document("b")
        target = replace(self.target, source_version_id="a", evidence_scope=())
        initial = Gap(
            "origin:" + target.id,
            "Find the producing record and evidenced lineage for: " + target.text)

        def decompose(target, material, context):
            if material.version_id == "a":
                return Analysis(
                    resolutions=(Resolution(
                        initial.id, (span(material),),
                        "The first material was initially treated as original."),),
                    origins=(OriginFinding(
                        target.id, material.version_id, (span(material),),
                        "original_record", "Fixture original role."),))
            return Analysis(gaps=(initial,))

        report = run_provenance(
            target, ReplayTraceProvider(((first, second),)), Psi(decompose),
            config=TraceConfig(max_rounds=1))
        self.assertNotEqual("complete", report["stop_reason"])
        self.assertEqual("partial", report["provenance_status"])
        self.assertIn(initial.id, {item["id"] for item in report["gaps"]})

    def test_strict_staged_contract_rejects_unattributed_later_return(self):
        second = document("second")

        class Strict:
            requires_task_attribution = True

            def decompose(self, target, material, context):
                return Analysis(gaps=(Gap(
                    "next", "Find the next bridge record", action="search",
                    locator="bridge record"),))

        report = run_provenance(
            self.target, ReplayTraceProvider(((self.doc,), (second,))),
            Strict(), config=TraceConfig(max_rounds=2))
        self.assertEqual("provider_error", report["stop_reason"])
        self.assertEqual(1, len(report["analysis_history"]))

    def test_lazy_provider_can_carry_exact_attribution_in_each_hit(self):
        second = document("second")
        receipts = []

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search(self, target, tasks, round_number, limit):
                if round_number == 1:
                    self.last_feedback = []
                    yield self_doc
                else:
                    task = next(item for item in tasks if item.id == "next")
                    self.last_feedback = [{
                        "gap_id": item.id, "action": item.action,
                        "locator": item.locator,
                        "status": "returned" if item.id == task.id else "unavailable",
                        "reason": ("Fixture return." if item.id == task.id
                                   else "No fixture match."),
                        "version_ids": ([second.version_id]
                                        if item.id == task.id else []),
                    } for item in tasks]
                    yield RetrievalHit(second, (task.id,))

        class Strict:
            requires_task_attribution = True

            def decompose(self, target, material, context):
                receipts.append(context["current_return"])
                if material.version_id == self_doc.version_id:
                    return Analysis(gaps=(Gap(
                        "next", "Find the next bridge record", action="search",
                        locator="bridge record"),))
                return Analysis()

        self_doc = self.doc
        report = run_provenance(
            self.target, Provider(), Strict(), config=TraceConfig(max_rounds=2))
        self.assertNotEqual("provider_error", report["stop_reason"])
        self.assertEqual(["next"], receipts[-1]["task_ids"])
        self.assertEqual("envelope", receipts[-1]["attribution"])

    def test_provider_feedback_status_cannot_deny_an_attributed_return(self):
        second = document("second")

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search_hits(self, target, tasks, round_number, limit):
                if round_number == 1:
                    self.last_feedback = []
                    return iter((RetrievalHit(self_doc, ()),))
                task = next(item for item in tasks if item.id == "next")
                self.last_feedback = [{
                    "gap_id": task.id, "action": task.action,
                    "locator": task.locator, "status": "unavailable",
                    "reason": "Contradictory provider receipt.",
                    "version_ids": [],
                }]
                return iter((RetrievalHit(second, (task.id,)),))

        def decompose(target, material, context):
            return (Analysis(gaps=(Gap(
                "next", "Find the next bridge record", action="search",
                locator="bridge record"),))
                if material.version_id == self_doc.version_id else Analysis())

        self_doc = self.doc
        report = run_provenance(
            self.target, Provider(), Psi(decompose),
            config=TraceConfig(max_rounds=2))
        self.assertEqual("provider_error", report["stop_reason"])

    def test_strict_staged_provider_cannot_omit_feedback_for_issued_tasks(self):
        second = document("second")

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search_hits(self, target, tasks, round_number, limit):
                self.last_feedback = []
                if round_number == 1:
                    return iter((RetrievalHit(self_doc, ()),))
                task = next(item for item in tasks if item.id == "next")
                return iter((RetrievalHit(second, (task.id,)),))

        class Strict:
            requires_task_attribution = True

            def decompose(self, target, material, context):
                return (Analysis(gaps=(Gap(
                    "next", "Find the next bridge record", action="search",
                    locator="bridge record"),))
                    if material.version_id == self_doc.version_id else Analysis())

        self_doc = self.doc
        report = run_provenance(
            self.target, Provider(), Strict(),
            config=TraceConfig(max_rounds=2))
        self.assertEqual("provider_error", report["stop_reason"])

    def test_returned_feedback_must_list_every_attributed_version(self):
        second, third = document("second"), document("third")

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search_hits(self, target, tasks, round_number, limit):
                if round_number == 1:
                    self.last_feedback = []
                    return iter((RetrievalHit(self_doc, ()),))
                task = next(item for item in tasks if item.id == "next")
                self.last_feedback = [{
                    "gap_id": task.id, "action": task.action,
                    "locator": task.locator, "status": "returned",
                    "reason": "Incomplete provider receipt.",
                    "version_ids": [second.version_id],
                }]
                return iter((RetrievalHit(second, (task.id,)),
                             RetrievalHit(third, (task.id,))))

        def decompose(target, material, context):
            return (Analysis(gaps=(Gap(
                "next", "Find the next bridge record", action="search",
                locator="bridge record"),))
                if material.version_id == self_doc.version_id else Analysis())

        self_doc = self.doc
        report = run_provenance(
            self.target, Provider(), Psi(decompose),
            config=TraceConfig(max_rounds=2))
        self.assertEqual("provider_error", report["stop_reason"])

    def test_claim_cannot_be_supported_from_out_of_scope_document(self):
        target = replace(self.target, evidence_scope=("different",))
        report = run_provenance(target, ReplayTraceProvider(((self.doc,),)), verifier=Verify(lambda *_: self.check()))
        self.assertEqual("verifier_error", report["stop_reason"])

    def test_legacy_verdict_cannot_bypass_frozen_evidence_scope(self):
        target = replace(self.target, evidence_scope=("different",))
        legacy = VerificationResult("supported", (span(self.doc),), "Fixture support")
        report = run_provenance(target, ReplayTraceProvider(((self.doc,),)),
                                verifier=Verify(lambda *_: legacy))
        self.assertEqual("verifier_error", report["stop_reason"])
        self.assertFalse(report["assessment_valid"])

    def test_invented_world_basis_cannot_pass(self):
        check = replace(self.check(world="supported"), world_basis=(Span("notice", 0, 8, "invented"),))
        self.assertEqual("verifier_error", self.run_check(check)["stop_reason"])

    def test_every_round_and_final_share_the_same_decision_mapping(self):
        report = run_provenance(self.target, ReplayTraceProvider(((self.doc,),) * 4),
            verifier=Verify(lambda *_: self.check()), config=TraceConfig(max_rounds=5))
        self.assertTrue(all(r["decision"] == present_decision(report)["decision"] for r in round_decisions(report)))

    def test_cosmetic_fragment_changes_do_not_extend_loop(self):
        count = []
        def fn(target, material, context):
            count.append(1)
            return Analysis(fragments=(Fragment("generated-"+str(len(count)), "paraphrase-"+str(len(count)),
                span(material), target.id, ("wording-"+str(len(count)),)),))
        report = run_provenance(self.target, ReplayTraceProvider(((self.doc,),) * 8), Psi(fn),
                               config=TraceConfig(max_rounds=8))
        self.assertEqual(2, report["usage"]["decomposition_calls"])

    def test_verifier_rechecks_when_visible_fragment_semantics_change(self):
        decompositions = []
        checks = []

        def decompose(target, material, context):
            decompositions.append(1)
            supports = len(decompositions) == 1
            return Analysis(fragments=(Fragment(
                "stable-fragment",
                "The notice supports the target." if supports
                else "The notice contradicts the target.",
                span(material), target.id,
                ("positive",) if supports else ("negative",)),))

        def verify(target, context):
            checks.append(context["fragments"][0])
            evidence = ("supported" if checks[-1]["qualifiers"] == ("positive",)
                        else "contradicted")
            return self.check(evidence=evidence)

        report = run_provenance(
            self.target, ReplayTraceProvider(((self.doc,), (self.doc,))),
            Psi(decompose), Verify(verify), TraceConfig(max_rounds=2))
        self.assertEqual(2, len(checks))
        self.assertEqual("contradicted",
                         report["assessments"]["evidence"]["raw_verdict"])

    def test_identical_semantic_input_does_not_resample_verifier(self):
        calls = []
        check = self.check(evidence="supported")
        report = run_provenance(
            self.target, ReplayTraceProvider(((self.doc,), (self.doc,))),
            Psi(lambda *_: Analysis()),
            Verify(lambda *_: calls.append(1) or check),
            TraceConfig(max_rounds=4))
        self.assertEqual(1, len(calls))
        self.assertTrue(any(operation["action"] == "verification_skipped"
                            for operation in report["operations"]))

    def test_self_revisit_does_not_invent_a_news_gap(self):
        report = run_provenance(self.target, ReplayTraceProvider(((self.doc,),)),
            Psi(lambda t, m, c: Analysis(revisit_versions=(m.version_id,))))
        self.assertFalse(any(g["id"].startswith("revisit:") for g in report["gaps"]))
        self.assertEqual(1, report["usage"]["decomposition_calls"])

    def test_new_upstream_reanalyses_old_declared_edge_without_model_request(self):
        article = document("article", "According to https://example.org/notice")
        seen = []
        def fn(t, m, c):
            seen.append(m.version_id)
            if m.version_id == "article":
                available = any(x["version_id"] == "notice" for x in c["materials"])
                return Analysis(relations=(Relation("citation", "article", "notice" if available else None,
                    "cites", "direct" if available else "declared", (span(m),), "Visible citation", self.doc.url),))
            return Analysis()
        report = run_provenance(self.target, ReplayTraceProvider(((article, self.doc),)), Psi(fn))
        self.assertEqual(["article", "notice", "article"], seen)
        self.assertEqual("direct", report["relations"][0]["status"])
        self.assertTrue(any(o["action"] == "upstream_arrival_reanalysis" for o in report["operations"]))

    def test_nested_fragments_must_connect_to_current_target(self):
        for parent in ["missing", "f"]:
            report = run_provenance(self.target, ReplayTraceProvider(((self.doc,),)),
                Psi(lambda t, m, c: Analysis(fragments=(Fragment("f", "x", span(m), parent),))))
            self.assertEqual("decomposer_error", report["stop_reason"])
        valid = run_provenance(self.target, ReplayTraceProvider(((self.doc,),)),
            Psi(lambda t, m, c: Analysis(fragments=(Fragment("f", "x", span(m), t.id),
                                                    Fragment("child", "y", span(m), "f")))))
        self.assertEqual([], valid["errors"])

    def test_future_versions_do_not_enter_stateful_semantic_plugin(self):
        seen = []
        future = replace(self.doc, version_id="future", available_at="2026-09-05T00:00:00Z")
        report = run_provenance(self.target, ReplayTraceProvider(((future, self.doc),)),
            Psi(lambda t, m, c: seen.append(m.version_id) or Analysis()))
        self.assertEqual(["notice"], seen)
        self.assertEqual(2, report["usage"]["decomposition_calls"])

    def test_fetch_task_retrieves_its_upstream_not_same_seed_again(self):
        seed = document("article", "According to https://example.org/notice")
        provider = SnapshotSearchProvider([seed, self.doc], ["article"])
        self.assertEqual([seed], list(provider.search(self.target, (), 1, 5)))
        tasks = (Gap("upstream", "Read the cited notice", action="fetch", locator=self.doc.url),)
        self.assertEqual([self.doc], list(provider.search(self.target, tasks, 2, 5)))
        self.assertEqual([], list(provider.search(self.target, tasks, 3, 5)))
        self.assertEqual("unavailable", provider.last_feedback[0]["status"])

    def test_exact_tasks_run_before_broad_search_when_capacity_is_one(self):
        decoy = document("a-decoy", "bridge archive commentary")
        exact = document("z-exact", "the exact upstream")
        provider = SnapshotSearchProvider([decoy, exact], [])
        tasks = (
            Gap("broad", "bridge archive", action="search", locator="bridge archive"),
            Gap("exact", "fetch exact", action="fetch", locator=exact.url),
        )
        self.assertEqual([exact], list(provider.search(self.target, tasks, 2, 1)))
        feedback = {item["gap_id"]: item for item in provider.last_feedback}
        self.assertEqual("returned", feedback["exact"]["status"])
        self.assertEqual("budget_exhausted", feedback["broad"]["status"])

    def test_shared_exact_candidate_covers_most_constrained_tasks(self):
        shared = "https://example.org/shared"
        first = replace(document("a"), url=shared)
        exact = replace(document("z"), url=shared)
        provider = SnapshotSearchProvider([first, exact], [])
        tasks = (
            Gap("shared-url", "Fetch shared URL", action="fetch",
                locator=shared),
            Gap("exact-version", "Fetch exact version", action="fetch",
                locator=exact.version_id),
        )
        self.assertEqual([exact], list(provider.search(
            self.target, tasks, 2, 1)))
        feedback = {item["gap_id"]: item for item in provider.last_feedback}
        self.assertEqual("returned", feedback["shared-url"]["status"])
        self.assertEqual("returned", feedback["exact-version"]["status"])
        self.assertEqual(
            {"exact-version", "shared-url"},
            set(provider.last_attribution[exact.version_id]))

    def test_broad_search_tasks_each_get_one_candidate_before_fill(self):
        alpha_one = document("a1", "alpha first")
        alpha_two = document("a2", "alpha second")
        beta = document("b", "beta only")
        provider = SnapshotSearchProvider(
            [alpha_one, alpha_two, beta], [])
        tasks = (
            Gap("alpha", "Find alpha", action="search", locator="alpha"),
            Gap("beta", "Find beta", action="search", locator="beta"),
        )
        found = list(provider.search(self.target, tasks, 2, 2))
        self.assertEqual({"a1", "b"}, {item.version_id for item in found})
        self.assertTrue(all(
            item["status"] == "returned" for item in provider.last_feedback))

    def test_snapshot_index_rejects_duplicate_versions_and_seeds(self):
        with self.assertRaisesRegex(ValueError, "duplicate version_id"):
            SnapshotSearchProvider([self.doc, self.doc], ["notice"])
        with self.assertRaisesRegex(ValueError, "duplicate seed"):
            SnapshotSearchProvider([self.doc], ["notice", "notice"])

    def test_reanalyse_runs_before_broad_search_when_capacity_is_one(self):
        old = document("old", "bridge archive")
        decoy = document("decoy", "bridge archive commentary")
        provider = SnapshotSearchProvider([old, decoy], ["old"])
        self.assertEqual([old], list(provider.search(self.target, (), 1, 1)))
        tasks = (
            Gap("broad", "bridge archive", action="search", locator="bridge archive"),
            Gap("again", "reanalyse old", action="reanalyse", locator="old"),
        )
        self.assertEqual([old], list(provider.search(self.target, tasks, 2, 1)))

    def test_query_changes_actual_search_results(self):
        library = document("library", "The library closes at nine.")
        provider = SnapshotSearchProvider([self.doc, library], [])
        provider.search(self.target, (), 1, 5)
        found = list(provider.search(self.target, (Gap("q", "library", locator="library"),), 2, 5))
        self.assertEqual([library], found)

    def test_chinese_query_routes_to_chinese_snapshot(self):
        chinese = document("cn", "公告确认大桥关闭至周五。")
        provider = SnapshotSearchProvider([chinese], [])
        found = list(provider.search(
            self.target, (Gap("q-cn", "查找大桥关闭公告", action="search",
                              locator="大桥关闭"),), 2, 1))
        self.assertEqual([chinese], found)

    def test_question_backed_query_change_counts_as_progress(self):
        beta = document("beta", "Beta record located.")
        seen = []

        def decompose(target, material, context):
            seen.append((context["usage"]["rounds"], material.version_id))
            if material.version_id == "notice":
                question = "alpha" if context["usage"]["rounds"] == 1 else "beta"
                return Analysis(gaps=(Gap("query", question, action="search"),))
            return Analysis()

        report = run_provenance(
            self.target,
            ReplayTraceProvider(((self.doc,), (self.doc,), (beta,))),
            Psi(decompose), config=TraceConfig(max_rounds=3))
        self.assertEqual(3, report["usage"]["rounds"])
        self.assertIn((3, "beta"), seen)

    def test_changed_effective_query_is_issued_before_exhaustion(self):
        issued_questions = {}

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search(self, target, tasks, round_number, limit):
                issued_questions[round_number] = {
                    item.id: item.question for item in tasks}
                if round_number == 1:
                    self.last_feedback = []
                    return (self_doc,)
                self.last_feedback = [{
                    "gap_id": item.id, "action": item.action,
                    "locator": item.locator, "status": "unavailable",
                    "reason": "No match for this exact fixture query.",
                    "version_ids": [],
                } for item in tasks]
                return ()

        class QueryVerifier:
            uses_retrieval_feedback = True

            def verify(self, target, context):
                unavailable = {
                    item["gap_id"] for item in context["retrieval_feedback"]
                    if item["status"] == "unavailable"
                }
                question = "beta" if "query" in unavailable else "alpha"
                return self_check((replace(
                    self_gap, question=question, locator=None),))

        self_doc = self.doc
        self_check = self.check
        self_gap = self.gap(
            id="query", dimension="evidence", locator=None)
        report = run_provenance(
            self.target, Provider(), verifier=QueryVerifier(),
            config=TraceConfig(max_rounds=3))
        self.assertEqual("alpha", issued_questions[2]["query"])
        self.assertEqual("beta", issued_questions[3]["query"])
        self.assertEqual(3, report["usage"]["rounds"])

    def test_new_verifier_gap_reopens_after_older_psi_resolution(self):
        second = document("second", "The follow-up remains inconclusive.")
        gap = self.gap(dimension="evidence", blocking=True,
                       locator="bridge record")
        calls = []

        def decompose(target, material, context):
            if material.version_id == "second":
                return Analysis(resolutions=(Resolution(
                    gap.id, (span(material),), "The material was inspected."),))
            return Analysis()

        def verify(*_):
            calls.append(1)
            current_basis = span(self.doc if len(calls) == 1 else second)
            return self.check((replace(gap, basis=(current_basis,)),),
                              evidence="supported")

        report = run_provenance(
            self.target, ReplayTraceProvider(((self.doc,), (second,))),
            Psi(decompose), Verify(verify), TraceConfig(max_rounds=2))
        self.assertEqual(2, len(calls))
        self.assertEqual([gap.id], report["assessments"]["evidence"]["blocking_gap_ids"])

    def test_newer_psi_resolution_closes_older_verifier_gap(self):
        second = document("second", "The requested bridge record was inspected.")
        gap = self.gap(dimension="evidence", blocking=True,
                       action="search", locator="bridge record")
        calls = []

        def decompose(target, material, context):
            if material.version_id == "second":
                return Analysis(resolutions=(Resolution(
                    gap.id, (span(material),),
                    "The newly returned record answers the task."),))
            return Analysis()

        def verify(*_):
            calls.append(1)
            return (self.check((gap,), evidence="supported") if len(calls) == 1
                    else self.check(evidence="unresolved"))

        report = run_provenance(
            self.target, ReplayTraceProvider(((self.doc,), (second,))),
            Psi(decompose), Verify(verify), TraceConfig(max_rounds=2))
        self.assertEqual([], report["errors"])
        self.assertFalse(any(item["id"] == gap.id for item in report["gaps"]))
        self.assertEqual("unresolved", report["decision_status"])

    def test_exhausted_search_does_not_rerun_verifier_without_new_input(self):
        provider = SnapshotSearchProvider([self.doc], ["notice"])
        count = []
        report = run_provenance(self.target, provider,
            verifier=Verify(lambda *_: count.append(1) or self.check()), config=TraceConfig(max_rounds=8))
        self.assertEqual(1, len(count))
        self.assertEqual("provider_exhausted", report["stop_reason"])

    def test_exhausted_task_can_branch_to_a_new_task_for_the_next_round(self):
        issued_rounds = {}
        first_gap = self.gap(id="g1", locator="first bridge lead")
        second_gap = self.gap(id="g2", locator="second bridge lead")

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search(self, target, tasks, round_number, limit):
                issued_rounds[round_number] = {item.id for item in tasks}
                if round_number == 1:
                    self.last_feedback = []
                    return (self_doc,)
                self.last_feedback = [{
                    "gap_id": item.id, "action": item.action,
                    "locator": item.locator, "status": "unavailable",
                    "reason": "No match in the fixture index.",
                    "version_ids": [],
                } for item in tasks]
                return ()

        class BranchVerifier:
            uses_retrieval_feedback = True

            def verify(self, target, context):
                unavailable = {item["gap_id"] for item in
                               context.get("retrieval_feedback", [])
                               if item["status"] == "unavailable"}
                if first_gap.id not in unavailable:
                    return self_check((first_gap,))
                if second_gap.id not in unavailable:
                    return replace(
                        self_check((second_gap,)),
                        resolutions=(Resolution(
                            first_gap.id, (span(self_doc),),
                            "The first fixed-index lead was exhausted."),))
                return self_check((second_gap,))

        self_doc = self.doc
        self_check = self.check
        report = run_provenance(
            self.target, Provider(), verifier=BranchVerifier(),
            config=TraceConfig(max_rounds=3))
        self.assertIn(second_gap.id, issued_rounds[3])
        self.assertTrue(any(item["action"] == "followup_tasks_queued"
                            for item in report["operations"]))

    def test_retrieval_budget_feedback_retries_within_outer_round_budget(self):
        second = document("second", "The second bridge record was returned.")
        gap = self.gap(id="retry", locator="bridge retry")
        issued_rounds = {}

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search_hits(self, target, tasks, round_number, limit):
                issued_rounds[round_number] = {item.id for item in tasks}
                if round_number == 1:
                    self.last_feedback = []
                    return iter((RetrievalHit(self_doc, ()),))
                if round_number == 2:
                    self.last_feedback = [{
                        "gap_id": item.id, "action": item.action,
                        "locator": item.locator, "status": "budget_exhausted",
                        "reason": "Fixture retrieval quota deferred this task.",
                        "version_ids": [],
                    } for item in tasks]
                    return iter(())
                self.last_feedback = [{
                    "gap_id": item.id, "action": item.action,
                    "locator": item.locator,
                    "status": "returned" if item.id == gap.id else "unavailable",
                    "reason": ("Fixture return." if item.id == gap.id
                               else "No fixture match."),
                    "version_ids": ([second.version_id] if item.id == gap.id else []),
                } for item in tasks]
                return iter((RetrievalHit(second, (gap.id,)),))

        class RetryVerifier:
            uses_retrieval_feedback = True

            def verify(self, target, context):
                returned = any(
                    gap.id in item.get("task_ids", [])
                    for item in context.get("current_round_returns", []))
                if not returned:
                    return self_check((gap,))
                return replace(
                    self_check(gaps=(), evidence="contradicted"),
                    resolutions=(Resolution(
                        gap.id, (span(second),),
                        "The retried task returned its exact fixture version."),))

        self_doc = self.doc
        self_check = self.check
        report = run_provenance(
            self.target, Provider(), verifier=RetryVerifier(),
            config=TraceConfig(max_rounds=3))
        self.assertIn(3, issued_rounds, report)
        self.assertIn(gap.id, issued_rounds[3])
        self.assertTrue(any(item["action"] == "retrieval_budget_deferred"
                            for item in report["operations"]))

    def test_budget_deferred_task_survives_an_unhelpful_duplicate_return(self):
        second = document("second", "The retried bridge record arrived.")
        gap = self.gap(id="retry-duplicate", locator="bridge retry")
        issued_rounds = {}

        class Provider:
            def __init__(self):
                self.last_feedback = []

            def search_hits(self, target, tasks, round_number, limit):
                issued_rounds[round_number] = {item.id for item in tasks}
                if round_number == 1:
                    self.last_feedback = []
                    return iter((RetrievalHit(self_doc, ()),))
                if round_number == 2:
                    seed_task = next(item for item in tasks if item.id != gap.id)
                    self.last_feedback = [{
                        "gap_id": item.id, "action": item.action,
                        "locator": item.locator,
                        "status": ("returned" if item.id == seed_task.id
                                   else "budget_exhausted"),
                        "reason": ("Duplicate fixture return." if item.id == seed_task.id
                                   else "Round retrieval capacity was deferred."),
                        "version_ids": ([self_doc.version_id]
                                        if item.id == seed_task.id else []),
                    } for item in tasks]
                    return iter((RetrievalHit(self_doc, (seed_task.id,)),))
                self.last_feedback = [{
                    "gap_id": item.id, "action": item.action,
                    "locator": item.locator,
                    "status": "returned" if item.id == gap.id else "unavailable",
                    "reason": ("Fixture return." if item.id == gap.id
                               else "No fixture match."),
                    "version_ids": ([second.version_id] if item.id == gap.id else []),
                } for item in tasks]
                return iter((RetrievalHit(second, (gap.id,)),))

        class RetryVerifier:
            uses_retrieval_feedback = True

            def verify(self, target, context):
                returned = any(
                    gap.id in item.get("task_ids", [])
                    for item in context.get("current_round_returns", []))
                return (replace(
                    self_check(gaps=(), evidence="contradicted"),
                    resolutions=(Resolution(
                        gap.id, (span(second),), "Exact retry returned."),))
                    if returned else self_check((gap,)))

        self_doc = self.doc
        self_check = self.check
        report = run_provenance(
            self.target, Provider(), verifier=RetryVerifier(),
            config=TraceConfig(max_rounds=3))
        self.assertIn(3, issued_rounds, report)
        self.assertIn(gap.id, issued_rounds[3])

    def test_unconsumed_planned_hits_are_not_committed_when_revisits_use_budget(self):
        seed = document("a", "bridge seed")
        others = [document(name, "bridge follow-up " + name)
                  for name in ("b", "c", "d")]
        provider = SnapshotSearchProvider([seed, *others], [seed.version_id])

        class Revisiting:
            requires_task_attribution = True

            def decompose(self, target, material, context):
                if material.version_id == seed.version_id:
                    return Analysis(gaps=(Gap(
                        "bridge-search", "Find bridge follow-ups",
                        action="search", locator="bridge"),))
                return Analysis(revisit_versions=(seed.version_id,))

        report = run_provenance(
            replace(self.target, evidence_scope=()), provider, Revisiting(),
            config=TraceConfig(max_rounds=2, max_documents=10,
                               max_decomposition_calls=4))
        self.assertNotEqual("provider_error", report["stop_reason"])
        self.assertEqual("decomposition_budget", report["stop_reason"])
        second_round = provider.history[1]
        self.assertEqual(["b", "c"], second_round["returned_ids"])
        self.assertIn("d", second_round["planned_ids"])
        self.assertNotIn("d", provider.returned)

    def test_runtime_gap_collision_keeps_committed_projection_atomic(self):
        first, second = document("a"), document("b")

        def decompose(target, material, context):
            finding = Fragment(
                material.version_id + ":fragment", material.content,
                span(material), target.id)
            if material.version_id == first.version_id:
                return Analysis(
                    fragments=(finding,),
                    gaps=(Gap("revisit:a", "A model-owned follow-up task"),))
            return Analysis(
                fragments=(finding,), revisit_versions=(first.version_id,))

        report = run_provenance(
            replace(self.target, evidence_scope=()),
            ReplayTraceProvider(((first, second),)), Psi(decompose),
            config=TraceConfig(max_rounds=1, max_decomposition_calls=2))
        self.assertEqual("decomposer_error", report["stop_reason"])
        self.assertEqual({"a", "b"}, set(report["eligible_version_ids"]))
        self.assertEqual({"a", "b"}, set(report["analyses"]))
        self.assertEqual(
            {"a:fragment", "b:fragment"},
            {item["id"] for item in report["fragments"]})
        self.assertEqual(
            ["A model-owned follow-up task"],
            [item["question"] for item in report["gaps"]
             if item["id"] == "revisit:a"])

    def test_discovered_upstreams_pass_each_return_through_psi(self):
        a = document("a", "https://example.org/b")
        b = document("b", "https://example.org/notice")
        provider = SnapshotSearchProvider([a, b, self.doc], ["a"])
        seen = []
        def fn(t, m, c):
            seen.append(m.version_id)
            locator = {"a": b.url, "b": self.doc.url}.get(m.version_id)
            return Analysis(gaps=(Gap("next:"+m.version_id, "Read upstream", action="fetch", locator=locator),) if locator else ())
        report = run_provenance(self.target, provider, Psi(fn), config=TraceConfig(max_rounds=5))
        self.assertEqual("a", seen[0])
        self.assertEqual({"a", "b", "notice"}, set(seen))
        self.assertEqual(3, report["usage"]["decomposition_calls"])


if __name__ == "__main__": unittest.main()
