"""scripts/dev/affected_tests.py: the pure selection function.

Builds a tiny fake module tree in a tempdir and checks `select()` picks up
a direct importer, a one-level-through importer, leaves an unrelated test
alone, and always includes the fixed smoke set.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = PLUGIN_ROOT / "scripts" / "dev"
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))

import affected_tests as at  # noqa: E402


class SelectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.tests_dir = self.root / "tests"
        self.tests_dir.mkdir()
        self.scripts_dir = self.root / "scripts"
        self.scripts_dir.mkdir()

        self.leaf = self.scripts_dir / "mod_leaf.py"
        self.leaf.write_text("VALUE = 1\n", encoding="utf-8")
        self.mid = self.scripts_dir / "mod_mid.py"
        self.mid.write_text("import mod_leaf\n", encoding="utf-8")
        self.direct = self.tests_dir / "test_direct.py"
        self.direct.write_text("import mod_leaf\n", encoding="utf-8")
        self.through = self.tests_dir / "test_through.py"
        self.through.write_text("import mod_mid\n", encoding="utf-8")
        self.unrelated = self.tests_dir / "test_unrelated.py"
        self.unrelated.write_text("import os\n", encoding="utf-8")

        self.modules = {
            "mod_leaf": self.leaf, "mod_mid": self.mid,
            "test_direct": self.direct, "test_through": self.through,
            "test_unrelated": self.unrelated,
        }

    def test_direct_and_one_level_through_selected_unrelated_is_not(self):
        with mock.patch.object(at, "TESTS_DIR", self.tests_dir):
            result = at.select({self.leaf}, self.modules)
        self.assertIn("tests.test_direct", result)
        self.assertIn("tests.test_through", result)
        self.assertNotIn("tests.test_unrelated", result)

    def test_smoke_set_always_present(self):
        with mock.patch.object(at, "TESTS_DIR", self.tests_dir):
            result = at.select(set(), self.modules)
        for name in at.SMOKE_SET:
            self.assertIn(name, result)


if __name__ == "__main__":
    unittest.main()
