"""A git failure is not an untracked file: the freshness stamp retries once.

`run_git` returns None when git fails (a 5 s timeout on a machine just
woken from sleep, at the 0.3.18 gate's round 13) and "" for a tracked
path with no log entry. Falling straight to mtime on None made the
checkout time the file's freshness and flipped the ranking snapshot for
one gate run out of four, with nothing in the tree changed.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_corpus  # noqa: E402


class FreshnessRetryTests(unittest.TestCase):
    def test_a_transient_git_failure_retries_before_the_mtime_fallback(self) -> None:
        answers = iter([None, "1700000000"])
        calls: list[tuple[str, ...]] = []

        def flaky_git(project: Path, *arguments: str) -> str | None:
            calls.append(arguments)
            return next(answers)

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "doc.md").write_text("x", encoding="utf-8")
            with mock.patch.object(godmode_corpus, "run_git", flaky_git):
                stamp = godmode_corpus._freshness_stamp(project, "doc.md", True)
        self.assertEqual(stamp, 1700000000 * 1_000_000_000)
        self.assertEqual(len(calls), 2)

    def test_an_untracked_path_still_falls_back_to_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "doc.md").write_text("x", encoding="utf-8")
            expected = (project / "doc.md").stat().st_mtime_ns
            with mock.patch.object(godmode_corpus, "run_git", lambda *a: ""):
                stamp = godmode_corpus._freshness_stamp(project, "doc.md", True)
        self.assertEqual(stamp, expected)
        self.assertGreater(stamp, 0)


if __name__ == "__main__":
    unittest.main()
