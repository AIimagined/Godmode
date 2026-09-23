"""The preflight leaves no `.godmode-preflight-*` scratch behind - but
only ever touches its OWN, and only once it is no longer LIVE.

Field observation: three stale scratch dirs sat beside the repo while
the run reported `cleanup: confirmed` - the run cleaned its own dir and
never looked at its siblings. The sweep runs before a preflight and
removes every sibling that this repo owns and that is not still live;
a sibling repository's worktree, or a concurrent run's half-built one,
is skipped instead of swept.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_preflight import (  # noqa: E402
    STALE_SCRATCH_SECONDS,
    push_preflight,
    sweep_stale_scratch,
)

OLD_ENOUGH = STALE_SCRATCH_SECONDS + 300


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _age(path: Path, seconds: float = OLD_ENOUGH) -> None:
    """Push `path`'s mtime (and its `head` child's, if any) back so it
    reads as stale to the liveness check, mirroring an abandoned run
    rather than one just started."""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))
    head = path / "head"
    if head.exists():
        os.utime(head, (stamp, stamp))


class ScratchSweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.parent, ignore_errors=True)
        self.repo = self.parent / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root")

    def test_stale_siblings_removed_live_kept(self) -> None:
        stale = self.parent / ".godmode-preflight-old"
        (stale / "head").mkdir(parents=True)
        _age(stale)
        live = self.parent / ".godmode-preflight-live"
        (live / "head").mkdir(parents=True)

        removed, unswept, skipped = sweep_stale_scratch(self.repo, keep=live)

        self.assertEqual([p.name for p in removed], [".godmode-preflight-old"])
        self.assertEqual(unswept, [])
        self.assertEqual(skipped, [])
        self.assertFalse(stale.exists())
        self.assertTrue(live.exists())

    def test_registered_worktree_is_pruned_not_deleted_underneath(self) -> None:
        wt = self.parent / ".godmode-preflight-wt" / "head"
        _git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        _age(wt.parent)
        removed, unswept, skipped = sweep_stale_scratch(self.repo)
        listing = subprocess.run(["git", "worktree", "list"], cwd=self.repo,
                                 capture_output=True, text=True).stdout
        self.assertNotIn("preflight-wt", listing)
        self.assertFalse(wt.exists())
        self.assertEqual(unswept, [])
        self.assertEqual(skipped, [])
        self.assertEqual([p.name for p in removed], [".godmode-preflight-wt"])

    def test_a_plain_file_sibling_is_reported_unswept_not_removed(self) -> None:
        # `shutil.rmtree(path, ignore_errors=True)` on a plain file silently
        # does nothing - the earlier version appended it to `removed`
        # anyway, so the report claimed a sweep that never happened. A
        # candidate still on disk after the attempt goes in `unswept`.
        stray = self.parent / ".godmode-preflight-stray"
        stray.write_text("not a directory\n", encoding="utf-8")
        _age(stray)

        removed, unswept, skipped = sweep_stale_scratch(self.repo)

        self.assertEqual(removed, [])
        self.assertEqual([p.name for p in unswept], [".godmode-preflight-stray"])
        self.assertEqual(skipped, [])
        self.assertTrue(stray.exists())

    def test_push_preflight_sweeps_a_stale_sibling_and_reports_it(self) -> None:
        # Wiring check: deleting the sweep call (or the result-dict key)
        # from `push_preflight` must fail this test even though the
        # sweep function itself is fully covered above.
        stale = self.parent / ".godmode-preflight-old"
        (stale / "head").mkdir(parents=True)
        _age(stale)

        report = push_preflight(self.repo)

        self.assertFalse(stale.exists())
        self.assertIn(".godmode-preflight-old", report["swept_stale_scratch"])

    def test_foreign_repos_worktree_is_skipped_not_swept(self) -> None:
        # A SECOND, unrelated repository parks its own preflight worktree
        # beside the first repo's parent (the layout the field observation
        # describes: several repos sharing a checkouts directory). Sweeping
        # `self.repo` must never touch it, no matter its age.
        other = self.parent / "other-repo"
        other.mkdir()
        _git(other, "init", "-q")
        _git(other, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
             "--allow-empty", "-m", "root")
        foreign = self.parent / ".godmode-preflight-foreign" / "head"
        _git(other, "worktree", "add", "-q", "--detach", str(foreign))
        _age(foreign.parent)

        removed, unswept, skipped = sweep_stale_scratch(self.repo)

        self.assertEqual(removed, [])
        self.assertEqual(unswept, [])
        self.assertEqual([p.name for p in skipped], [".godmode-preflight-foreign"])
        self.assertTrue(foreign.exists())

    def test_young_candidate_is_skipped_even_if_owned(self) -> None:
        # This repo's own worktree, just created - a concurrent run's
        # scratch mid-build. It must never be swept out from under it.
        wt = self.parent / ".godmode-preflight-young" / "head"
        _git(self.repo, "worktree", "add", "-q", "--detach", str(wt))

        removed, unswept, skipped = sweep_stale_scratch(self.repo)

        self.assertEqual(removed, [])
        self.assertEqual(unswept, [])
        self.assertEqual([p.name for p in skipped], [".godmode-preflight-young"])
        self.assertTrue(wt.exists())

    def test_old_owned_candidate_is_removed(self) -> None:
        wt = self.parent / ".godmode-preflight-owned-old" / "head"
        _git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        _age(wt.parent)

        removed, unswept, skipped = sweep_stale_scratch(self.repo)

        self.assertEqual([p.name for p in removed], [".godmode-preflight-owned-old"])
        self.assertEqual(unswept, [])
        self.assertEqual(skipped, [])
        self.assertFalse(wt.parent.exists())


if __name__ == "__main__":
    unittest.main()
