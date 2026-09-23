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

from godmode_runtime import godmode_constants as _constants_module  # noqa: E402
from godmode_runtime.godmode_constants import ACTION_SUBJECTS  # noqa: E402

# Fix round 1 (Task 3 review, S2): the original two patterns only ever
# matched a quoted literal in the subject position, so a writer that
# passes an imported constant instead - `append("action", DONEBAR_TURN_
# SUBJECT, ...)` - was invisible to this whole census, exactly the gap
# that let an unregistered subject through review. The second alternative
# in each pattern also accepts a bare ALL_CAPS identifier there; `_literals`
# resolves it against `godmode_constants`'s own module namespace (the one
# place a subject constant can be defined) rather than trusting the name
# alone, so an unrelated all-caps local never counts as a match.
_WRITER = re.compile(r'append\(\s*"action",\s*(?:"([a-z0-9_-]+)"|([A-Z][A-Z0-9_]*))')
_READER = re.compile(r'select\(\s*kind="action",\s*subject=(?:"([a-z0-9_-]+)"|([A-Z][A-Z0-9_]*))')
_SCANNED = (PLUGIN_ROOT / "hooks", PLUGIN_ROOT / "scripts" / "godmode_runtime")

_CONST_SUBJECTS = {
    name: value for name, value in vars(_constants_module).items()
    if isinstance(value, str) and name.isupper()
}


def _literals(pattern: re.Pattern[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for base in _SCANNED:
        for path in sorted(base.rglob("*.py")):
            for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace")):
                literal, const_name = match.group(1), match.group(2)
                subject = literal if literal is not None else _CONST_SUBJECTS.get(const_name or "")
                if not subject:
                    continue
                found.setdefault(subject, set()).add(path.name)
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
