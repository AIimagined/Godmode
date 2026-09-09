"""Field report 22 (2026-09-09): memory kills unnamed, nags after
`--status blocked`, and a preflight that could only run after a gated
commit. Each con becomes a behaviour here.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_precheck import failure_nudge  # noqa: E402
from godmode_runtime.godmode_preflight import push_preflight  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_session_hook import _open_obligations_touched  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)


class MemoryKillTests(unittest.TestCase):
    def test_a_memory_kill_names_the_bound_and_the_failure_class(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            text = failure_nudge(archive, "python -m unittest ...\nKilled\nexit 137", "s1")
            self.assertIsNotNone(text)
            self.assertIn("watchdog", text)
            self.assertIn("memory-kill", text)

    def test_an_ordinary_failure_keeps_the_rca_text(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            text = failure_nudge(archive, "Traceback (most recent call last):\nValueError: x", "s1")
            self.assertIn("error-pattern", text)
            self.assertNotIn("memory-kill", text)


class BlockedObligationTests(unittest.TestCase):
    def test_a_blocked_obligation_is_not_nagged(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("obligation", "widen the launcher interpreter discovery on Windows",
                           {"status": "open", "value": "launcher interpreter discovery windows"}, evidence=[])
            reply = "The launcher interpreter discovery on Windows still needs the store alias handled."
            self.assertEqual(len(_open_obligations_touched(archive, reply)), 1)
            archive.append("obligation", "widen the launcher interpreter discovery on Windows",
                           {"status": "blocked", "value": "waiting on the host"}, evidence=[])
            self.assertEqual(_open_obligations_touched(archive, reply), [])


class DirtyPreflightTests(unittest.TestCase):
    def test_a_dirty_tree_is_refused_by_default_and_validated_with_dirty(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _git(project, "init", "-q")
            (project / "a.txt").write_text("one\n", encoding="utf-8")
            _git(project, "add", "a.txt")
            _git(project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first")
            (project / "a.txt").write_text("two\n", encoding="utf-8")
            with self.assertRaises(ArchiveError):
                push_preflight(project)
            report = push_preflight(project, dirty=True)
            self.assertIn("working-tree snapshot", report["validated"])
            self.assertEqual(report["cleanup"], "confirmed")
            # The working tree itself is untouched by the snapshot.
            self.assertEqual((project / "a.txt").read_text(encoding="utf-8"), "two\n")

    def test_a_clean_tree_validates_head(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _git(project, "init", "-q")
            (project / "a.txt").write_text("one\n", encoding="utf-8")
            _git(project, "add", "a.txt")
            _git(project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first")
            self.assertEqual(push_preflight(project, dirty=True)["validated"], "HEAD")


if __name__ == "__main__":
    unittest.main()
