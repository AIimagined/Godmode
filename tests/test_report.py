from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import (  # noqa: E402
    open_session,
    record_claim,
    record_step,
)
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_plan import (  # noqa: E402
    approve,
    bind_execution,
    specify,
    start,
)
from godmode_runtime.godmode_report import (  # noqa: E402
    FIELD_ORDER,
    UNCERTAINTY_LABELS,
    completion_report,
    render_markdown,
)


@contextmanager
def isolated_git_project():
    """A committed git repo with one passing test file, plus its archive.

    Local copy of the fixture in test_godmode_runtime.py, so this module runs
    on its own without importing another test module's helpers.
    """
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        (project / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (project / "tests").mkdir()
        (project / "tests" / "test_app.py").write_text(
            "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n    assert add(0, 0) == 0\n",
            encoding="utf-8",
        )
        env = {"GODMODE_STATE_HOME": str(state), "GIT_CONFIG_GLOBAL": str(base / "gitconfig")}
        with mock.patch.dict(os.environ, env, clear=False):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project)]
            subprocess.run(git[:1] + ["init", "-q", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True, capture_output=True)
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


def _approved_plan(archive, session, title="ship subtraction"):
    specify(archive, session, title, {
        "objective": "add a subtraction helper",
        "outcome": "sub() exists and is tested",
        "acceptance": "the suite covers sub()",
        "non_goals": "multiplication",
    })
    start(archive, session, title, {
        "objective": "add a subtraction helper",
        "acceptance": "the suite covers sub()",
        "accept": "cmd:python -m unittest",
        "scope": "app.py tests/test_app.py",
        "out_of_scope": "multiplication",
        "current_state": "only add() exists",
        "assumptions": "integers only",
        "parity": "mirrors add()",
        "steps": "write test; write sub(); run suite",
        "risk": "none identified",
        "rollback": "revert the commit",
        "verification": "python -m unittest",
        "points": "1",
    })
    assert approve(archive, session)["approved"]


class CompletionReportTests(unittest.TestCase):
    def test_verified_session_derives_verified(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "ship subtraction")
            _approved_plan(archive, session)
            bind_execution(archive, session, "wire subtraction", ["app.py"])
            record_claim(
                archive, project, session,
                "The add function returns a sum.", "verified",
                cites=["file:app.py#L2"],
            )
            # E62: the plan's accept command needs a this-session attestation
            # too, or `close_session` (and so `status`) stays short of verified.
            record_step(archive, session, "check:subtraction", "ran", result="exit 0",
                       evidence=["cmd:python -m unittest"])
            report = completion_report(archive, archive.anchor, project, session=session)
            fields = report["fields"]

            self.assertEqual(sorted(fields), sorted(FIELD_ORDER))
            self.assertEqual(fields["status"]["value"], "verified")
            self.assertEqual(fields["status"]["label"], "verified")
            self.assertEqual(fields["task"]["value"], "ship subtraction")
            self.assertIn("app.py", str(fields["what_changed"]["detail"]))
            self.assertIn("file:app.py#L2", fields["evidence"]["detail"])
            self.assertEqual(
                fields["security_privacy"]["value"],
                "no secret-shaped values in staged content",
            )
            for name in FIELD_ORDER:
                self.assertIn(fields[name]["label"], UNCERTAINTY_LABELS, name)

    def test_uncited_claim_derives_partially_verified(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "quick tweak")
            archive.append("change", "tweak app", {"session": session, "files": ["app.py"]})
            record_claim(archive, project, session, "Everything is wired.", "verified")
            report = completion_report(archive, archive.anchor, project, session=session)
            status = report["fields"]["status"]
            self.assertEqual(status["value"], "partially verified")
            self.assertEqual(status["label"], "observed")

    def test_no_change_records_derives_no_change_required(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "just looking")
            report = completion_report(archive, archive.anchor, project, session=session)
            self.assertEqual(report["fields"]["status"]["value"], "no change required")

    def test_blocked_gate_derives_blocked(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "blocked work")
            archive.append("change", "attempt fix", {"session": session, "files": ["app.py"]})
            record_step(archive, session, "check:suite", "blocked",
                        result="exit 1", reason="suite failed")
            report = completion_report(archive, archive.anchor, project, session=session)
            status = report["fields"]["status"]
            self.assertEqual(status["value"], "blocked")
            self.assertEqual(status["label"], "blocked")
            self.assertIn("check:suite", report["fields"]["next_safe_action"]["value"])

    def test_next_safe_action_prefers_latest_checkpoint(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "checkpointed work")
            archive.append("checkpoint", "midway", {"status": "green", "next": "run the suite once more"})
            report = completion_report(archive, archive.anchor, project, session=session)
            self.assertEqual(
                report["fields"]["next_safe_action"]["value"],
                "run the suite once more",
            )
            self.assertEqual(report["fields"]["next_safe_action"]["label"], "hypothesis")

    def test_render_contains_title_and_every_field(self) -> None:
        with isolated_git_project() as (project, archive):
            session = open_session(archive, "render check")
            report = completion_report(archive, archive.anchor, project, session=session)
            rendered = render_markdown(report)
            self.assertIn("TASK COMPLETION REPORT", rendered)
            positions = [rendered.index(f"| {name} |") for name in FIELD_ORDER]
            self.assertEqual(positions, sorted(positions), "field order must be deterministic")
            self.assertEqual(rendered, render_markdown(report))

    def test_non_git_project_is_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                session = open_session(archive, "non-git")
                report = completion_report(archive, archive.anchor, project, session=session)
                fields = report["fields"]
                self.assertEqual(fields["git_state"]["value"], "not a Git repository")
                self.assertEqual(fields["security_privacy"]["label"], "hypothesis")
                self.assertNotEqual(
                    fields["security_privacy"]["value"],
                    "no secret-shaped values in staged content",
                )
                self.assertEqual(fields["documentation"]["label"], "hypothesis")


if __name__ == "__main__":
    unittest.main()
