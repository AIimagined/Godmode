"""Law hygiene: origin, contradiction, and mechanical supersession.

A law with no recorded origin cannot be re-validated when the world
changes. Two active laws sharing their subject matter with opposite
polarity are a disagreement waiting for a release to expose it. And a
law whose guard a pin now enforces mechanically is a retirement
candidate - prose duplicating a sensor is debt, not protection. The scan
names candidates and record ids; the operator retires, never the scan.
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

from godmode_runtime.godmode_law import hygiene  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _lesson(archive, subject, guard, why="observed failure", status="active"):
    archive.append("lesson", subject, {
        "value": why, "generalized_guard": guard, "status": status,
    })


class HygieneTests(unittest.TestCase):
    def test_a_clean_ledger_reports_no_findings(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "quote-paths", "quote every path passed to the shell")
            report = hygiene(archive)
            self.assertEqual(report["findings"], [])

    def test_a_law_without_an_origin_is_named(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "mystery-rule", "always do the thing", why="")
            findings = hygiene(archive)["findings"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["check"], "no-recorded-origin")
            self.assertIn("mystery-rule", findings[0]["detail"])

    def test_opposite_polarity_twins_are_flagged_as_a_pair(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "parallel-yes",
                    "run the test suite chunks in parallel batches for speed")
            _lesson(archive, "parallel-no",
                    "never run the test suite chunks in parallel batches")
            findings = [f for f in hygiene(archive)["findings"]
                        if f["check"] == "contradictory-pair"]
            self.assertEqual(len(findings), 1)
            self.assertIn("parallel-yes", findings[0]["detail"])
            self.assertIn("parallel-no", findings[0]["detail"])

    def test_a_pin_covered_law_is_a_retirement_candidate(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "redirect-guard",
                    "temp file redirects must target the scratch directory")
            archive.append("checklist", "redirect-scratch", {
                "value": "temp file redirects target the scratch directory, "
                         "enforced by the gate corpus",
            })
            findings = [f for f in hygiene(archive)["findings"]
                        if f["check"] == "sensor-superseded"]
            self.assertEqual(len(findings), 1)
            self.assertIn("redirect-guard", findings[0]["detail"])

    def test_retired_laws_are_out_of_scope(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _lesson(archive, "old-rule", "always do the thing", why="",
                    status="retired")
            self.assertEqual(hygiene(archive)["findings"], [])


if __name__ == "__main__":
    unittest.main()
