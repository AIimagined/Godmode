"""N-13: the Codex discovery premise.

`hooks wire --host codex` refuses from a linked worktree (exit 2, no
writes), naming the primary checkout path; `hooks probe --host codex`
records `codex features list`'s own output in the probe record's `premise`
field before any live claim about the probe itself; `hooks status` shows
the same premise. `ProjectAnchor` carries no `git_dir` field - only
`git_common_dir` and `worktree_root` - so "linked worktree" is derived
honestly from those two (see `godmode_anchor.is_linked_worktree`), not from
a comparison this codebase has never had the fields for.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import (  # noqa: E402
    is_linked_worktree, primary_checkout_root, resolve_anchor,
)
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_hooks  # noqa: E402
from godmode_runtime.godmode_hookproof import codex_runtime_premise, run_probe  # noqa: E402


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _run_git(["init", "-q"], path)
    _run_git(["config", "user.email", "codex-premise-test@example.com"], path)
    _run_git(["config", "user.name", "Codex Premise Test"], path)
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    _run_git(["add", "README.md"], path)
    _run_git(["commit", "-q", "-m", "init"], path)


def _write_fake_codex(directory: Path, *, stdout: str, exit_code: int = 0) -> None:
    """A `codex` binary that never talks to a real Codex install - only
    proves this code reads its own subprocess's stdout/exit code honestly."""
    if os.name == "nt":
        script = directory / "codex.cmd"
        script.write_text(f"@echo off\r\necho {stdout}\r\nexit /b {exit_code}\r\n", encoding="utf-8")
    else:
        script = directory / "codex"
        script.write_text(f"#!/bin/sh\necho '{stdout}'\nexit {exit_code}\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _fake_codex_env(fake_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = str(fake_dir) + os.pathsep + env.get("PATH", "")
    return env


class CodexRuntimePremiseUnitTests(unittest.TestCase):
    """`codex_runtime_premise` in isolation - no probe, no wire, no CLI."""

    def test_absent_binary_reads_unavailable_never_a_guess(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir:
            with mock.patch.dict(os.environ, {"PATH": empty_dir}, clear=False):
                premise = codex_runtime_premise()
        self.assertEqual(premise["state"], "unavailable")
        self.assertIsInstance(premise["reason"], str)
        self.assertIn("PATH", premise["reason"])
        self.assertIsNone(premise["output"])

    def test_a_nonzero_exit_also_reads_unavailable_with_its_own_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            _write_fake_codex(fake_dir, stdout="boom", exit_code=1)
            with mock.patch.dict(os.environ, _fake_codex_env(fake_dir), clear=False):
                premise = codex_runtime_premise()
        self.assertEqual(premise["state"], "unavailable")
        self.assertIn("exited 1", premise["reason"])

    def test_a_working_binary_records_its_stdout_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake_dir = Path(temp)
            _write_fake_codex(fake_dir, stdout="{\"hooks\":\"stable\"}")
            with mock.patch.dict(os.environ, _fake_codex_env(fake_dir), clear=False):
                premise = codex_runtime_premise()
        self.assertEqual(premise["state"], "recorded")
        self.assertIsNone(premise["reason"])
        self.assertIn("hooks", premise["output"])


class CodexProbeRecordsThePremiseTests(unittest.TestCase):
    def test_probe_carries_the_premise_field_before_any_live_claim(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            fake_dir = base / "bin"
            fake_dir.mkdir()
            _write_fake_codex(fake_dir, stdout="{\"hooks\":\"stable\"}")
            env = _fake_codex_env(fake_dir)
            env["GODMODE_STATE_HOME"] = str(base / "state")
            with mock.patch.dict(os.environ, env, clear=False):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                report = run_probe(project, archive, "codex")
        self.assertIn("premise", report)
        self.assertEqual(report["premise"]["state"], "recorded")
        # The premise is set before `denied`/`proof_recorded`/`state` are
        # computed (see `run_probe`'s source order): it never depends on,
        # and is never overwritten by, the self-injection outcome below it.
        self.assertIn("denied", report)
        self.assertIn("proof_recorded", report)

    def test_probe_premise_is_unavailable_when_codex_is_not_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with tempfile.TemporaryDirectory() as empty_dir:
                env = {"PATH": empty_dir, "GODMODE_STATE_HOME": str(base / "state")}
                with mock.patch.dict(os.environ, env, clear=False):
                    anchor = resolve_anchor(project)
                    archive = Chronicle(anchor)
                    archive.initialize()
                    report = run_probe(project, archive, "codex")
        self.assertEqual(report["premise"]["state"], "unavailable")

    def test_probe_for_a_different_host_carries_no_codex_premise(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                report = run_probe(project, archive, "claude")
        self.assertNotIn("premise", report)


class CodexStatusShowsThePremiseTests(unittest.TestCase):
    def test_hooks_status_shows_the_premise_for_codex(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            fake_dir = base / "bin"
            fake_dir.mkdir()
            _write_fake_codex(fake_dir, stdout="{\"hooks\":\"stable\"}")
            env = _fake_codex_env(fake_dir)
            env["GODMODE_STATE_HOME"] = str(base / "state")
            with mock.patch.dict(os.environ, env, clear=False):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="status", host="codex", git=False)
                result = cmd_hooks(args, runtime)
        self.assertIn("premise", result.payload)
        self.assertEqual(result.payload["premise"]["state"], "recorded")

    def test_hooks_status_never_carries_a_codex_premise_for_another_host(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="status", host="claude", git=False)
                result = cmd_hooks(args, runtime)
        self.assertNotIn("premise", result.payload)


class LinkedWorktreeRefusalTests(unittest.TestCase):
    """A real `git worktree add`, not a mock - the refusal must survive
    actual git plumbing, not just a hand-built anchor."""

    def test_wire_refuses_from_a_real_linked_worktree_naming_the_primary_checkout(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)
            worktree = base / "linked"
            _run_git(["worktree", "add", str(worktree), "-b", "wt-branch"], primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(worktree)
                self.assertTrue(is_linked_worktree(anchor))
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host="codex", force=False)
                result = cmd_hooks(args, runtime)

                self.assertEqual(result.exit_code, 2)
                self.assertFalse((worktree / ".codex" / "hooks.json").exists())
                self.assertEqual(
                    result.payload["primary_checkout"], str(primary_checkout_root(anchor))
                )
                self.assertEqual(Path(result.payload["primary_checkout"]).name, "primary")

    def test_wire_passes_from_the_primary_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(primary)
                self.assertFalse(is_linked_worktree(anchor))
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host="codex", force=False)
                result = cmd_hooks(args, runtime)

                self.assertEqual(result.exit_code, 0)
                self.assertTrue(result.payload["written"])
                self.assertTrue((primary / ".codex" / "hooks.json").exists())

    def test_wire_still_refuses_a_second_time_without_writing_anything(self) -> None:
        # No lingering state from a failed attempt should ever flip this to
        # a pass; each call re-derives the anchor fresh.
        with tempfile.TemporaryDirectory() as base_temp:
            base = Path(base_temp)
            primary = base / "primary"
            primary.mkdir()
            _init_repo(primary)
            worktree = base / "linked"
            _run_git(["worktree", "add", str(worktree), "-b", "wt-branch"], primary)

            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(worktree)
                archive = Chronicle(anchor)
                archive.initialize()
                runtime = Runtime(anchor=anchor, archive=archive)
                args = argparse.Namespace(hooks_command="wire", host="codex", force=False)
                first = cmd_hooks(args, runtime)
                second = cmd_hooks(args, runtime)

                self.assertEqual(first.exit_code, 2)
                self.assertEqual(second.exit_code, 2)
                self.assertFalse((worktree / ".codex").exists())


if __name__ == "__main__":
    unittest.main()


class RecordedPremiseIsBoundedTests(unittest.TestCase):
    def test_a_verbose_runtime_output_is_capped(self) -> None:
        import shutil
        import subprocess as sp
        from unittest import mock
        from godmode_runtime import godmode_hookproof as hp
        fake = sp.CompletedProcess(args=["codex", "features", "list"],
                                   returncode=0, stdout="x" * 10_000, stderr="")
        with mock.patch.object(shutil, "which", return_value="codex"):
            with mock.patch.object(hp.subprocess, "run", return_value=fake):
                premise = hp.codex_runtime_premise()
        self.assertEqual(premise["state"], "recorded")
        self.assertLessEqual(len(premise["output"]), 2000)
