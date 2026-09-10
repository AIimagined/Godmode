"""Every `action` subject a writer emits, and every one a reader matches,
is a member of `ACTION_SUBJECTS`. The record kinds were pinned; the
action subjects were inline literals a reader matched by string, so a
typo on either side was a rule that silently never fired (absorbed from a
threat-detection harness's KnownActions census, 2026-09-10).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_constants import ACTION_SUBJECTS  # noqa: E402

_WRITER = re.compile(r'append\(\s*"action",\s*"([a-z0-9_-]+)"')
_READER = re.compile(r'select\(\s*kind="action",\s*subject="([a-z0-9_-]+)"')
_SCANNED = (PLUGIN_ROOT / "hooks", PLUGIN_ROOT / "scripts" / "godmode_runtime")


def _literals(pattern: re.Pattern[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for base in _SCANNED:
        for path in sorted(base.rglob("*.py")):
            for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace")):
                found.setdefault(match.group(1), set()).add(path.name)
    return found


class ActionSubjectCensusTests(unittest.TestCase):
    def test_every_written_subject_is_registered(self) -> None:
        unknown = {k: sorted(v) for k, v in _literals(_WRITER).items() if k not in ACTION_SUBJECTS}
        self.assertEqual(unknown, {}, f"add to ACTION_SUBJECTS: {unknown}")

    def test_every_read_subject_is_registered(self) -> None:
        unknown = {k: sorted(v) for k, v in _literals(_READER).items() if k not in ACTION_SUBJECTS}
        self.assertEqual(unknown, {}, f"a reader matches a subject no writer emits: {unknown}")

    def test_every_registered_subject_has_a_writer(self) -> None:
        written = set(_literals(_WRITER))
        self.assertEqual(sorted(ACTION_SUBJECTS - written), [], "registered but never written")

    def test_the_writer_scan_sees_the_hook(self) -> None:
        self.assertIn("tripwire-nudge", _literals(_WRITER))


if __name__ == "__main__":
    unittest.main()
