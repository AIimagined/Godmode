"""Push preflight: disposable worktree, two-bucket triage, honest skips.

The stage runs BEFORE the password prompt and feeds it, never bypasses
it: a banned-term scan over the tracked files (the private list lives
outside the repo; absent means the check reports itself skipped, the
same contract the privacy test already has) and an optional suite
command. Findings come back in two buckets - mechanical (a scrub can
fix them; named with the remedy) and judgment (a person decides). The
worktree is disposable on every exit path, and a dirty tree is refused
before anything runs: preflight validates a state, and a dirty tree is
not a state anyone can push.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_preflight import push_preflight  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


class PreflightTests(unittest.TestCase):
    def test_a_dirty_tree_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
            with self.assertRaises(ArchiveError):
                push_preflight(repo)

    def test_missing_term_list_reports_itself_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            report = push_preflight(repo)
            self.assertIn("banned-term scan", report["skipped"][0])
            self.assertEqual(report["mechanical"], [])
            self.assertEqual(report["judgment"], [])

    def test_a_term_hit_is_a_mechanical_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            terms = Path(tmp) / "terms.txt"
            terms.write_text("secretproject\n", encoding="utf-8")
            (repo / "code.py").write_text("# secretproject lives here\n",
                                          encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "leak")
            os.environ["GODMODE_COVERAGE_TERMS"] = str(terms)
            try:
                report = push_preflight(repo)
            finally:
                del os.environ["GODMODE_COVERAGE_TERMS"]
            self.assertEqual(len(report["mechanical"]), 1)
            self.assertIn("code.py", report["mechanical"][0]["detail"])
            # The term itself never appears in the finding - same contract
            # as the privacy test: red output must not be the second leak.
            self.assertNotIn("secretproject", str(report))

    def test_a_failing_suite_is_a_judgment_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            report = push_preflight(
                repo, suite=[sys.executable, "-c", "raise SystemExit(3)"])
            self.assertEqual(len(report["judgment"]), 1)
            self.assertIn("exit 3", report["judgment"][0]["detail"])

    def test_the_worktree_is_gone_on_every_exit_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(Path(tmp))
            push_preflight(repo,
                           suite=[sys.executable, "-c", "raise SystemExit(1)"])
            listing = subprocess.run(
                ["git", "worktree", "list"], cwd=repo,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(len(listing.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
