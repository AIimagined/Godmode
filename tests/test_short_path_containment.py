"""Windows 8.3 short names must not defeat containment or pin lookup.

Field-observed on CI (2026-08-31): the runner's temp directory came back
in short form (RUNNER~1), normcase/normpath left it unexpanded, and files
inside the project read as outside the working tree - absorption called
an in-tree write "outside", and a pinned path stopped matching, turning
a deny into an allow. The same mechanism is an evasion vector on any
Windows: a protected path spelled via its short name would slip the
match. Canonicalization now expands short names (Windows only) before
comparing.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import _contained, _pin_key  # noqa: E402


def _short_form(path: str) -> str | None:
    """The 8.3 spelling of an existing path, or None where unavailable
    (non-Windows, or a volume with 8.3 generation disabled)."""
    if os.name != "nt":
        return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 260) == 0:
        return None
    short = buffer.value
    return short if short and short.lower() != path.lower() else None


class ShortPathTests(unittest.TestCase):
    def setUp(self) -> None:
        # A name long enough to force an 8.3 alias on volumes that keep them.
        self._tmp = tempfile.TemporaryDirectory(prefix="godmode-longname-root-")
        self.root = Path(self._tmp.name) / "a-project-directory-with-a-long-name"
        self.root.mkdir()
        (self.root / "guard_module.py").write_text("x = 1\n", encoding="utf-8")
        self.short_root = _short_form(str(self.root))
        if self.short_root is None:
            self.skipTest("no 8.3 short name available on this volume")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_short_spelled_file_is_still_contained(self) -> None:
        short_file = self.short_root + os.sep + "guard_module.py"
        self.assertTrue(_contained(short_file, self.root))

    def test_a_short_spelled_root_still_contains_long_files(self) -> None:
        long_file = str(self.root / "guard_module.py")
        self.assertTrue(_contained(long_file, Path(self.short_root)))

    def test_pin_keys_agree_across_spellings(self) -> None:
        long_key = _pin_key(str(self.root / "guard_module.py"), self.root)
        short_key = _pin_key(self.short_root + os.sep + "guard_module.py",
                             self.root)
        self.assertEqual(long_key, "guard_module.py")
        self.assertEqual(short_key, long_key)


if __name__ == "__main__":
    unittest.main()
