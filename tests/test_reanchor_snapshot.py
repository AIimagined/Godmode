"""Survive the scrub: fingerprint cited commits before history is rewritten.

`reanchor_report` says which citations came loose. That is enough after a
rewrite only if something recorded what the old sha POINTED AT before it
vanished - otherwise "commit abc123 is unreachable" is the end of the
story, and the evidence behind a verdict is gone with no way back.

A scrub rewrites shas but keeps what the commit *is*: the tree it
produced, its subject line, and when its author wrote it. That triple is
the durable identity, so it is what gets snapshotted before the rewrite
and matched against after.

Ordering is the whole point and is pinned here: snapshot BEFORE, remap
AFTER. A snapshot taken after the rewrite records the new sha and proves
nothing about the old one.
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
    commit_fingerprint,
    remap_commit_citations,
    snapshot_commit_citations,
    unreachable_commit_citations,
)


def _git(project: Path, *arguments: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ("git",) + arguments, cwd=project, capture_output=True, text=True,
        env=env if env is None else dict(os.environ, **env))
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
    _git(project, "commit", "-q", "-m", f"touch {name}",
         env={"GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
              "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00"})
    return _git(project, "rev-parse", "HEAD")


def _rewrite_history(project: Path) -> str:
    """Simulate a scrub: same tree, same subject, same author date, new sha.

    An amend with a different committer date is the smallest faithful
    stand-in - it changes exactly what a scrub changes (the sha) and
    preserves exactly what a scrub preserves.
    """
    _git(project, "commit", "-q", "--amend", "--no-edit",
         env={"GIT_COMMITTER_DATE": "2021-06-06T06:06:06+00:00"})
    return _git(project, "rev-parse", "HEAD")


class FingerprintTests(unittest.TestCase):
    def test_a_fingerprint_survives_a_rewrite(self) -> None:
        with git_project() as (project, _archive):
            old = _commit(project, "api.py", "one\n")
            before = commit_fingerprint(project, old)
            new = _rewrite_history(project)
            self.assertNotEqual(old, new)
            self.assertEqual(before, commit_fingerprint(project, new))

    def test_an_absent_commit_has_no_fingerprint(self) -> None:
        with git_project() as (project, _archive):
            _commit(project, "api.py", "one\n")
            self.assertIsNone(commit_fingerprint(project, "0" * 40))


class SnapshotTests(unittest.TestCase):
    def test_cited_commits_are_snapshotted(self) -> None:
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{head}"])
            report = snapshot_commit_citations(archive, project)
            self.assertEqual(report["snapshotted"], 1)

    def test_snapshotting_twice_does_not_duplicate(self) -> None:
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{head}"])
            snapshot_commit_citations(archive, project)
            second = snapshot_commit_citations(archive, project)
            self.assertEqual(second["snapshotted"], 0)
            self.assertEqual(second["already"], 1)

    def test_every_record_kind_is_covered_not_just_asserting_ones(self) -> None:
        """Preservation is total; staleness is scoped. Different questions.

        `DEFAULT_KINDS` exists for staleness, where only records that
        assert something can decay. A rewrite orphans a `commit:` citation
        wherever it sits, so snapshotting must cover every kind. On this
        project all 34 commit citations live on `checkpoint`, `sprint`,
        `lesson` and `decision` records - none on the asserting kinds - so
        a scoped snapshot would have recorded nothing at all.
        """
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            archive.append("checkpoint", "a checkpoint",
                           {"head": head, "status": "green"},
                           evidence=[f"commit:{head}"])
            report = snapshot_commit_citations(archive, project)
            self.assertEqual(report["snapshotted"], 1)

    def test_a_sha_with_trailing_prose_is_still_read(self) -> None:
        """`commit:<sha> some words` is a real shape in this archive.

        Citations are hand-written as often as generated. Sequence 83 here
        carries `commit:c5fa933 CI green`; reading the whole remainder as a
        sha reported a reachable commit as unrecoverable, which is a false
        alarm in the one report that must not cry wolf before a scrub.
        """
        with git_project() as (project, archive):
            head = _commit(project, "api.py", "one\n")
            archive.append("decision", "shipped", {"note": "shipped"},
                           evidence=[f"commit:{head[:7]} CI green"])
            report = snapshot_commit_citations(archive, project)
            self.assertEqual(report["snapshotted"], 1)
            self.assertEqual(report["unreachable"], [])

    def test_a_commit_already_gone_cannot_be_snapshotted(self) -> None:
        with git_project() as (project, archive):
            _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=["commit:" + "0" * 40])
            report = snapshot_commit_citations(archive, project)
            self.assertEqual(report["snapshotted"], 0)
            self.assertEqual(len(report["unreachable"]), 1)


class RemapTests(unittest.TestCase):
    def test_a_rewritten_commit_is_found_by_its_fingerprint(self) -> None:
        with git_project() as (project, archive):
            old = _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{old}"])
            snapshot_commit_citations(archive, project)
            new = _rewrite_history(project)
            # The citation is now dangling; the snapshot is what saves it.
            self.assertEqual(len(unreachable_commit_citations(archive, project)), 1)
            report = remap_commit_citations(archive, project)
            self.assertEqual(len(report["remapped"]), 1)
            self.assertEqual(report["remapped"][0]["old"], old)
            self.assertEqual(report["remapped"][0]["new"], new)

    def test_without_a_snapshot_a_lost_commit_stays_lost(self) -> None:
        # The honest outcome, and the reason ordering matters: nothing
        # recorded what the sha meant, so nothing can recover it.
        with git_project() as (project, archive):
            old = _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{old}"])
            _rewrite_history(project)
            report = remap_commit_citations(archive, project)
            self.assertEqual(report["remapped"], [])
            self.assertEqual(len(report["unresolved"]), 1)

    def test_remapping_is_recorded_so_it_survives_the_session(self) -> None:
        with git_project() as (project, archive):
            old = _commit(project, "api.py", "one\n")
            archive.append("claim", "shipped", {"text": "shipped"},
                           evidence=[f"commit:{old}"])
            snapshot_commit_citations(archive, project)
            _rewrite_history(project)
            remap_commit_citations(archive, project)
            # Re-reading finds the mapping already recorded, not redone.
            again = remap_commit_citations(archive, project)
            self.assertEqual(again["remapped"], [])
            self.assertEqual(len(again["already_remapped"]), 1)


if __name__ == "__main__":
    unittest.main()
