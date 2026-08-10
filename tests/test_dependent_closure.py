"""What depends on what changed, and whether anybody dealt with it.

`atlas affected` already answers the first half: given a target, here is what
breaks. Nothing consumes that answer. The operator's question is the second
half — this change touched three files, so what else *had* to move, and did it?

The shape is deliberately the one requests and obligations use: findings, never
closures. A dependent this reports is not automatically wrong. It might need
updating, or it might be genuinely unaffected, and only a person can say which.
What must not happen is nobody saying anything — a dependent that was neither
updated nor explained is the case that ships broken.
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

from godmode_runtime.godmode_atlas import build, unfollowed_dependents  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _tree(project: Path) -> None:
    """A caller, a test, and an unrelated file, all importing by module name."""
    (project / "auth.py").write_text("def check():\n    return True\n", encoding="utf-8")
    (project / "login.py").write_text("import auth\n\nauth.check()\n", encoding="utf-8")
    (project / "test_auth.py").write_text("import auth\n\ndef test():\n    auth.check()\n",
                                          encoding="utf-8")
    (project / "billing.py").write_text("def invoice():\n    return 1\n", encoding="utf-8")


class ClosureTests(unittest.TestCase):
    def test_a_dependent_nobody_touched_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        names = {finding["dependent"] for finding in report["findings"]}
        self.assertIn("login.py", names)

    def test_a_dependent_that_was_also_changed_is_not_reported(self) -> None:
        """It was dealt with. Reporting it anyway trains the reader to skim."""
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py", "login.py"])
        names = {finding["dependent"] for finding in report["findings"]}
        self.assertNotIn("login.py", names)

    def test_a_file_that_depends_on_nothing_changed_is_not_reported(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        names = {finding["dependent"] for finding in report["findings"]}
        self.assertNotIn("billing.py", names)

    def test_the_changed_file_itself_is_never_its_own_dependent(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        names = {finding["dependent"] for finding in report["findings"]}
        self.assertNotIn("auth.py", names)

    def test_each_finding_says_what_it_depends_on(self) -> None:
        """`login.py is affected` is unactionable without `by auth.py`, and a
        change usually touches more than one file."""
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        finding = next(f for f in report["findings"] if f["dependent"] == "login.py")
        self.assertEqual(finding["because_of"], "auth.py")

    def test_a_test_is_reported_as_a_test_not_as_a_caller(self) -> None:
        """A test that covers the changed code and a module that calls it need
        different things done to them, and one flat list hides which is
        which."""
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        finding = next(f for f in report["findings"] if f["dependent"] == "test_auth.py")
        self.assertEqual(finding["relation"], "tests")

    def test_every_finding_is_a_question(self) -> None:
        """Findings, never closures — the contract requests and obligations
        keep. An agent that could close these would close them the way it
        currently forgets them."""
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        for finding in report["findings"]:
            self.assertIn("question", finding)

    def test_the_report_states_what_it_examined(self) -> None:
        """So an empty report cannot be read as `nothing was examined` — the
        same reason the request review states its own denominator."""
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), ["auth.py"])
        self.assertEqual(report["changed"], ["auth.py"])
        self.assertGreater(report["dependents_seen"], 0)

    def test_nothing_changed_reports_nothing_rather_than_everything(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _tree(project)
            report = unfollowed_dependents(build(project), [])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "nothing-changed")


if __name__ == "__main__":
    unittest.main()
