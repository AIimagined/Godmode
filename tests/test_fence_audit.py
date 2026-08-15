"""Two questions asked of a finished change rather than of a pending edit.

The fence refuses an edit outside the declared set at the boundary. That covers
the tools that announce a `file_path` and nothing else: a shell command that
rewrites a file in passing, an edit made before the plan was approved, or work
done in a session where the gate was disabled all land in the tree unfenced.

So the same declaration is asked of the result. Every changed file either falls
inside what the plan said it would touch, or somebody says why it does not —
"every changed line should trace directly to the user's request", checked
against the one machine-readable statement of that request this project has.

And the acceptance half: a plan states what done looks like, and nothing ever
compared a completion against it. A `build` recorded as done that cites no
acceptance is a claim the plan's own contract could have graded and did not.
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

from godmode_runtime.godmode_fence import audit_changes, unaccepted_completions  # noqa: E402
from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


SPEC = {"objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"}


def _approved_plan(archive, editable: str | None, acceptance: str = "the suite passes") -> None:
    specify(archive, "S-1", "narrow the rotation fix", SPEC)
    contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
    contract["acceptance"] = acceptance
    contract["accept"] = "cmd:x"
    if editable is not None:
        contract["editable"] = editable
    start(archive, "S-1", "narrow the rotation fix", contract)
    approve(archive, "S-1")


class TraceabilityTests(unittest.TestCase):
    def test_a_change_inside_the_declared_set_traces(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            report = audit_changes(archive, project, ["src/auth/session.py"])
        self.assertEqual(report["untraceable"], [])

    def test_a_change_outside_it_does_not(self) -> None:
        """The case the boundary gate cannot catch: it landed by some route
        that never presented a file_path."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            report = audit_changes(archive, project, ["src/billing/invoice.py"])
        self.assertEqual([f["path"] for f in report["untraceable"]],
                         ["src/billing/invoice.py"])

    def test_an_undeclared_plan_audits_nothing_and_says_so(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, None)
            report = audit_changes(archive, project, ["anything.py"])
        self.assertEqual(report["verdict"], "no-declared-scope")

    def test_each_untraceable_change_is_a_question(self) -> None:
        """Findings, never closures. A file outside the set is not thereby
        wrong — it may be a dependency the plan did not foresee — but nobody
        having said which is the case that ships."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            report = audit_changes(archive, project, ["src/billing/invoice.py"])
        self.assertIn("question", report["untraceable"][0])

    def test_the_report_states_what_it_examined(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            report = audit_changes(archive, project,
                                   ["src/auth/session.py", "src/billing/invoice.py"])
        self.assertEqual(report["changes_examined"], 2)


class AcceptanceTests(unittest.TestCase):
    def test_a_completion_that_cites_no_acceptance_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**", acceptance="the rotation replay test passes")
            archive.append("change","rotation fixed", {"status": "done"}, evidence=[])
            report = unaccepted_completions(archive)
        self.assertEqual(len(report["findings"]), 1, report)

    def test_a_completion_with_evidence_is_not_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**", acceptance="the rotation replay test passes")
            archive.append("change","rotation fixed", {"status": "done"},
                           evidence=["run:the rotation replay test passes"])
            report = unaccepted_completions(archive)
        self.assertEqual(report["findings"], [])

    def test_an_unfinished_build_is_not_reported(self) -> None:
        """Only a completion claims to have met the acceptance. Work in
        progress has not claimed anything yet."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            archive.append("change","rotation half done", {"status": "in-progress"}, evidence=[])
            report = unaccepted_completions(archive)
        self.assertEqual(report["findings"], [])

    def test_without_an_approved_plan_there_is_nothing_to_grade_against(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("change","something", {"status": "done"}, evidence=[])
            report = unaccepted_completions(archive)
        self.assertEqual(report["verdict"], "no-acceptance-declared")

    def test_the_finding_quotes_the_acceptance_it_was_measured_against(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**", acceptance="the rotation replay test passes")
            archive.append("change","rotation fixed", {"status": "done"}, evidence=[])
            report = unaccepted_completions(archive)
        self.assertIn("rotation replay test", report["findings"][0]["acceptance"])


if __name__ == "__main__":
    unittest.main()
