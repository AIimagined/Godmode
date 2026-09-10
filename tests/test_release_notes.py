"""`godmode release-notes build|check`: a note is derived from the
changelog and held to its shape."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from godmode_runtime.godmode_release_notes import build_notes, check_notes, notes_path  # noqa: E402

CHANGELOG = """# Changelog

## [Unreleased]

## [1.2.0] - 2026-09-10

### Added

- Perimeter checks. `godmode perimeter add` declares a boot command; `tests/test_perimeter.py` pins it.
- The scope gate blocks a done claim while asks are open.

### Fixed

- A bare `godmode status` prints the survey.

## [1.1.0] - 2026-09-01

### Added

- Older thing.
"""


class ReleaseNotesTests(unittest.TestCase):
    def _project(self, changelog: str = CHANGELOG) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="godmode-notes-")
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return root

    def test_build_derives_the_note_from_the_changelog_section(self) -> None:
        root = self._project()
        report = build_notes(root, "1.2.0")
        self.assertTrue(report["written"], report)
        text = notes_path(root, "1.2.0").read_text(encoding="utf-8")
        self.assertIn("# Godmode v1.2.0", text)
        self.assertIn("## Added", text)
        self.assertIn("## Fixed", text)
        self.assertIn("## Verifying", text)
        self.assertIn("python -m unittest tests.test_perimeter", text)
        self.assertNotIn("Older thing", text)
        self.assertEqual(check_notes(root, "1.2.0")["ok"], True)

    def test_build_refuses_without_a_section_or_over_an_existing_note(self) -> None:
        root = self._project()
        self.assertFalse(build_notes(root, "9.9.9")["written"])
        build_notes(root, "1.2.0")
        self.assertFalse(build_notes(root, "1.2.0")["written"])
        self.assertTrue(build_notes(root, "1.2.0", force=True)["written"])

    def test_check_names_a_missing_note_narration_and_an_uncovered_entry(self) -> None:
        root = self._project()
        missing = check_notes(root, "1.2.0")
        self.assertFalse(missing["ok"])
        self.assertIn("note-missing", [f["check"] for f in missing["findings"]])
        path = notes_path(root, "1.2.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Godmode v1.2.0\n\nThe batch release. After three cuts we pushed it.\n\n"
                        "## Added\n\n- Perimeter checks.\n\n## Verifying\n\n- run it\n", encoding="utf-8")
        report = check_notes(root, "1.2.0")
        codes = [f["check"] for f in report["findings"]]
        self.assertIn("release-note-narration", codes)
        self.assertIn("entry-uncovered", codes)  # the scope gate and the bare status are not in the note
        path.write_text("# Godmode v1.2.0\n\n## Added\n\n- Perimeter checks.\n\n## Changed\n\n## Verifying\n\n- run it\n",
                        encoding="utf-8")
        report = check_notes(root, "1.2.0")
        self.assertIn("empty-section", [f["check"] for f in report["findings"]])
        self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
