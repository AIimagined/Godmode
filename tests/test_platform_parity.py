"""Which platforms this release is actually measured on, and where it is not.

The product claims Windows and macOS support. This session can run Windows and
cannot run macOS, so the honest report is a matrix with one measured cell and
one that says `unmeasured` - not a pass. An absent instrument is graded
distinctly from a negative result (R8), and "we have no mac" is an absent
instrument.

`unmeasured` deliberately does not fail the build. A check that goes red
because a developer lacks a second machine gets disabled within a week, and a
disabled check measures nothing at all. A recorded *failing*
run does fail the build; an absent one cannot, because absence is not a defect
in the code.

A hazard scan for platform-locked path literals was written alongside this and
removed: on this repository it produced thirteen findings and all thirteen were
correct code. See the check module for the detail.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import platform_parity as P  # noqa: E402


class TheMatrix(unittest.TestCase):
    def test_a_platform_with_no_recorded_run_is_unmeasured_not_failing(self) -> None:
        matrix = P.matrix(runs={})
        for platform in P.SUPPORTED:
            self.assertEqual(matrix[platform], "unmeasured", platform)

    def test_a_recorded_run_reads_as_measured(self) -> None:
        matrix = P.matrix(runs={"Darwin": {"date": "2026-09-12", "tests": 31, "result": "pass"}})
        self.assertEqual(matrix["Darwin"], "measured")
        self.assertEqual(matrix["Windows"], "unmeasured")

    def test_a_recorded_failure_is_not_reported_as_measured_pass(self) -> None:
        matrix = P.matrix(runs={"Darwin": {"date": "2026-09-12", "tests": 31, "result": "fail"}})
        self.assertEqual(matrix["Darwin"], "failing")

    def test_the_current_platform_is_one_we_claim_to_support(self) -> None:
        self.assertIn(P.current_platform(), P.SUPPORTED)


class TheRecordedSuite(unittest.TestCase):
    def test_the_portability_modules_all_exist(self) -> None:
        """A recorded run means these modules. A renamed module would make the
        matrix report a measurement of something that no longer runs."""
        for module in P.PORTABILITY_MODULES:
            rel = Path(module.replace(".", "/") + ".py")
            self.assertTrue((PLUGIN_ROOT / rel).exists(), f"missing {rel}")


if __name__ == "__main__":
    unittest.main()
