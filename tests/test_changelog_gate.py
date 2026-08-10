"""The gate that wants a fragment, when the fragment has already become an entry.

A fragment is a staging area. The artifact it exists to produce is a CHANGELOG
entry, and `changelog merge` consumes every fragment to write one. So a commit
that merges fragments and ships code in the same breath has changed code, has
recorded the note the gate is protecting, and carries no fragment - because it
spent them.

The gate read that as a code change with no note and refused it. It is right
about the fragments and wrong about the question: what it exists to guarantee is
that a change is written down, not that a particular staging file survives to be
counted.

Splitting the release into two commits avoids this, and the repository has
always done that by habit. Habit is not a check. A gate that only passes when
somebody remembers the customary commit order will refuse a correct release the
first time somebody does it in one.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_changelog import check_fragments  # noqa: E402


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments],
                   capture_output=True, check=False)


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "d@e.invalid")
        _git(self.root, "config", "user.name", "Dev")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- something\n",
            encoding="utf-8")
        (self.root / "code.py").write_text("x = 1\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "base")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _commit(self, message: str) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", message)

    def test_a_code_change_with_no_note_anywhere_is_still_refused(self) -> None:
        """The gate's whole purpose. Nothing here may weaken it."""
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        self._commit("change code")
        report = check_fragments(self.root, base="HEAD~1")
        self.assertFalse(report["satisfied"], report)
        self.assertEqual(report["verdict"], "missing-fragment")

    def test_a_code_change_with_a_fragment_passes(self) -> None:
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        fragments = self.root / "changelog.d"
        fragments.mkdir()
        (fragments / "thing.added.md").write_text("A thing.\n", encoding="utf-8")
        self._commit("change code with a fragment")
        self.assertTrue(check_fragments(self.root, base="HEAD~1")["satisfied"])

    def test_a_code_change_that_writes_the_entry_itself_passes(self) -> None:
        """The release commit: fragments spent, entry written, code shipped."""
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.2.0] - 2026-02-01\n\n### Added\n\n- the thing "
            "the fragments described\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n"
            "- something\n", encoding="utf-8")
        self._commit("release: 0.2.0")
        report = check_fragments(self.root, base="HEAD~1")
        self.assertTrue(report["satisfied"], report)
        self.assertEqual(report["verdict"], "satisfied")

    def test_touching_the_changelog_without_adding_an_entry_is_not_enough(self) -> None:
        """Fixing a typo in an old entry is not a note for today's code, and
        treating any CHANGELOG edit as satisfaction would turn the gate off."""
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- somethingg\n",
            encoding="utf-8")
        self._commit("typo")
        self.assertFalse(check_fragments(self.root, base="HEAD~1")["satisfied"])

    def test_the_report_says_which_of_the_two_satisfied_it(self) -> None:
        """A reader who sees `satisfied` with no fragments should not have to
        guess why the gate passed."""
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [0.2.0] - 2026-02-01\n\n### Added\n\n- an entry\n\n"
            "## [0.1.0] - 2026-01-01\n\n### Added\n\n- something\n", encoding="utf-8")
        self._commit("release: 0.2.0")
        self.assertEqual(check_fragments(self.root, base="HEAD~1")["satisfied_by"],
                         "changelog-entry")

    def test_a_fragment_is_still_named_as_the_reason_when_it_is_one(self) -> None:
        (self.root / "code.py").write_text("x = 2\n", encoding="utf-8")
        fragments = self.root / "changelog.d"
        fragments.mkdir()
        (fragments / "thing.added.md").write_text("A thing.\n", encoding="utf-8")
        self._commit("change code with a fragment")
        self.assertEqual(check_fragments(self.root, base="HEAD~1")["satisfied_by"],
                         "fragment")


if __name__ == "__main__":
    unittest.main()
