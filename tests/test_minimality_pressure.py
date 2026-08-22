"""C-04: a pressure gate on layer-adding work.

`godmode minimality` has always reported how much duplicated authority,
how many speculative seams and how many orphans a tree carries. Reporting
a number nobody compares against anything is how a number gets ignored:
this session added seven modules and the seam count moved, and the only
reason anyone noticed was that someone happened to run the report twice.

So the counts get a baseline and the growth has to be answered for. The
shape is the swallow ratchet's, which is already proven here - a recorded
ceiling per section, and a comparison that speaks when the ceiling is
exceeded.

Where it deliberately differs from that ratchet: swallowed errors should
only ever go down, so its baseline never rises. Minimality counts rise
legitimately whenever a feature lands, so a never-rising baseline would
be red forever after the first one, and a gate that is always red is a
gate people learn to skip. Growth is therefore accepted rather than
forbidden - but accepting it costs a recorded reason, which is the point:
the cost is stating why, not being blocked.
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
from godmode_runtime.godmode_minimality import (  # noqa: E402
    accept_growth,
    pressure_report,
    write_pressure_baseline,
)
from test_godmode_runtime import isolated_project  # noqa: E402

FLAT = {"duplicate-authority": 10, "speculative-seams": 5}
GREW = {"duplicate-authority": 14, "speculative-seams": 5}


class BaselineTests(unittest.TestCase):
    def test_no_baseline_reports_uninitialized_rather_than_growth(self) -> None:
        # An absent baseline is not a clean bill of health, and reporting
        # zero growth against nothing would read as one.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            report = pressure_report(project, FLAT, archive=archive)
            self.assertFalse(report["baseline_exists"])
            self.assertEqual(report["verdict"], "no-baseline")

    def test_counts_at_the_baseline_are_steady(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            write_pressure_baseline(project, FLAT)
            report = pressure_report(project, FLAT, archive=archive)
            self.assertEqual(report["verdict"], "steady")
            self.assertEqual(report["grew"], [])

    def test_a_fall_is_recorded_and_never_reported_as_growth(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            write_pressure_baseline(project, GREW)
            report = pressure_report(project, FLAT, archive=archive)
            self.assertEqual(report["grew"], [])
            self.assertIn("duplicate-authority", report["fell"])


class GrowthTests(unittest.TestCase):
    def test_unaccepted_growth_is_reported(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            write_pressure_baseline(project, FLAT)
            report = pressure_report(project, GREW, archive=archive)
            self.assertEqual(report["verdict"], "pressure-grew")
            grew = {row["section"]: row for row in report["grew"]}
            self.assertEqual(grew["duplicate-authority"]["delta"], 4)

    def test_accepting_growth_needs_a_reason(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                accept_growth(archive, "duplicate-authority", reason="  ")

    def test_accepted_growth_stops_being_reported(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            write_pressure_baseline(project, FLAT)
            accept_growth(archive, "duplicate-authority",
                          reason="four host manifests each declare their own key set")
            report = pressure_report(project, GREW, archive=archive)
            self.assertEqual(report["grew"], [])
            self.assertEqual(report["verdict"], "steady")
            self.assertIn("duplicate-authority", report["accepted"])

    def test_accepting_one_section_does_not_excuse_another(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            write_pressure_baseline(project, FLAT)
            accept_growth(archive, "duplicate-authority", reason="stated")
            report = pressure_report(
                project, {"duplicate-authority": 14, "speculative-seams": 9},
                archive=archive)
            self.assertEqual([row["section"] for row in report["grew"]],
                             ["speculative-seams"])


if __name__ == "__main__":
    unittest.main()
