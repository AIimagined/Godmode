"""`GODMODE_STATE_HOME` means what its name says: with it set, every state
file a live session writes lands under it - the git project's archive
included - so a test harness that sets it can never reach the developer's
own `.git/godmode-state`."""

from __future__ import annotations

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

from godmode_runtime.godmode_anchor import application_home, resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402


def _git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True, capture_output=True)
    return repo


class StateHomeContainsEveryWriteTests(unittest.TestCase):
    def test_every_state_file_lands_under_the_variable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = _git_repo(Path(raw))
            state = Path(raw) / "state-home"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                anchor = resolve_anchor(repo)
                archive = Chronicle(anchor)
                archive.initialize()
                archive.append("decision", "one", {"status": "ruled"}, evidence=[])
                archive.append("checkpoint", "mid", {"status": "progress"})
                archive.read_events()
                home = application_home()
            self.assertTrue(anchor.is_git)
            self.assertEqual(home, state.resolve())
            self.assertTrue(Path(anchor.archive_root).is_relative_to(state.resolve()), anchor.archive_root)
            self.assertFalse((repo / ".git" / "godmode-state").exists(),
                             "a state file landed in the project's .git")
            written = [p for p in state.rglob("*") if p.is_file()]
            self.assertTrue(written)
            for path in written:
                self.assertTrue(path.is_relative_to(state.resolve()), path)

    def test_without_the_variable_the_git_archive_stays_beside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = _git_repo(Path(raw))
            environment = {k: v for k, v in os.environ.items() if k != "GODMODE_STATE_HOME"}
            with mock.patch.dict(os.environ, environment, clear=True):
                anchor = resolve_anchor(repo)
            self.assertEqual(Path(anchor.archive_root), (repo / ".git" / "godmode-state").resolve())


if __name__ == "__main__":
    unittest.main()
