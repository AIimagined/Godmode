"""godmode-host-sync: the shipped skill's structure and its flow's commands.

Plan 7 Task 13 (NS-9): this skill routes to `hooks status`, `hooks wire
--all`, `hooks probe`, and `doctor` - verbs that already exist and already
carry their own test suites. This module proves two different things: the
skill bundle itself is well-formed (frontmatter, PURPOSE.md citing a real
seq:, both companion files), and every preflight command its Deterministic
Execution Flow names actually runs and exits the way the flow says it does,
on a disposable fixture project - never the live project archive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_forge import validate_skill  # noqa: E402
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import scrubbed_env  # noqa: E402

SKILL_DIR = PLUGIN_ROOT / "skills" / "godmode-host-sync"
GODMODE = PLUGIN_ROOT / "scripts" / "godmode.py"


@contextmanager
def _fixture_project():
    with tempfile.TemporaryDirectory(prefix="godmode-host-sync-") as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            yield project, state


def _run(project: Path, state: Path, *args: str) -> subprocess.CompletedProcess:
    # The attendance ratchet requires a scrubbed host environment for any
    # spawn of the shipped CLI: an inherited host environment leaks the
    # operator session and its attendance signals into the child.
    environment = scrubbed_env(GODMODE_STATE_HOME=str(state))
    return subprocess.run(
        [sys.executable, str(GODMODE), "--project", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=environment,
    )


class SkillBundleTests(unittest.TestCase):
    def test_structure_validates(self) -> None:
        result = validate_skill(SKILL_DIR)
        self.assertTrue(result["valid"], result)
        self.assertGreaterEqual(result["positive_cases"], 2)
        self.assertGreaterEqual(result["near_negative_cases"], 2)
        self.assertGreaterEqual(result["assertions"], 1)

    def test_frontmatter_lint_passes_with_no_findings(self) -> None:
        result = lint_frontmatter(SKILL_DIR)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["findings"], [])

    def test_purpose_cites_a_real_seq(self) -> None:
        text = (SKILL_DIR / "PURPOSE.md").read_text(encoding="utf-8")
        self.assertIn("seq:", text)

    def test_description_carries_a_negative_scope_clause(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Not for", text)

    def test_evals_file_has_the_required_rows(self) -> None:
        data = json.loads((SKILL_DIR / "godmode-evals.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["routing"]["positive"]), 2)
        self.assertGreaterEqual(len(data["routing"]["near_negative"]), 2)
        self.assertTrue(data["behavior_assertions"])


class FlowStepTests(unittest.TestCase):
    """Every preflight command the flow names, run on a fixture project."""

    def test_step1_hooks_status_exits_clean(self) -> None:
        with _fixture_project() as (project, state):
            done = _run(project, state, "hooks", "status")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertIn("wire_state", payload)

    def test_step2_dry_run_preview_writes_nothing(self) -> None:
        with _fixture_project() as (project, state):
            done = _run(project, state, "hooks", "wire", "--all", "--dry-run")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload["changed"], [])
            self.assertEqual(payload["summary"], "safe to apply")
            self.assertFalse((project / ".codex").exists())

    def test_step2_fallback_a_linked_worktree_names_the_primary_checkout(self) -> None:
        """This project's own worktree is the fallback case the flow documents:
        `hooks wire` for codex refuses from a linked worktree and names the
        primary checkout to switch to, rather than silently doing nothing."""
        with tempfile.TemporaryDirectory(prefix="godmode-host-sync-state-") as raw:
            state = Path(raw)
            done = _run(PLUGIN_ROOT, state, "hooks", "wire", "--host", "codex", "--dry-run")
            if done.returncode == 0:
                self.skipTest("this checkout is not a linked worktree")
            self.assertEqual(done.returncode, 2, done.stderr)
            payload = json.loads(done.stdout)
            self.assertIn("primary_checkout", payload)
            self.assertIn("refuses from a linked worktree", payload["refused"])

    def test_step3_apply_then_status_reports_it(self) -> None:
        with _fixture_project() as (project, state):
            applied = _run(project, state, "hooks", "wire", "--all")
            self.assertEqual(applied.returncode, 0, applied.stderr)
            payload = json.loads(applied.stdout)
            self.assertIn("codex", payload["changed"])
            self.assertTrue((project / ".codex" / "hooks.json").is_file())
            status = _run(project, state, "hooks", "status")
            self.assertEqual(status.returncode, 0, status.stderr)

    def test_step4_probe_denies_and_records_a_proof(self) -> None:
        with _fixture_project() as (project, state):
            self.assertEqual(_run(project, state, "init").returncode, 0)
            # The host label is passed explicitly rather than detected: the
            # spawn runs under a scrubbed environment with no host markers,
            # so an ambient detection would record the proof under "unknown".
            done = _run(project, state, "hooks", "probe", "--host", "codex")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertTrue(payload["denied"])
            self.assertTrue(payload["proof_recorded"])

    def test_step5_doctor_scoped_to_one_host_is_healthy(self) -> None:
        with _fixture_project() as (project, state):
            done = _run(project, state, "doctor", "--host", "codex")
            self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
