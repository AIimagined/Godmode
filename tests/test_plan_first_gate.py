"""NS-13d: the edit that would make an unplanned change span a second file
needs an approved plan; a single-file change never does.

Every project here is a throwaway, non-git directory with its own state home.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_plan as plan  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

BIG = "\n".join(f"line {n}" for n in range(60))
FULL_CONTRACT = {field: f"{field} text" for field in plan.CONTRACT_FIELDS}
FULL_CONTRACT["accept"] = ["cmd:python -m unittest tests.test_x"]


class Workspace(unittest.TestCase):
    branch: str | None = "feature/work"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="godmode-plan-first-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.project = base / "project"
        self.project.mkdir()
        self.state = base / "state"
        env = mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(self.state)})
        env.start()
        self.addCleanup(env.stop)
        anchor = dataclasses.replace(resolve_anchor(self.project), branch=self.branch)
        self.archive = Chronicle(anchor)
        self.archive.initialize()

    def edited(self, relative: str) -> None:
        """What `hooks/godmode_post_edit.py` records after an edit."""
        self.archive.append("action", "edit-recorded", {"path": relative, "operation": "edit:x"},
                            evidence=[])

    def verdict(self, *relatives: str, tool_input: dict | None = None,
                policy: dict | None = None) -> dict:
        targets = [str(self.project / relative) for relative in relatives]
        return plan.plan_first_verdict(
            self.archive, targets, project_root=self.project,
            tool_input={"content": BIG} if tool_input is None else tool_input,
            policy=policy or {}, branch=self.branch)


class TheGate(Workspace):
    def test_a_single_file_edit_is_never_refused(self) -> None:
        self.assertTrue(self.verdict("a.py")["allowed"])
        self.edited("a.py")
        self.edited("a.py")
        self.assertTrue(self.verdict("a.py")["allowed"])

    def test_the_edit_that_adds_a_second_file_is_refused(self) -> None:
        self.edited("a.py")
        refused = self.verdict("b.py")
        self.assertFalse(refused["allowed"])
        self.assertEqual(refused["category"], "unplanned-multi-file-change")
        self.assertEqual(refused["tier"], "R2")
        self.assertEqual(refused["files"], ["a.py", "b.py"])

    def test_the_remedy_is_one_line_naming_how_to_record_and_approve_a_plan(self) -> None:
        self.edited("a.py")
        remedy = self.verdict("b.py")["remedy"]
        self.assertNotIn("\n", remedy)
        self.assertIn("godmode planmode specify", remedy)
        self.assertIn("godmode planmode approve", remedy)

    def test_one_call_naming_two_files_is_refused(self) -> None:
        self.assertFalse(self.verdict("a.py", "b.py")["allowed"])

    def test_a_small_edit_is_exempt(self) -> None:
        self.edited("a.py")
        small = {"old_string": "x = 1", "new_string": "x = 2"}
        self.assertTrue(self.verdict("b.py", tool_input=small)["allowed"])

    def test_a_small_edit_does_not_enroll_its_file(self) -> None:
        """Review H2: a small write to a second file, then a large write to
        the same file, must not pass as 'already part of the change'."""
        self.edited("a.py")
        small = self.verdict("b.py", tool_input={"content": "x = 1"})
        self.assertTrue(small["allowed"])
        self.assertEqual(small["exempt_files"], ["b.py"])
        plan.record_small_edit_exemption(self.archive, small["exempt_files"])
        self.edited("b.py")  # what the post-edit hook records next
        self.assertFalse(self.verdict("b.py")["allowed"])
        # A second small edit to it is still just a small edit.
        self.assertTrue(self.verdict("b.py", tool_input={"content": "x = 2"})["allowed"])

    def test_an_edit_of_unknown_size_is_not_assumed_small(self) -> None:
        self.edited("a.py")
        self.assertFalse(self.verdict("b.py", tool_input={})["allowed"])

    def test_a_file_already_in_the_change_passes(self) -> None:
        self.edited("a.py")
        self.edited("b.py")  # recorded before the gate existed, say
        self.assertTrue(self.verdict("b.py")["allowed"])
        self.assertFalse(self.verdict("c.py")["allowed"])

    def test_an_approved_plan_lifts_it(self) -> None:
        self.edited("a.py")
        plan.specify(self.archive, "S", "two-file change", {
            "objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"})
        plan.start(self.archive, "S", "two-file change", FULL_CONTRACT)
        self.assertFalse(self.verdict("b.py")["allowed"])  # open, not approved
        self.assertTrue(plan.approve(self.archive, "S")["approved"])
        self.assertTrue(self.verdict("b.py")["allowed"])

    def test_a_checkpoint_starts_a_new_change(self) -> None:
        self.edited("a.py")
        self.archive.append("checkpoint", "handoff", {"summary": "done"}, evidence=[])
        self.assertTrue(self.verdict("b.py")["allowed"])

    def test_the_policy_can_switch_it_off(self) -> None:
        self.edited("a.py")
        self.assertTrue(self.verdict("b.py", policy={"plan_first": "off"})["allowed"])
        self.assertFalse(self.verdict("b.py", policy={"plan_first": "on"})["allowed"])

    def test_a_target_outside_the_project_is_not_counted(self) -> None:
        self.edited("a.py")
        outside = plan.plan_first_verdict(
            self.archive, [str(self.project.parent / "elsewhere.py")], project_root=self.project,
            tool_input={"content": BIG}, policy={}, branch=self.branch)
        self.assertTrue(outside["allowed"])


class ThrowawayBranch(Workspace):
    branch = "spike/idea"

    def test_a_spike_skips_the_gate(self) -> None:
        self.edited("a.py")
        self.assertTrue(self.verdict("b.py")["allowed"])

    def test_declaring_the_spike_maintained_brings_it_back(self) -> None:
        self.edited("a.py")
        self.archive.append("branch", "git-topology",
                            {"branch": "spike/idea", "role": "maintained"}, evidence=[])
        self.assertFalse(self.verdict("b.py")["allowed"])


class DeclaredThrowaway(Workspace):
    branch = "main"

    def test_an_agent_declaration_of_throwaway_changes_nothing(self) -> None:
        """Review B2: the agent held to the gate cannot declare its way out."""
        self.edited("a.py")
        self.archive.append("branch", "git-topology",
                            {"branch": "main", "role": "throwaway"}, evidence=[])
        self.assertFalse(self.verdict("b.py")["allowed"])

    def test_an_operator_declaration_of_throwaway_skips_it(self) -> None:
        self.edited("a.py")
        self.archive.append("branch", "git-topology", {"branch": "main", "role": "throwaway"},
                            evidence=[], as_operator=True, operator_verified=True)
        self.assertTrue(self.verdict("b.py")["allowed"])


class EditSize(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertEqual(plan.edit_size_lines({"old_string": "a\nb", "new_string": "c"}), 2)
        self.assertEqual(plan.edit_size_lines({"content": BIG}), 60)
        self.assertEqual(plan.edit_size_lines(
            {"edits": [{"old_string": "a", "new_string": "b\nc"}, {"new_string": "d"}]}), 3)
        self.assertEqual(plan.edit_size_lines({"new_source": "x\ny"}), 2)
        self.assertEqual(plan.edit_size_lines(
            {"input": "*** Update File: a\n+new\n-old\n context"}), 2)
        self.assertIsNone(plan.edit_size_lines({}))
        self.assertIsNone(plan.edit_size_lines(None))


class PolicyKey(unittest.TestCase):
    def test_plan_first_is_validated_and_composed_tightest_wins(self) -> None:
        from godmode_runtime.godmode_sentinel import compose_policies
        self.assertEqual(compose_policies({}, {"plan_first": "off"}), {"plan_first": "off"})
        self.assertEqual(compose_policies({"plan_first": "on"}, {"plan_first": "off"}),
                         {"plan_first": "on"})


class ThroughTheHook(unittest.TestCase):
    """The real gate script, fed a Claude Edit payload."""

    def run_hook(self, project: Path, state: Path, target: str, content: str = BIG) -> str:
        body = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                           "tool_input": {"file_path": str(project / target), "content": content},
                           "cwd": str(project)})
        done = subprocess.run([sys.executable, str(HOOKS / "godmode_gate_fast.py")], input=body,
                              capture_output=True, text=True, timeout=120, cwd=str(project),
                              env=scrubbed_env(GODMODE_STATE_HOME=str(state)))
        return done.stdout

    def make(self, initialized: bool) -> tuple[Path, Path]:
        tmp = tempfile.TemporaryDirectory(prefix="godmode-plan-first-hook-")
        self.addCleanup(tmp.cleanup)
        project, state = Path(tmp.name) / "project", Path(tmp.name) / "state"
        project.mkdir()
        if initialized:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                archive.append("action", "edit-recorded", {"path": "a.py", "operation": "edit:x"},
                               evidence=[])
        return project, state

    def test_the_second_file_is_stopped_with_its_remedy(self) -> None:
        project, state = self.make(initialized=True)
        out = self.run_hook(project, state, "b.py")
        self.assertIn("unplanned multi-file change", out)
        self.assertIn("godmode planmode approve", out)

    def test_a_small_write_then_a_large_one_to_the_same_file_is_stopped(self) -> None:
        project, state = self.make(initialized=True)
        first = self.run_hook(project, state, "b.py", content="x = 1")
        self.assertNotIn("unplanned multi-file change", first)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}):
            Chronicle(resolve_anchor(project)).append(
                "action", "edit-recorded", {"path": "b.py", "operation": "edit:b"}, evidence=[])
        second = self.run_hook(project, state, "b.py")
        self.assertIn("unplanned multi-file change", second)

    def test_the_first_file_passes(self) -> None:
        project, state = self.make(initialized=True)
        out = self.run_hook(project, state, "a.py")
        self.assertNotIn("unplanned multi-file change", out)

    def test_an_uninitialized_project_is_never_gated(self) -> None:
        project, state = self.make(initialized=False)
        out = self.run_hook(project, state, "b.py")
        self.assertNotIn("unplanned multi-file change", out)
        self.assertNotIn('"deny"', out)
        self.assertNotIn('"ask"', out)
        self.assertFalse(state.exists() and any(state.rglob("*.json")),
                         "the hook must not initialize an ungoverned project")


if __name__ == "__main__":
    unittest.main()
