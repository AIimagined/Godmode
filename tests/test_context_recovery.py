"""Context recovery under git crisis, scoped lessons, and the evidence ladder.

Why these tests exist: a mid-rebase or mid-merge repository used to read as
merely "dirty", so a resuming agent would start substantive work on top of an
unfinished operation; lessons recorded in one project used to leak verbatim
into another; and a claim could jump from observation straight to verified
with nothing in between. Each test pins the guard that stops one of those.
"""

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
    EVIDENCE_LEVELS,
    advance_evidence,
    lessons_for,
    opening_handshake,
    record_lesson_scoped,
)
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_lens import (  # noqa: E402
    detect_context_issues,
    observe_git,
    repo_state,
)


@contextmanager
def isolated_git_project():
    """A committed git repo plus its archive, with git identity pinned locally."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        (project / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        env = {"GODMODE_STATE_HOME": str(state), "GIT_CONFIG_GLOBAL": str(base / "gitconfig")}
        with mock.patch.dict(os.environ, env, clear=False):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project)]
            subprocess.run(git[:1] + ["init", "-q", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True, capture_output=True)
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive, anchor, git


def make_merge_conflict(project: Path, git: list[str]) -> None:
    """Two branches editing the same line, merged, so MERGE_HEAD survives."""
    subprocess.run(git + ["checkout", "-q", "-b", "feature"], check=True, capture_output=True)
    (project / "app.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8")
    subprocess.run(git + ["commit", "-q", "-am", "feature edit"], check=True, capture_output=True)
    subprocess.run(git + ["checkout", "-q", "-"], check=True, capture_output=True)
    (project / "app.py").write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")
    subprocess.run(git + ["commit", "-q", "-am", "main edit"], check=True, capture_output=True)
    merged = subprocess.run(git + ["merge", "feature"], capture_output=True, text=True)
    if merged.returncode == 0:
        raise AssertionError("fixture expected a merge conflict but the merge succeeded")


class RepoStateTests(unittest.TestCase):
    def test_clean_repo_reports_no_crisis(self) -> None:
        with isolated_git_project() as (project, _archive, _anchor, _git):
            state = repo_state(project)
            self.assertEqual(state["in_progress"], [])
            self.assertFalse(state["detached"])
            self.assertEqual(state["stash_depth"], 0)
            self.assertFalse(state["crisis"])

    def test_merge_conflict_reports_merging_and_crisis(self) -> None:
        with isolated_git_project() as (project, _archive, _anchor, git):
            make_merge_conflict(project, git)
            state = repo_state(project)
            self.assertIn("merging", state["in_progress"])
            self.assertTrue(state["crisis"])

    def test_detached_head_is_detected(self) -> None:
        with isolated_git_project() as (project, _archive, _anchor, git):
            subprocess.run(
                git + ["checkout", "-q", "--detach"], check=True, capture_output=True
            )
            state = repo_state(project)
            self.assertTrue(state["detached"])
            self.assertTrue(state["crisis"])
            self.assertEqual(state["in_progress"], [])

    def test_stash_depth_counts_stashed_entries(self) -> None:
        with isolated_git_project() as (project, _archive, _anchor, git):
            (project / "app.py").write_text("def add(a, b):\n    return a + b  # x\n",
                                            encoding="utf-8")
            subprocess.run(git + ["stash", "push", "-q"], check=True, capture_output=True)
            state = repo_state(project)
            self.assertEqual(state["stash_depth"], 1)
            self.assertFalse(state["crisis"])

    def test_observe_git_carries_repo_state(self) -> None:
        with isolated_git_project() as (project, _archive, anchor, git):
            make_merge_conflict(project, git)
            observed = observe_git(anchor)
            self.assertIn("state", observed)
            self.assertIn("merging", observed["state"]["in_progress"])
            self.assertTrue(observed["state"]["crisis"])

    def test_context_issues_warn_about_in_progress_operation(self) -> None:
        with isolated_git_project() as (project, archive, anchor, git):
            make_merge_conflict(project, git)
            issues = detect_context_issues(anchor, archive.read_events(), None)
            by_code = {issue["code"]: issue for issue in issues}
            self.assertIn("repo-in-progress-operation", by_code)
            found = by_code["repo-in-progress-operation"]
            self.assertEqual(found["severity"], "warning")
            self.assertIn("merging", found["detail"])
            self.assertIn("finish or abort", found["detail"])

    def test_context_issues_stay_silent_on_a_clean_repo(self) -> None:
        with isolated_git_project() as (_project, archive, anchor, _git):
            issues = detect_context_issues(anchor, archive.read_events(), None)
            codes = {issue["code"] for issue in issues}
            self.assertNotIn("repo-in-progress-operation", codes)


class HandshakeCrisisTests(unittest.TestCase):
    def test_handshake_carries_repo_state_and_warning_under_crisis(self) -> None:
        with isolated_git_project() as (project, archive, anchor, git):
            make_merge_conflict(project, git)
            handshake = opening_handshake(archive, anchor, project)
            self.assertIn("repo_state", handshake)
            self.assertTrue(handshake["repo_state"]["crisis"])
            self.assertIn("warning", handshake)
            self.assertIn("merging", handshake["warning"])
            # repo_state sits directly after dirty_files in the fixed order.
            keys = list(handshake.keys())
            self.assertEqual(keys.index("repo_state"), keys.index("dirty_files") + 1)

    def test_handshake_omits_warning_when_calm(self) -> None:
        with isolated_git_project() as (project, archive, anchor, _git):
            handshake = opening_handshake(archive, anchor, project)
            self.assertFalse(handshake["repo_state"]["crisis"])
            self.assertNotIn("warning", handshake)


class ScopedLessonTests(unittest.TestCase):
    def test_lessons_are_filtered_by_project_tag(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            record_lesson_scoped(
                archive, "flush-buffers", "flush before close",
                project_tag="alpha", surface="io", framework="stdlib",
            )
            record_lesson_scoped(
                archive, "other-project-habit", "belongs elsewhere",
                project_tag="beta",
            )
            mine = lessons_for(archive, "alpha")
            self.assertEqual([r["subject"] for r in mine], ["flush-buffers"])
            data = mine[0]["data"]
            self.assertEqual(data["project_tag"], "alpha")
            self.assertEqual(data["surface"], "io")
            self.assertEqual(data["framework"], "stdlib")
            self.assertEqual(data["confidence"], "observed")

    def test_portable_lessons_cross_project_boundaries(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            record_lesson_scoped(archive, "local-only", "stays home", project_tag="beta")
            archive.append(
                "lesson", "universal-truth",
                {"value": "always read before writing", "portable": True,
                 "project_tag": "beta"},
            )
            subjects = [r["subject"] for r in lessons_for(archive, "alpha")]
            self.assertEqual(subjects, ["universal-truth"])

    def test_scoped_lesson_requires_a_project_tag(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            with self.assertRaises(ArchiveError):
                record_lesson_scoped(archive, "untagged", "value", project_tag="  ")


class EvidenceLadderTests(unittest.TestCase):
    def test_ladder_names_all_seven_levels_in_order(self) -> None:
        self.assertEqual(
            EVIDENCE_LEVELS,
            ("observation", "hypothesis", "corroborated", "rooted",
             "fixed-locally", "verified", "closed"),
        )

    def test_single_step_advances_are_allowed(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            first = advance_evidence(archive, "flaky-io", "observation", "cmd:pytest -k io")
            self.assertEqual(first["data"]["evidence_level"], "observation")
            second = advance_evidence(archive, "flaky-io", "hypothesis", "cmd:pytest -k io")
            self.assertEqual(second["data"]["previous_level"], "observation")

    def test_observation_to_verified_jump_is_refused(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            advance_evidence(archive, "flaky-io", "observation", "cmd:pytest -k io")
            with self.assertRaises(ArchiveError):
                advance_evidence(archive, "flaky-io", "verified", "cmd:pytest -k io")

    def test_downward_moves_need_a_reason_and_then_pass(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            advance_evidence(archive, "flaky-io", "observation", "cmd:pytest -k io")
            advance_evidence(archive, "flaky-io", "hypothesis", "cmd:pytest -k io")
            with self.assertRaises(ArchiveError):
                advance_evidence(archive, "flaky-io", "observation", "cmd:pytest -k io")
            demoted = advance_evidence(
                archive, "flaky-io", "observation", "cmd:pytest -k io",
                reason="repro no longer holds on main",
            )
            self.assertEqual(demoted["data"]["direction"], "down")
            self.assertIn("repro", demoted["data"]["reason"])

    def test_unknown_level_is_refused(self) -> None:
        with isolated_git_project() as (_project, archive, _anchor, _git):
            with self.assertRaises(ArchiveError):
                advance_evidence(archive, "flaky-io", "certain", "cmd:pytest")


if __name__ == "__main__":
    unittest.main()
