"""A push that changes only prose and images runs the modules that read
them, not every module whose source mentions a changed file's name."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT / "scripts" / "dev") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "dev"))

import affected_tests  # noqa: E402


class DocsOnlySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modules = affected_tests.module_map()

    def test_a_readme_and_image_change_selects_the_docs_set_only(self) -> None:
        changed = {PLUGIN_ROOT / "README.md", PLUGIN_ROOT / "assets" / "godmode-hero.png",
                   PLUGIN_ROOT / "changelog.d" / "note.changed.md"}
        self.assertTrue(affected_tests.docs_only(changed))
        selected = affected_tests.select(changed, self.modules)
        self.assertEqual(selected, sorted(affected_tests.DOCS_SET))
        self.assertIn("tests.test_readme_commands", selected)
        self.assertLess(len(selected), 15)

    def test_a_skill_document_is_not_docs_only(self) -> None:
        changed = {PLUGIN_ROOT / "skills" / "godmode" / "SKILL.md"}
        self.assertFalse(affected_tests.docs_only(changed))

    def test_one_code_file_beside_the_docs_takes_the_ordinary_path(self) -> None:
        changed = {PLUGIN_ROOT / "README.md",
                   PLUGIN_ROOT / "scripts" / "godmode_runtime" / "godmode_roi.py"}
        self.assertFalse(affected_tests.docs_only(changed))
        selected = affected_tests.select(changed, self.modules)
        self.assertIn("tests.test_roi_releases", selected)

    def test_every_docs_module_exists(self) -> None:
        for name in affected_tests.DOCS_SET:
            self.assertIn(name.split(".", 1)[1], self.modules, name)

    def test_nothing_changed_is_not_docs_only(self) -> None:
        self.assertFalse(affected_tests.docs_only(set()))


if __name__ == "__main__":
    unittest.main()
