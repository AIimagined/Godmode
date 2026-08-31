"""Recurrence advisories: the archive warns before the third strike lands.

The longitudinal record already knows which causes came back. When a new
task's terms overlap a repeated block or a repeated incident, the
precheck carries the pattern forward - before the action, not in the
post-mortem - naming the record evidence. At most once per session per
pattern: a receipt is recorded on first delivery and consulted after,
because a nudge that nags is a nudge that gets ignored.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_precheck import recurrence_nudges  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _incident(archive, subject, n):
    for i in range(n):
        archive.append("incident", subject, {"detail": f"occurrence {i}"})


class RecurrenceNudgeTests(unittest.TestCase):
    def test_a_repeated_incident_matching_the_task_is_surfaced(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _incident(archive, "exporter timeout on large files", 2)
            nudges = recurrence_nudges(
                archive, "tune the exporter timeout handling", [], "S-1")
            self.assertEqual(len(nudges), 1)
            self.assertIn("exporter timeout", nudges[0]["pattern"])
            self.assertEqual(nudges[0]["occurrences"], 2)

    def test_a_single_occurrence_is_not_a_pattern(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _incident(archive, "exporter timeout on large files", 1)
            self.assertEqual(
                recurrence_nudges(archive, "tune the exporter timeout", [], "S-1"),
                [])

    def test_an_unrelated_task_hears_nothing(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _incident(archive, "exporter timeout on large files", 3)
            self.assertEqual(
                recurrence_nudges(archive, "rename the login button", [], "S-1"),
                [])

    def test_the_same_session_is_nudged_once(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _incident(archive, "exporter timeout on large files", 2)
            first = recurrence_nudges(
                archive, "tune the exporter timeout", [], "S-1")
            second = recurrence_nudges(
                archive, "tune the exporter timeout", [], "S-1")
            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])

    def test_a_new_session_is_nudged_again(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _incident(archive, "exporter timeout on large files", 2)
            recurrence_nudges(archive, "tune the exporter timeout", [], "S-1")
            fresh = recurrence_nudges(
                archive, "tune the exporter timeout", [], "S-2")
            self.assertEqual(len(fresh), 1)


if __name__ == "__main__":
    unittest.main()
