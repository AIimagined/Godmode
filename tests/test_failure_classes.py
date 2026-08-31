"""Failure classes and the turning point.

One closed table names the ways work fails; a free-text class cannot be
trended. An incident may carry a class (off-list refused with the list
rendered) and may mark the turning point - the first failure the run
never recovered from - which requires evidence, because the turning
point is a causal claim, not a mood. The third-strike wire names the
class when the record carries one, so "same error three times" arrives
as "misread-tool-output three times", which names the fix layer.
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

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_metrics import economics  # noqa: E402
from godmode_runtime.godmode_mistakes import (  # noqa: E402
    FAILURE_CLASSES,
    record_incident,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class ClassTableTests(unittest.TestCase):
    def test_the_table_is_closed_and_nonempty(self) -> None:
        self.assertGreaterEqual(len(FAILURE_CLASSES), 8)
        self.assertIn("misread-tool-output", FAILURE_CLASSES)

    def test_an_off_list_class_is_refused_with_the_list(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as caught:
                record_incident(archive, "export broke", "boom",
                                failure_class="vibes")
            self.assertIn("misread-tool-output", str(caught.exception))

    def test_an_on_list_class_is_stored(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom",
                                     failure_class="misread-tool-output")
            self.assertEqual(record["data"]["failure_class"],
                             "misread-tool-output")

    def test_a_classless_incident_still_records(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom")
            self.assertIsNone(record["data"]["failure_class"])


class TurningPointTests(unittest.TestCase):
    def test_a_turning_point_requires_evidence(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_incident(archive, "export broke", "boom",
                                turning_point=True)

    def test_a_cited_turning_point_is_stored(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom",
                                     turning_point=True,
                                     cites=["seq:1"])
            self.assertTrue(record["data"]["turning_point"])


class WireClassTests(unittest.TestCase):
    def test_the_third_strike_wire_names_the_class(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for _ in range(3):
                record_incident(archive, "export broke", "boom",
                                failure_class="misread-tool-output")
            wires = economics(archive, project)["trip_wires"]
            self.assertEqual(len(wires), 1)
            self.assertIn("misread-tool-output", wires[0]["detail"])


if __name__ == "__main__":
    unittest.main()
