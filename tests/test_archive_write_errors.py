"""A write the archive cannot make is a refusal with a remedy, not a traceback.

Ninth field report 2026-09-05 (Codex): `session open` raised PermissionError
under a sandbox that cannot write outside the workspace. Field walk the same
day: on Windows a non-git project under a deep state home raised
FileNotFoundError from mkstemp because the temporary file name pushed the
path past MAX_PATH. Both surfaced as raw Python tracebacks.

D-7 (2026-09-14, host e2e under an operator-chosen `TEMP`): that walk's fix
shortened the TEMPORARY name (`test_the_temporary_name_stays_short` below)
but left `_atomic_json`'s own destination - the final `os.replace(temporary,
path)`, and every later read of `path` - exactly as long as before. An
operator's `GODMODE_STATE_HOME`/`TEMP` can be short enough for the archive
root itself to resolve and still leave no room for an event file's own
fixed-width name; the earlier fix never covered that call, so it still
raised `FileNotFoundError` as a bare traceback, never the `ArchiveError`
this file's other cases already expect.
"""
from __future__ import annotations

import os
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


class SyscallPathTests(unittest.TestCase):
    """`_syscall_path` is the one thing standing between a long destination
    and a bare `FileNotFoundError` (D-7) - it must change nothing except
    the exact case it exists for."""

    def test_a_short_path_is_returned_unchanged(self) -> None:
        short = Path(tempfile.gettempdir()) / "x.json"
        self.assertEqual(chronicle._syscall_path(short), str(short))

    def test_an_already_prefixed_path_is_left_alone(self) -> None:
        prefixed = "\\\\?\\C:\\already\\prefixed.json"
        self.assertEqual(chronicle._syscall_path(prefixed), prefixed)

    def test_a_unc_path_is_left_alone(self) -> None:
        # `\\?\` alone does not extend a UNC share (that needs the distinct
        # `\\?\UNC\` form) - prefixing it plain would misinterpret the path
        # rather than extend it, so this leaves UNC paths untouched.
        unc = "\\\\server\\share\\" + ("d" * 260) + "\\record.json"
        self.assertEqual(chronicle._syscall_path(unc), unc)

    @unittest.skipUnless(os.name == "nt", "MAX_PATH is a Windows-only limit")
    def test_a_long_windows_path_is_extended_length_prefixed(self) -> None:
        long_path = Path("C:\\" + "d" * 250 + "\\record.json")
        self.assertEqual(chronicle._syscall_path(long_path),
                         "\\\\?\\" + str(long_path))

    def test_non_windows_never_gets_the_prefix_even_when_long(self) -> None:
        long_path = Path("/tmp/" + "d" * 250 + "/record.json")
        with mock.patch.object(chronicle.os, "name", "posix"):
            self.assertEqual(chronicle._syscall_path(long_path), str(long_path))


@unittest.skipUnless(os.name == "nt", "MAX_PATH is a Windows-only limit")
class LongDestinationWriteAndReadTests(unittest.TestCase):
    """D-7: the exact failure a live host-e2e run hit under an operator's
    own `GODMODE_STATE_HOME`/`TEMP` - a record file whose own name is
    fixed-width (`godmode-events/<12-digit seq>-<32 hex>.godmode.json`)
    pushes an otherwise-short archive root past Windows' 260-character
    MAX_PATH. Without `_syscall_path` covering `_atomic_json`'s final
    `os.replace` and `Chronicle._read_json`'s own read, this raised a bare
    `FileNotFoundError` - never the softened `ArchiveError` the rest of
    this file already expects, and never a value to read back.
    """

    def _deep_target(self, temporary: str) -> Path:
        """A path whose PARENT stays under MAX_PATH (so `mkdir`/`mkstemp`
        succeed exactly as they did before this fix) while parent +
        filename together clear it - the precise, narrower gap
        `_atomic_json`'s final `os.replace` (and every later read) still
        had after the temp-name shortening. Pads adaptively off the live
        `temporary` dir's own length rather than a fixed segment count, so
        this reproduces on a short default TEMP and a long one alike.
        """
        filename = "0" * 12 + "-" + "a" * 32 + ".godmode.json"  # fixed-width, 58 chars
        parent = Path(temporary)
        while len(str(parent)) < 240:
            remaining = 240 - len(str(parent)) - 1  # room for the separator
            segment = "p" * max(1, min(remaining, 200))
            parent = parent / segment
        return parent / filename

    def test_a_destination_past_max_path_still_writes(self) -> None:
        # ignore_cleanup_errors: a plain, unprefixed `shutil.rmtree` (what
        # this context manager's own `__exit__` uses) still cannot remove
        # a file past MAX_PATH afterward - a separate, already-known
        # stdlib limitation this fixture deliberately runs into on its way
        # out; it is not the thing under test here.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            target = self._deep_target(temporary)
            self.assertGreater(len(str(target)), 260, "fixture must exceed MAX_PATH")
            chronicle._atomic_json(target, {"proof": "d7"})
            # A plain, unprefixed exists() check is expected to miss it -
            # that asymmetry (silently unreadable via the ordinary API) is
            # exactly why `TimeoutSimulationScenarioTests` saw an empty
            # event list instead of a crash; `Chronicle._read_json` below
            # is what production code actually reads through.
            self.assertEqual(
                chronicle.Chronicle._read_json(target), {"proof": "d7"})

    def test_prefix_identity_reads_a_past_max_path_record(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            target = self._deep_target(temporary)
            chronicle._atomic_json(target, {"proof": "d7"})
            identity = chronicle.Chronicle._prefix_identity([target])
            self.assertIsNotNone(identity, "a real record must yield a real identity")


if __name__ == "__main__":
    unittest.main()
