"""A path that escapes the project after symlink resolution is refused."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_paths import contain, contained_or_refuse  # noqa: E402


def _can_symlink(base: Path) -> bool:
    try:
        os.symlink(base, base / "probe-link", target_is_directory=True); (base / "probe-link").unlink(); return True
    except (OSError, NotImplementedError):
        return False


class ContainmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp()); self.addCleanup(__import__("shutil").rmtree, self.base, ignore_errors=True)
        self.project = self.base / "project"; self.project.mkdir()
        self.outside = self.base / "outside"; self.outside.mkdir()

    def test_inside_is_contained(self) -> None:
        (self.project / "a.txt").write_text("x", encoding="utf-8")
        self.assertIsNotNone(contain("a.txt", [self.project]))

    def test_dotdot_escape_is_none(self) -> None:
        self.assertIsNone(contain("../outside/secret.txt", [self.project]))

    def test_symlink_out_is_refused(self) -> None:
        if not _can_symlink(self.base):
            self.skipTest("symlinks need privilege here")
        os.symlink(self.outside, self.project / "link", target_is_directory=True)
        with self.assertRaises(ArchiveError):
            contained_or_refuse("link/secret.txt", [self.project], "manifest path")

    def test_second_root_counts(self) -> None:
        (self.outside / "state.json").write_text("{}", encoding="utf-8")
        self.assertIsNotNone(contain(str(self.outside / "state.json"), [self.project, self.outside]))


if __name__ == "__main__":
    unittest.main()
