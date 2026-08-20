"""B5-B: citations that stopped meaning what they meant when they were written.

A claim graded `verified` because `file:src/api.py` resolved stays graded
`verified` for the life of the archive. The grade was true about the file
as it stood that day; nothing re-checks it when the file changes, so a
later session reads full confidence about a state that no longer exists.

Two ways a citation comes loose, and both are pinned here:

* **The file moved on.** A commit touching the cited path, landing after
  the record was written, means the evidence read now is not the evidence
  graded then. Detected from `recorded_at` against git history, so it
  needs no new field and works on every record already in the archive.
* **The commit vanished.** A rebase, a squash or a history scrub leaves a
  `commit:` citation pointing at an object no longer reachable. This is
  not hypothetical for this project: a history scrub is planned, and it
  will orphan every commit citation the archive holds unless they are
  re-anchored first.

Staleness is deliberately NOT a downgrade. A stale citation means "this
needs looking at again", which is a different fact from "the evidence
never supported it" - collapsing the two would either hide real
downgrades or cry wolf on every file that was legitimately edited later.
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
from godmode_runtime.godmode_reanchor import (  # noqa: E402
    reanchor_report,
    stale_records,
    unreachable_commit_citations,
)


def _git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git",) + arguments, cwd=project, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(arguments)}: {result.stderr}")
    return result.stdout.strip()


@contextmanager
def git_project():
    """A real repository, because the whole feature reads real git history.

    Mocking git here would test the mock: the behaviour under test is
    exactly how a commit relates to a timestamp and whether an object is
    still reachable, which is git's semantics, not ours.
    """
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        _git(project, "init", "-q")
        _git(project, "config", "user.email", "test@example.invalid")
        _git(project, "config", "user.name", "Test")
        _git(project, "config", "commit.gpgsign", "false")
        with mock.patch.dict(os.environ,
                             {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, archive


# Commit times are set explicitly rather than taken from the clock. Git
# stamps commits in whole seconds while a chronicle record carries
# microseconds, so a test that commits and records back to back lands both
# inside one second and asserts on an ordering neither timestamp can
# express. Naming the dates tests the real rule - did this file change
# after that record - instead of racing the clock.
BEFORE = "2020-01-01T00:00:00+00:00"
AFTER = "2030-01-01T00:00:00+00:00"


def _commit(project: Path, name: str, body: str, when: str = BEFORE) -> str:
    (project / name).write_text(body, encoding="utf-8")
    _git(project, "add", name)
    environment = dict(os.environ,
                       GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    result = subprocess.run(
        ("git", "commit", "-q", "-m", f"touch {name}"),
        cwd=project, capture_output=True, text=True, env=environment)
    if result.returncode != 0:
        raise AssertionError(f"git commit: {result.stderr}")
    return _git(project, "rev-parse", "HEAD")


class FileCitationTests(unittest.TestCase):
    def test_a_file_committed_after_the_record_is_stale(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            archive.append("claim", "api is covered", {"text": "api is covered"},
                           evidence=["file:api.py"])
            _commit(project, "api.py", "after\n", when=AFTER)
            stale = stale_records(archive, project)
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0]["citation"], "file:api.py")

    def test_a_file_untouched_since_the_record_is_not_stale(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            archive.append("claim", "api is covered", {"text": "api is covered"},
                           evidence=["file:api.py"])
            _commit(project, "other.py", "unrelated\n")
            self.assertEqual(stale_records(archive, project), [])

    def test_an_uncited_record_is_never_stale(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            archive.append("claim", "no citations", {"text": "no citations"})
            _commit(project, "api.py", "after\n", when=AFTER)
            self.assertEqual(stale_records(archive, project), [])


class CommitCitationTests(unittest.TestCase):
    def test_a_reachable_commit_citation_is_fine(self) -> None:
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "before\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{head}"])
            self.assertEqual(unreachable_commit_citations(archive, project), [])

    def test_a_commit_that_no_longer_exists_is_reported(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            # A plausible but absent object - exactly the shape a history
            # scrub leaves behind once the original commit is rewritten.
            ghost = "0" * 40
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{ghost}"])
            findings = unreachable_commit_citations(archive, project)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["commit"], ghost)


class ReportTests(unittest.TestCase):
    def test_the_report_separates_stale_from_unreachable(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            archive.append("claim", "api is covered", {"text": "api is covered"},
                           evidence=["file:api.py"])
            _commit(project, "api.py", "after\n", when=AFTER)
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=["commit:" + "0" * 40])
            report = reanchor_report(archive, project)
            self.assertEqual(len(report["stale"]), 1)
            self.assertEqual(len(report["unreachable"]), 1)
            # Staleness is a review prompt, never a silent regrade.
            self.assertFalse(report["regraded"])

    def test_a_clean_project_reports_nothing_to_reanchor(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "before\n")
            archive.append("claim", "api is covered", {"text": "api is covered"},
                           evidence=["file:api.py"])
            report = reanchor_report(archive, project)
            self.assertEqual(report["stale"], [])
            self.assertEqual(report["unreachable"], [])

    def test_a_non_git_project_degrades_instead_of_failing(self) -> None:
        # Godmode runs outside git too; the honest answer there is "cannot
        # tell", never a crash and never a false all-clear.
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(os.environ,
                                 {"GODMODE_STATE_HOME": str(base / "s")},
                                 clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                archive.append("claim", "x", {"text": "x"},
                               evidence=["file:api.py"])
                report = reanchor_report(archive, project)
                self.assertFalse(report["git"])


if __name__ == "__main__":
    unittest.main()
