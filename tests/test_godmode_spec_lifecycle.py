"""godmode-spec-lifecycle: the shipped skill's structure and its flow's commands.

Plan 7 Task 13 (NS-9): this skill routes to `planmode specify|start|check|
approve|bind`, `status remaining`, and `checkpoint` - verbs that already
exist and already carry their own contract tests. This module proves the
skill bundle is well-formed (frontmatter, PURPOSE.md citing a real seq:,
both companion files), and that every preflight command its Deterministic
Execution Flow names actually runs and exits the way the flow says it does,
on a disposable fixture project with its own `GODMODE_STATE_HOME` - never
the live project archive.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from godmode_runtime.godmode_forge import lint_skill, validate_skill  # noqa: E402
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402
from _host_env import scrubbed_env, scrubbed_environment  # noqa: E402

SKILL_DIR = PLUGIN_ROOT / "skills" / "godmode-spec-lifecycle"
GODMODE = PLUGIN_ROOT / "scripts" / "godmode.py"


@contextmanager
def _fixture_project():
    """A disposable, non-git project with its own GODMODE_STATE_HOME, so
    every archive write in this module lands nowhere near the real project
    archive - matching this repo's own fixture convention
    (`tests/test_godmode_codegraph.py`'s `_seeded_project`)."""
    with tempfile.TemporaryDirectory(prefix="godmode-spec-lifecycle-") as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "state"
        project.mkdir()
        with scrubbed_environment(GODMODE_STATE_HOME=str(state)):
            yield project, state


def _run(project: Path, state: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GODMODE), "--project", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=scrubbed_env(GODMODE_STATE_HOME=str(state)),
    )


class SkillBundleTests(unittest.TestCase):
    def test_structure_validates(self) -> None:
        result = validate_skill(SKILL_DIR)
        self.assertTrue(result["valid"], result)
        self.assertGreaterEqual(result["positive_cases"], 2)
        self.assertGreaterEqual(result["near_negative_cases"], 2)
        self.assertGreaterEqual(result["assertions"], 1)

    def test_bundle_lint_passes_all_four_facets(self) -> None:
        result = lint_skill(SKILL_DIR)
        self.assertTrue(result["passed"], result)
        for facet in ("scope", "delivery", "safety", "bundle"):
            self.assertTrue(result["facets"][facet]["passed"], (facet, result))

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

    def test_must_not_covers_self_approval(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never approve its own plan", text)

    def test_openai_yaml_is_hand_finished(self) -> None:
        text = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertNotIn("Generated locally by Godmode", text)
        self.assertNotIn("...", text)
        self.assertNotIn(
            "Use $godmode-spec-lifecycle to complete this request and prove its acceptance checks.",
            text,
        )


class FlowStepTests(unittest.TestCase):
    """Every preflight command the flow names, run on a seeded fixture
    project - never the live archive."""

    def _init_and_open(self, project: Path, state: Path) -> None:
        self.assertEqual(_run(project, state, "init").returncode, 0)
        self.assertEqual(_run(project, state, "session", "open").returncode, 0)

    def test_step2_specify_refuses_an_incomplete_spec(self) -> None:
        with _fixture_project() as (project, state):
            self._init_and_open(project, state)
            done = _run(project, state, "planmode", "specify", "--title", "t",
                        "--objective", "o")
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertIn("needs every field", done.stdout + done.stderr)

    def test_step2_specify_records_a_complete_spec(self) -> None:
        with _fixture_project() as (project, state):
            self._init_and_open(project, state)
            done = _run(project, state, "planmode", "specify", "--title", "t",
                        "--objective", "o", "--outcome", "out",
                        "--acceptance", "acc", "--non-goals", "ng")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            payload = json.loads(done.stdout)
            self.assertTrue(payload["id"].startswith("SPEC-"))

    def test_step3_start_names_missing_contract_fields_rather_than_waiving_them(self) -> None:
        with _fixture_project() as (project, state):
            self._init_and_open(project, state)
            _run(project, state, "planmode", "specify", "--title", "t", "--objective", "o",
                 "--outcome", "out", "--acceptance", "acc", "--non-goals", "ng")
            done = _run(project, state, "planmode", "start", "--title", "t",
                        "--objective", "o")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            payload = json.loads(done.stdout)
            self.assertIn("scope", payload["gaps"])

    def _drafted_plan(self, project: Path, state: Path) -> None:
        self._init_and_open(project, state)
        _run(project, state, "planmode", "specify", "--title", "t", "--objective", "o",
             "--outcome", "out", "--acceptance", "acc", "--non-goals", "ng")
        started = _run(project, state, "planmode", "start", "--title", "t",
                       "--objective", "o", "--acceptance", "acc", "--accept", "cmd:true",
                       "--scope", "a.py", "--out-of-scope", "b.py", "--current-state", "s",
                       "--assumptions", "as", "--parity", "p", "--steps", "st",
                       "--risk", "r", "--rollback", "rb", "--verification", "v",
                       "--points", "pt")
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertEqual(json.loads(started.stdout)["gaps"], [])

    def test_step4_check_reports_not_allowed_before_approval(self) -> None:
        with _fixture_project() as (project, state):
            self._drafted_plan(project, state)
            done = _run(project, state, "planmode", "check")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            payload = json.loads(done.stdout)
            self.assertFalse(payload["allowed"])

    def test_step5_approve_succeeds_on_a_complete_contract(self) -> None:
        with _fixture_project() as (project, state):
            self._drafted_plan(project, state)
            approved = _run(project, state, "planmode", "approve")
            self.assertEqual(approved.returncode, 0, approved.stdout + approved.stderr)
            self.assertTrue(json.loads(approved.stdout)["approved"])
            checked = _run(project, state, "planmode", "check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertTrue(json.loads(checked.stdout)["allowed"])

    def test_step6_bind_names_a_file_outside_declared_scope_as_drift(self) -> None:
        with _fixture_project() as (project, state):
            self._drafted_plan(project, state)
            self.assertEqual(_run(project, state, "planmode", "approve").returncode, 0)
            done = _run(project, state, "planmode", "bind", "--summary", "did the work",
                        "--file", "a.py", "--file", "outside.py")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            payload = json.loads(done.stdout)
            self.assertIn("outside.py", payload["outside_scope"])
            self.assertNotIn("a.py", payload["outside_scope"])

    def test_step8_status_remaining_runs_against_the_open_plan(self) -> None:
        with _fixture_project() as (project, state):
            self._drafted_plan(project, state)
            done = _run(project, state, "status", "remaining")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_step10_checkpoint_records_the_resumable_handoff(self) -> None:
        with _fixture_project() as (project, state):
            self._drafted_plan(project, state)
            done = _run(project, state, "checkpoint", "--summary", "drafted the plan",
                        "--status", "plan open, not yet approved", "--next", "approve then bind")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
