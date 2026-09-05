"""A write the archive cannot make is a refusal with a remedy, not a traceback.

Ninth field report 2026-09-05 (Codex): `session open` raised PermissionError
under a sandbox that cannot write outside the workspace. Field walk the same
day: on Windows a non-git project under a deep state home raised
FileNotFoundError from mkstemp because the temporary file name pushed the
path past MAX_PATH. Both surfaced as raw Python tracebacks.
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

from godmode_runtime import godmode_chronicle as chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


class AtomicWriteErrorTests(unittest.TestCase):
    def test_an_unwritable_destination_is_an_archive_error_naming_the_remedy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            blocker = Path(temporary) / "blocker"
            blocker.write_text("a file where a directory must go", encoding="utf-8")
            target = blocker / "record.json"
            with self.assertRaises(ArchiveError) as caught:
                chronicle._atomic_json(target, {"x": 1})
        message = str(caught.exception)
        self.assertIn(str(target.parent), message)
        self.assertIn("GODMODE_STATE_HOME", message)

    def test_a_permission_error_reads_the_same_way(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "record.json"
            with mock.patch.object(chronicle.tempfile, "mkstemp", side_effect=PermissionError(13, "denied")):
                with self.assertRaises(ArchiveError) as caught:
                    chronicle._atomic_json(target, {"x": 1})
        self.assertIn("denied", str(caught.exception))
        self.assertIn("GODMODE_STATE_HOME", str(caught.exception))

    def test_the_temporary_name_stays_short(self) -> None:
        """The record file name is 60 characters; a temp name built from it
        plus a random suffix crossed MAX_PATH under a deep state home."""
        seen: dict[str, str] = {}
        real = chronicle.tempfile.mkstemp

        def spy(**kwargs):
            seen.update({k: str(v) for k, v in kwargs.items()})
            return real(**kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / ("0" * 12 + "-" + "a" * 32 + ".godmode.json")
            with mock.patch.object(chronicle.tempfile, "mkstemp", side_effect=spy):
                chronicle._atomic_json(target, {"x": 1})
        self.assertLessEqual(len(seen.get("prefix", "")) + len(seen.get("suffix", "")), 12, seen)


if __name__ == "__main__":
    unittest.main()
