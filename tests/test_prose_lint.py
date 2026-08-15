"""U-S4: charter prose linter + assumption gate + declared approval categories.

Three small units, one closing theme: prose that governs the agent is held to
the same honesty standard the runtime already holds evidence to.

* Prose linter (advisory, never blocking) - extends the negative-check half
  of `godmode_docslint` to a project's own compiled charter rules
  (`godmode_charter.compile_charter`): a HARD rule phrased only as
  prohibitions, a rule the charter itself could not map to any checkable
  shape, and a directive bound from two different role documents.
* Assumption gate [E4] - an R3+ session with zero `assumption` records earns
  one SOFT `before_approach` advisory; any assumption record (including one
  that states there were none) clears it. Reuses the R3+ tier proxy U-T2
  already defined (fix-vocabulary claims + Edit/Write mutation turns) rather
  than inventing a second definition of "R3+" - see
  `godmode_attest.assumption_gate`'s own comment.
* Approval declarations [E56] - `.godmode-authorization-policy.json` gains
  `approval_required: [<category>...]`: an otherwise-unprotected operation in
  a declared category becomes ask-tier, with the exact operation named in
  the reason. Tighten-only: it can never soften an existing R5 refusal to an
  ask, because the risk tier is computed from category/text alone and never
  reads the `protected` flag this widens.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime.godmode_charter import compile_charter, negation_heavy  # noqa: E402
from godmode_runtime.godmode_docslint import lint_charter_prose, lint_docs  # noqa: E402
from godmode_runtime.godmode_attest import (  # noqa: E402
    ASSUMPTION_GATE_ADVISORY,
    assumption_gate,
    gate,
    open_session,
    record_claim,
)
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


def _codes(report: dict) -> list[str]:
    return [f["check"] for f in report["findings"]]


class NegationHeavyTests(unittest.TestCase):
    """>=2 negation tokens and no positive verb, on a HARD rule only."""

    def test_a_pure_prohibition_hard_rule_is_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n"
                "- Never push without an explicit ask; do not skip the review.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            hard = [r for r in charter["compiled"] if r["enforcement"] == "HARD"]
            self.assertTrue(hard, charter["compiled"])
            report = lint_charter_prose(charter)
        self.assertIn("negation-heavy-rule", _codes(report))

    def test_the_positive_restatement_is_not_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n"
                "- Always ask before pushing; state the reviewer before merging.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            report = lint_charter_prose(charter)
        self.assertNotIn("negation-heavy-rule", _codes(report))

    def test_a_negation_paired_with_a_positive_verb_is_not_flagged(self) -> None:
        # Two negations, but the rule already states the positive half - the
        # green control that proves the "no positive verb" clause matters,
        # not just the negation count.
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n"
                "- Never merge without stating the reviewer in the commit "
                "message.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            report = lint_charter_prose(charter)
        self.assertNotIn("negation-heavy-rule", _codes(report))

    def test_it_never_flags_a_soft_or_advisory_rule(self) -> None:
        # The spec names HARD rules only; a SOFT/ADVISORY rule phrased the
        # same way is not this check's business.
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must never feel slow or cluttered.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            self.assertFalse(
                any(r["enforcement"] == "HARD" for r in charter["compiled"]),
                charter["compiled"],
            )
            report = lint_charter_prose(charter)
        self.assertNotIn("negation-heavy-rule", _codes(report))

    def test_the_bare_function_matches_the_module_check(self) -> None:
        self.assertTrue(negation_heavy(
            "Never push without an explicit ask; do not skip the review."))
        self.assertFalse(negation_heavy(
            "Always ask before pushing; state the reviewer before merging."))


class NamedProhibitionDoctrineExemptionTests(unittest.TestCase):
    """Controller ruling, 2026-08-15: safety prohibitions keep their
    prohibition form. A HARD rule phrased "never/no/must not <verb>
    <concrete object>" is exempt outright - not bad prose to rewrite - which
    is the doctrine an earlier pass of this same check violated by rewriting
    two of GODMODE.md's own gates. The exemption is scoped to a *named*
    object: a placeholder ("do not do things") or a verb with nothing named
    before the clause boundary ("never push without...") still flags.
    """

    def test_the_two_real_godmode_gates_produce_zero_findings(self) -> None:
        # The exact prior wording (git show 08e9a3d:GODMODE.md), not a
        # paraphrase - this is what the ruling requires stay unflagged.
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n"
                "- Never claim verified without a citation that resolves; "
                "an absence claim requires the search that would disprove "
                "it.\n"
                "- Never mutate production or an unknown environment "
                "without an authorized capability.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            hard = [r for r in charter["compiled"] if r["enforcement"] == "HARD"]
            self.assertEqual(len(hard), 2, charter["compiled"])
            report = lint_charter_prose(charter)
        self.assertNotIn("negation-heavy-rule", _codes(report), report["findings"])

    def test_a_named_prohibition_with_an_article_before_the_object_is_exempt(self) -> None:
        # "a test" - the article must not swallow "test" as the object.
        self.assertFalse(negation_heavy(
            "Never weaken a test without a recorded rationale; a guard "
            "must be observed failing before it counts."))

    def test_a_vague_placeholder_object_still_flags(self) -> None:
        # The coordinator's own example of genuinely bad prose: no positive
        # verb, and "things" names nothing a reader could check.
        self.assertTrue(negation_heavy(
            "Do not do things that are not helpful and not unclear."))

    def test_the_vague_placeholder_still_flags_through_the_full_hard_pipeline(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Never do anything without doing something.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            hard = [r for r in charter["compiled"] if r["enforcement"] == "HARD"]
            self.assertTrue(hard, charter["compiled"])
            report = lint_charter_prose(charter)
        self.assertIn("negation-heavy-rule", _codes(report))

    def test_a_verb_with_no_named_object_before_the_boundary_still_flags(self) -> None:
        # "never push without" - the object slot is the clause boundary
        # itself ("without"), not a concrete thing, so this stays flagged;
        # it is the shape the check still exists to catch.
        self.assertTrue(negation_heavy(
            "Never push without an explicit ask; do not skip the review."))


class NoDoneCriterionTests(unittest.TestCase):
    """A rule the charter itself could not map to a checkable shape."""

    def test_an_unverifiable_rule_is_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            charter = compile_charter(project)
            self.assertEqual(charter["enforcement"]["ADVISORY"], 1, charter)
            report = lint_charter_prose(charter)
        self.assertIn("no-done-criterion", _codes(report))

    def test_a_checkable_rule_is_not_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- A claim must cite evidence before completion.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            self.assertEqual(charter["enforcement"]["HARD"], 1, charter)
            report = lint_charter_prose(charter)
        self.assertNotIn("no-done-criterion", _codes(report))

    def test_findings_are_advisory_and_never_block(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            report = lint_charter_prose(compile_charter(project))
        self.assertTrue(report["findings"])
        self.assertTrue(all(f["severity"] == "advisory" for f in report["findings"]))


class DuplicatedSourceTests(unittest.TestCase):
    """The same normalized directive bound from two role documents."""

    def test_the_same_directive_in_two_role_docs_is_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Every commit must carry a changelog fragment.\n",
                encoding="utf-8",
            )
            (project / "OPERATOR.md").write_text(
                "# Gates\n- Every commit must carry a changelog fragment.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            self.assertGreaterEqual(charter["documents"], 2, charter)
            report = lint_charter_prose(charter)
        self.assertIn("duplicated-source", _codes(report))

    def test_the_same_directive_repeated_within_one_doc_is_not_flagged(self) -> None:
        # One document repeating itself is an editing accident visible on a
        # read of that file - this check is for the copy that lives
        # somewhere else and drifts unnoticed.
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n"
                "- Every commit must carry a changelog fragment.\n"
                "- Every commit must carry a changelog fragment.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            report = lint_charter_prose(charter)
        self.assertNotIn("duplicated-source", _codes(report))

    def test_distinct_directives_across_two_docs_are_not_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Every commit must carry a changelog fragment.\n",
                encoding="utf-8",
            )
            (project / "OPERATOR.md").write_text(
                "# Gates\n- Every claim must cite evidence before completion.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            report = lint_charter_prose(charter)
        self.assertNotIn("duplicated-source", _codes(report))


class LintDocsIntegrationTests(unittest.TestCase):
    """`prose_advisories` rides alongside `lint_docs` without touching its
    exit-code-bearing fields."""

    def test_prose_advisories_never_affect_verdict_or_high_severity(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            report = lint_docs(project)
        self.assertTrue(report["prose_advisories"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "clean")
        self.assertEqual(report["high_severity"], 0)

    def test_a_project_with_no_charter_docs_reports_no_prose_advisories(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "README.md").write_text("# hi\n", encoding="utf-8")
            report = lint_docs(project)
        self.assertEqual(report["prose_advisories"], [])


class ThisRepositoryProseLintTests(unittest.TestCase):
    """Population sweep: godmode's own charter passes its own linter.

    Triage, recorded here rather than only in the task report. 5 HARD rules
    in GODMODE.md's `## Gates`; two are phrased "never X without Y" and stay
    exactly that way - a controller ruling (2026-08-15) reversed the first
    pass of this sweep, which had rewritten them positively and, in doing
    so, silently narrowed one rule and changed the trigger verb of the
    other. `NamedProhibitionDoctrineExemptionTests` above is the mechanism
    that now keeps them unflagged; this class is the population-level proof
    it actually holds on this repo's real content. The remaining 3 findings
    are ADVISORY rules already known and already reviewed
    (`AdvisoryReviewRepoTests`, tests/test_charter_checkability.py) -
    sentence-fragment artifacts of the line-based directive scanner, not
    real rules; accepted as advisory rather than rewritten, since inventing
    a verification shape for a narrative fragment would be false
    enforcement. Zero duplicated-source findings: this repo binds exactly
    one role document today.
    """

    def test_no_hard_rule_reads_as_a_pure_prohibition(self) -> None:
        charter = compile_charter(PLUGIN_ROOT)
        report = lint_charter_prose(charter)
        self.assertNotIn("negation-heavy-rule", _codes(report), report["findings"])

    def test_no_directive_is_bound_from_two_role_documents(self) -> None:
        charter = compile_charter(PLUGIN_ROOT)
        report = lint_charter_prose(charter)
        self.assertNotIn("duplicated-source", _codes(report), report["findings"])

    def test_the_only_remaining_findings_are_the_known_reviewed_advisories(self) -> None:
        charter = compile_charter(PLUGIN_ROOT)
        report = lint_charter_prose(charter)
        self.assertEqual(
            {f["check"] for f in report["findings"]}, {"no-done-criterion"},
            report["findings"],
        )
        self.assertEqual(len(report["findings"]), charter["enforcement"]["ADVISORY"])

    def test_docs_lint_stays_clean_on_this_repository(self) -> None:
        report = lint_docs(PLUGIN_ROOT)
        self.assertEqual(report["verdict"], "clean")
        self.assertEqual(report["high_severity"], 0)


class AssumptionGateTests(unittest.TestCase):
    """SOFT `before_approach` advisory: R3+ session, zero assumption records."""

    def test_a_session_with_no_r3_signal_gets_no_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            session = open_session(archive, "S1")
            self.assertIsNone(assumption_gate(archive, session))

    def test_an_r3_session_via_fix_vocabulary_claim_earns_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            session = open_session(archive, "S1")
            record_claim(archive, project, session, "fixed the off-by-one bug",
                        "observed")
            self.assertEqual(
                assumption_gate(archive, session), ASSUMPTION_GATE_ADVISORY)

    def test_an_r3_session_via_mutation_turns_earns_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            session = open_session(archive, "S1")
            timeline = {"commands": {}, "mutation_turns": [3]}
            self.assertEqual(
                assumption_gate(archive, session, timeline), ASSUMPTION_GATE_ADVISORY)

    def test_any_assumption_record_clears_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            session = open_session(archive, "S1")
            record_claim(archive, project, session, "fixed the off-by-one bug",
                        "observed")
            self.assertEqual(
                assumption_gate(archive, session), ASSUMPTION_GATE_ADVISORY)
            archive.append(
                "assumption", "no-blocking-assumptions",
                {"value": "none - the fix was fully specified by the failing "
                          "test", "status": "active", "session": session},
                evidence=[],
            )
            self.assertIsNone(assumption_gate(archive, session))

    def test_it_recomputes_the_same_advisory_every_call_not_a_counter(self) -> None:
        # "ONE advisory per session, not per call": the standing fact about
        # the session, not a one-shot flag that flips after the first read.
        with isolated_project() as (project, _s, _a, archive):
            session = open_session(archive, "S1")
            record_claim(archive, project, session, "fixed the off-by-one bug",
                        "observed")
            first = assumption_gate(archive, session)
            second = assumption_gate(archive, session)
        self.assertEqual(first, second)
        self.assertEqual(first, ASSUMPTION_GATE_ADVISORY)

    def test_the_gate_function_carries_it_as_a_non_blocking_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Every commit must carry a changelog fragment.\n",
                encoding="utf-8",
            )
            charter = compile_charter(project)
            session = open_session(archive, "S1")
            record_claim(archive, project, session, "fixed the off-by-one bug",
                        "observed")
            verdict = gate(archive, session, charter, "before_approach")
        self.assertTrue(verdict.allowed)
        self.assertIn(ASSUMPTION_GATE_ADVISORY, verdict.advisories)
        self.assertIn("advisories", verdict.view())

    def test_a_different_trigger_never_carries_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            charter = compile_charter(project)
            session = open_session(archive, "S1")
            record_claim(archive, project, session, "fixed the off-by-one bug",
                        "observed")
            verdict = gate(archive, session, charter, "before_completion")
        self.assertEqual(verdict.advisories, ())


class ApprovalRequiredTests(unittest.TestCase):
    """`.godmode-authorization-policy.json`'s `approval_required` categories."""

    def test_a_declared_category_becomes_protected_with_the_operation_in_the_reason(self) -> None:
        operation = "git checkout -b feature/approval-required-demo"
        baseline = classify_action(operation)
        self.assertFalse(baseline["protected"])

        widened = classify_action(operation, require_approval=("git-branch-create",))
        self.assertTrue(widened["protected"])
        self.assertEqual(widened["tier"], baseline["tier"])
        self.assertTrue(any(operation in item for item in widened["impact"]))

    def test_an_undeclared_category_is_unaffected(self) -> None:
        operation = "git checkout -b feature/x"
        widened = classify_action(operation, require_approval=("release-or-external-write",))
        self.assertFalse(widened["protected"])

    def test_policy_is_tighten_only_a_refusal_never_softens_to_ask(self) -> None:
        operation = "git push --force origin main"
        baseline = classify_action(operation)
        self.assertEqual(baseline["tier"], "R5")
        self.assertTrue(baseline["protected"])

        widened = classify_action(operation, require_approval=("git-history-or-remote",))
        self.assertEqual(widened["tier"], "R5")
        self.assertTrue(widened["protected"])

    def test_worktree_file_mutation_inside_the_tree_can_be_widened_too(self) -> None:
        operation = "echo hi > scratch.txt"
        baseline = classify_action(operation, project_root=PLUGIN_ROOT)
        self.assertFalse(baseline["protected"])

        widened = classify_action(
            operation, project_root=PLUGIN_ROOT,
            require_approval=("worktree-file-mutation",))
        self.assertTrue(widened["protected"])
        self.assertEqual(widened["tier"], baseline["tier"])


if __name__ == "__main__":
    unittest.main()
