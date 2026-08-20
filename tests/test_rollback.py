"""B6-A: rollback to the last commit something actually proved green.

The archive already holds checkpoints carrying a `head` commit, but their
`status` is free prose - "865 tests OK on the frozen tagged tree" is a
sentence, not a fact a machine may act on. Reading a restore point out of
prose is the inference this project's own doctrine refuses everywhere
else, so green is *attested with evidence* instead: the command that ran,
the exit code it returned, and the commit it ran against.

Two properties are pinned hard, because both are the kind of thing that
looks like a nicety until the day it matters:

* **A failing run cannot be marked green.** Otherwise the restore point is
  a commit nobody proved anything about, which is worse than having none -
  it carries the authority of a green without the evidence of one.
* **The plan never executes.** Restoring is `git reset --hard` territory:
  it destroys uncommitted work, and the archive cannot know what is in the
  working tree. Godmode names the commit and hands over the command; a
  person runs it. `executed: False` is asserted, not assumed.
"""

from __future__ import annotations

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
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_rollback import (  # noqa: E402
    last_green,
    mark_green,
    rollback_plan,
)


def _git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git",) + arguments, cwd=project, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(arguments)}: {result.stderr}")
    return result.stdout.strip()


@contextmanager
def git_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        _git(project, "init", "-q")
        _git(project, "config", "user.email", "test@example.invalid")
        _git(project, "config", "user.name", "Test")
        _git(project, "config", "commit.gpgsign", "false")
        with mock.patch.dict(os.environ,
                             {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, archive


def _commit(project: Path, name: str, body: str) -> str:
    (project / name).write_text(body, encoding="utf-8")
    _git(project, "add", name)
    _git(project, "commit", "-q", "-m", f"touch {name}")
    return _git(project, "rev-parse", "HEAD")


class MarkingTests(unittest.TestCase):
    def test_a_failing_run_cannot_be_marked_green(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            with self.assertRaises(ArchiveError):
                mark_green(archive, project, command="pytest", exit_code=1)

    def test_a_passing_run_records_the_current_commit(self) -> None:
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="pytest", exit_code=0)
            green = last_green(archive, project)
            self.assertEqual(green["commit"], head)
            self.assertEqual(green["command"], "pytest")

    def test_the_newest_green_wins(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="first", exit_code=0)
            second = _commit(project, "api.py", "two\n")
            mark_green(archive, project, command="second", exit_code=0)
            self.assertEqual(last_green(archive, project)["commit"], second)

    def test_a_green_whose_commit_vanished_is_skipped(self) -> None:
        # A rewritten history must not leave a restore point aimed at an
        # object that no longer exists - restoring to it would fail, and
        # reporting it would be a promise the repository cannot keep.
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="real", exit_code=0)
            mark_green(archive, project, command="ghost", exit_code=0,
                       commit="0" * 40)
            self.assertEqual(last_green(archive, project)["commit"], head)


class PlanTests(unittest.TestCase):
    def test_the_plan_names_what_changed_since_green(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="pytest", exit_code=0)
            _commit(project, "api.py", "two\n")
            _commit(project, "extra.py", "new\n")
            plan = rollback_plan(archive, project)
            self.assertIn("api.py", plan["changed_files"])
            self.assertIn("extra.py", plan["changed_files"])

    def test_the_plan_never_executes_anything(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="pytest", exit_code=0)
            _commit(project, "api.py", "two\n")
            plan = rollback_plan(archive, project)
            self.assertFalse(plan["executed"])
            self.assertIn("git", plan["restore_command"])
            # The working tree is untouched: the file still holds the newer
            # content, so nothing was restored behind the caller's back.
            self.assertEqual(
                (project / "api.py").read_text(encoding="utf-8"), "two\n")

    def test_no_green_is_reported_rather_than_guessed(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            plan = rollback_plan(archive, project)
            self.assertIsNone(plan["green"])
            self.assertIn("no attested green", plan["note"])

    def test_already_at_green_reports_nothing_to_restore(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            mark_green(archive, project, command="pytest", exit_code=0)
            plan = rollback_plan(archive, project)
            self.assertEqual(plan["changed_files"], [])
            self.assertTrue(plan["at_green"])


if __name__ == "__main__":
    unittest.main()
