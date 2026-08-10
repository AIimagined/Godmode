"""What this piece of work is allowed to touch, declared before it starts.

The impact machinery here answers `what did change` and `what depends on
this`. Neither answers the question an operator actually asks when they hand
over one section of a codebase: *nothing else moves*. `atlas affected` reports
the blast radius after a symbol is picked; `inventory diff` reports the damage
after it is done. Both are detection, and detection arrives after the edit.

So a plan may declare the paths it may touch, and an edit outside them is
refused rather than reported. The declaration is task-scoped, which is why it
lives on the plan contract and not in a config file: the set of files this
change may touch is a property of this change, and expires with it.

Undeclared means unenforced — a fence nobody wrote cannot fence anything, and
guessing the editable set from the request would be the auto-detection this
project refuses everywhere else. The gap is reported instead of inferred.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_fence import (  # noqa: E402
    declared_fence, fence_verdict,
)
from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


SPEC = {"objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"}


def _approved_plan(archive, editable: str | None) -> None:
    specify(archive, "S-1", "narrow the rotation fix", SPEC)
    contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
    if editable is not None:
        contract["editable"] = editable
    start(archive, "S-1", "narrow the rotation fix", contract)
    approve(archive, "S-1")


class DeclarationTests(unittest.TestCase):
    def test_a_plan_that_declares_nothing_fences_nothing(self) -> None:
        """Undeclared is unenforced, not empty. An empty fence would refuse
        every edit in the project the moment anybody opened a plan."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, None)
            self.assertIsNone(declared_fence(archive))

    def test_a_declared_fence_is_read_back_as_patterns(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**, tests/test_auth.py")
            self.assertEqual(declared_fence(archive),
                             ["src/auth/**", "tests/test_auth.py"])

    def test_newlines_separate_patterns_too(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**\ntests/test_auth.py")
            self.assertEqual(len(declared_fence(archive)), 2)

    def test_only_an_approved_plan_fences(self) -> None:
        """An unapproved plan is a proposal. Enforcing one would let the agent
        fence itself in or out by writing a plan nobody agreed to."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            specify(archive, "S-1", "narrow the rotation fix", SPEC)
            contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
            contract["editable"] = "src/auth/**"
            start(archive, "S-1", "narrow the rotation fix", contract)
            self.assertIsNone(declared_fence(archive))


class VerdictTests(unittest.TestCase):
    def test_a_path_inside_the_fence_is_allowed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, "src/auth/session.py",
                                    project_root=project)
        self.assertTrue(verdict["allowed"])

    def test_a_path_outside_the_fence_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, "src/billing/invoice.py",
                                    project_root=project)
        self.assertFalse(verdict["allowed"])

    def test_an_undeclared_fence_allows_but_says_so(self) -> None:
        """Fails open on purpose, and reports the gap so it cannot rot
        silently — the same contract the UI boundary keeps."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, None)
            verdict = fence_verdict(archive, "src/billing/invoice.py",
                                    project_root=project)
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["fence"], "undeclared")

    def test_the_refusal_names_the_command_that_widens_the_fence(self) -> None:
        """A refusal whose remedy is stale or absent teaches the agent a false
        model of what is possible, and the agent then hands work back that it
        could have completed."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, "src/billing/invoice.py",
                                    project_root=project)
        self.assertFalse(verdict["allowed"], "or this asserts about the wrong branch")
        self.assertIn("planmode", verdict["remedy"])
        self.assertIn("editable", verdict["remedy"])
        self.assertIn("re-approved", verdict["remedy"])

    def test_the_refusal_names_what_was_declared(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, "src/billing/invoice.py",
                                    project_root=project)
        self.assertIn("src/auth/**", verdict["detail"])

    def test_an_absolute_path_inside_the_project_is_judged_by_its_relative_form(self) -> None:
        """The host hands the hook whatever the agent typed, which is usually
        absolute. Judging the raw string would let the same file pass or fail
        depending on how it was spelled."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, str(project / "src" / "auth" / "session.py"),
                                    project_root=project)
        self.assertTrue(verdict["allowed"])

    def test_a_path_outside_the_project_is_refused_whatever_the_fence_says(self) -> None:
        """A fence is a statement about this project. A path that escapes it
        is not covered by any pattern, and treating an unmatched escape as
        allowed would make `../` the way through the fence."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "**")
            verdict = fence_verdict(archive, str(project.parent / "elsewhere.py"),
                                    project_root=project)
        self.assertFalse(verdict["allowed"])

    def test_a_windows_spelled_path_matches_a_posix_pattern(self) -> None:
        """Patterns are written with forward slashes; the host supplies
        backslashes. A fence that depends on the separator is a fence that
        works on one platform."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            verdict = fence_verdict(archive, "src\\auth\\session.py",
                                    project_root=project)
        self.assertTrue(verdict["allowed"])

    def test_a_shallow_pattern_does_not_match_a_nested_file(self) -> None:
        """`src/*.py` and `src/**` are different claims and must stay so, or
        every fence quietly becomes the whole subtree."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/*.py")
            verdict = fence_verdict(archive, "src/auth/session.py",
                                    project_root=project)
        self.assertFalse(verdict["allowed"])


class HookEnforcementTests(unittest.TestCase):
    """Refused at the boundary, not reported after the write.

    A verdict nothing consults is a report, and this project already has
    reports. The fence only answers `nothing else moves` if the host is told
    `deny` before the edit lands.
    """

    HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"

    def _decide(self, project: Path, file_path: str) -> tuple[str, str]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": file_path},
            "cwd": str(project),
        }
        done = subprocess.run(
            [sys.executable, str(self.HOOK), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        )
        body = (done.stdout or "").strip()
        if not body:
            return "allow", ""
        specific = json.loads(body).get("hookSpecificOutput") or {}
        return (str(specific.get("permissionDecision", "?")),
                str(specific.get("permissionDecisionReason", "")))

    def test_an_edit_outside_the_declared_set_does_not_proceed_silently(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            decision, reason = self._decide(project, str(project / "src" / "billing" / "invoice.py"))
        self.assertNotEqual(decision, "allow", reason)
        self.assertIn("editable set", reason)

    def test_an_edit_inside_the_declared_set_is_ordinary_work(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "src/auth/**")
            decision, reason = self._decide(project, str(project / "src" / "auth" / "session.py"))
        self.assertEqual(decision, "allow", reason)

    def test_a_project_with_no_declared_fence_is_unaffected(self) -> None:
        """Every existing project has no fence, and none of them may start
        refusing edits because this shipped."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, None)
            decision, reason = self._decide(project, str(project / "anything.py"))
        self.assertEqual(decision, "allow", reason)


if __name__ == "__main__":
    unittest.main()
