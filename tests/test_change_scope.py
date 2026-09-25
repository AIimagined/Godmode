"""The shared change-scope helper (R10, 2026-09-23): added-line parsing from
a real `git diff`, and the pure `in_scope`/`pre_existing`/`blocks` rules
every check under `quality/checks/` shares.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import _change_scope as scope  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


class ParseUnifiedDiff(unittest.TestCase):
    """`_parse_unified_added_lines` reads a raw unified diff with no git
    involved - the fast, deterministic path most of these tests use."""

    def test_a_single_added_line_is_reported_at_its_own_number(self) -> None:
        diff = (
            "diff --git a/x.py b/x.py\n"
            "index 111..222 100644\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -1,2 +1,3 @@\n"
            " one\n"
            "+two\n"
            " three\n"
        )
        added = scope._parse_unified_added_lines(diff)
        self.assertEqual(added, {"x.py": {2}})

    def test_a_removed_line_adds_nothing(self) -> None:
        diff = (
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -1,2 +1,1 @@\n"
            " one\n"
            "-two\n"
        )
        self.assertEqual(scope._parse_unified_added_lines(diff), {})

    def test_a_new_file_reports_every_line_added(self) -> None:
        diff = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+one\n"
            "+two\n"
        )
        self.assertEqual(scope._parse_unified_added_lines(diff), {"new.py": {1, 2}})

    def test_a_deleted_file_reports_nothing_for_it(self) -> None:
        diff = (
            "diff --git a/gone.py b/gone.py\n"
            "deleted file mode 100644\n"
            "--- a/gone.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-one\n"
            "-two\n"
        )
        self.assertEqual(scope._parse_unified_added_lines(diff), {})

    def test_two_files_are_tracked_independently(self) -> None:
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,0 +2,1 @@\n"
            "+added-in-a\n"
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -5,0 +6,1 @@\n"
            "+added-in-b\n"
        )
        self.assertEqual(scope._parse_unified_added_lines(diff),
                         {"a.py": {2}, "b.py": {6}})


class InScopeAndPreExisting(unittest.TestCase):
    def setUp(self) -> None:
        self.added = {"touched.py": {3, 4}}

    def test_all_filter_is_always_in_scope(self) -> None:
        self.assertTrue(scope.in_scope("untouched.py", 1, "all", self.added))

    def test_added_filter_requires_the_exact_line(self) -> None:
        self.assertTrue(scope.in_scope("touched.py", 3, "added", self.added))
        self.assertFalse(scope.in_scope("touched.py", 5, "added", self.added))
        self.assertFalse(scope.in_scope("untouched.py", 3, "added", self.added))

    def test_file_filter_accepts_any_line_in_a_touched_file(self) -> None:
        self.assertTrue(scope.in_scope("touched.py", 99, "file", self.added))
        self.assertFalse(scope.in_scope("untouched.py", 1, "file", self.added))

    def test_a_lineless_finding_falls_back_to_the_file_check_even_under_added(self) -> None:
        """A whole-file verdict (no line of its own) has no finer location
        to ask "was this line touched" - `added` degrades to `file` for it."""
        self.assertTrue(scope.in_scope("touched.py", None, "added", self.added))
        self.assertFalse(scope.in_scope("untouched.py", None, "added", self.added))

    def test_pre_existing_is_the_line_level_complement_of_added(self) -> None:
        self.assertFalse(scope.pre_existing("touched.py", 3, self.added))
        self.assertTrue(scope.pre_existing("touched.py", 5, self.added))
        self.assertTrue(scope.pre_existing("untouched.py", 1, self.added))


class Blocks(unittest.TestCase):
    def test_harm_blocks_at_every_fail_level(self) -> None:
        for level in scope.LEVELS:
            self.assertTrue(scope.blocks("harm", level))

    def test_warning_blocks_only_at_warning(self) -> None:
        self.assertTrue(scope.blocks("warning", "warning"))
        self.assertFalse(scope.blocks("warning", "error"))
        self.assertFalse(scope.blocks("warning", "harm"))

    def test_information_never_blocks(self) -> None:
        for level in scope.LEVELS:
            self.assertFalse(scope.blocks("information", level))


class ResolveAgainstARealRepo(unittest.TestCase):
    """`resolve`/`added_lines` against a real, small git repository - the
    fallback-to-all path when no comparable ref exists, and the ordinary
    path once a base branch does."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")

    def _write(self, name: str, body: str) -> None:
        (self.repo / name).write_text(body, encoding="utf-8")

    def test_no_comparable_ref_falls_back_to_all(self) -> None:
        self._write("x.py", "one\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "first")
        filt, added = scope.resolve(self.repo, "added", base="no-such-ref")
        self.assertEqual(filt, "all")
        self.assertEqual(added, {})

    def test_a_line_added_since_an_explicit_base_is_reported(self) -> None:
        self._write("x.py", "one\ntwo\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "base")
        _git(self.repo, "branch", "base-branch")
        self._write("x.py", "one\ntwo\nthree\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "add a line")

        filt, added = scope.resolve(self.repo, "added", base="base-branch")
        self.assertEqual(filt, "added")
        self.assertEqual(added, {"x.py": {3}})

    def test_all_filter_never_touches_git(self) -> None:
        # No commit at all in this repo - a git diff would fail outright.
        # `all` must not even try.
        filt, added = scope.resolve(self.repo, "all")
        self.assertEqual((filt, added), ("all", {}))


if __name__ == "__main__":
    unittest.main()
