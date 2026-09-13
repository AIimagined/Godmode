"""The false-green rate reports how much of its population it actually saw.

The rate itself was never wrong. Its denominator is verified claims that were
later resolved, and the reasoning holds: only a resolved claim can be shown
wrong. The defect was what the number looked like next to nothing else.

Measured on this project's own archive: `false_greens: 0, rate: 0.0` over
`verified_resolved: 1`, with three hundred verified claims never resolved -
including three that were demonstrably false greens, recorded as an incident
the same day. A rate of zero over one trial is not a low rate. It is an
unmeasured one wearing a clean bill of health.

No threshold is introduced, because a threshold is a policy nobody agreed and
the first argument about where it sits kills the check. The population is
simply reported beside the rate, and a reader who sees one trial against three
hundred unresolved claims needs no rule to know what the zero is worth.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import false_green_rate  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive = Chronicle(resolve_anchor(Path(self._tmp.name)))

    def claim(self, grade: str = "verified") -> int:
        record = self.archive.append("claim", f"claim {grade}", {"grade": grade})
        return int(record["sequence"])

    def resolve(self, target: int, outcome: str) -> None:
        self.archive.append("claim", f"resolve {target}",
                            {"resolves": target, "outcome": outcome})


class ThePopulationIsReported(Base):
    def test_unresolved_verified_claims_are_counted(self) -> None:
        for _ in range(5):
            self.claim()
        report = false_green_rate(self.archive)
        self.assertEqual(report["verified_unresolved"], 5)

    def test_a_resolved_claim_leaves_the_unresolved_count(self) -> None:
        first = self.claim()
        self.claim()
        self.resolve(first, "held")
        report = false_green_rate(self.archive)
        self.assertEqual(report["verified_resolved"], 1)
        self.assertEqual(report["verified_unresolved"], 1)

    def test_coverage_is_the_share_of_the_population_actually_tested(self) -> None:
        first = self.claim()
        for _ in range(3):
            self.claim()
        self.resolve(first, "held")
        report = false_green_rate(self.archive)
        self.assertEqual(report["coverage"], 0.25)

    def test_the_shape_that_misled_reads_honestly_now(self) -> None:
        """One trial, many untested: the zero must not stand alone."""
        first = self.claim()
        for _ in range(99):
            self.claim()
        self.resolve(first, "held")
        report = false_green_rate(self.archive)
        self.assertEqual(report["rate"], 0.0)
        self.assertEqual(report["verified_unresolved"], 99)
        self.assertLess(report["coverage"], 0.02)


class TheRateItselfIsUnchanged(Base):
    def test_a_failed_resolution_is_a_false_green(self) -> None:
        first = self.claim()
        self.resolve(first, "failed")
        report = false_green_rate(self.archive)
        self.assertEqual(report["false_greens"], 1)
        self.assertEqual(report["rate"], 1.0)

    def test_a_held_resolution_is_not(self) -> None:
        first = self.claim()
        self.resolve(first, "held")
        self.assertEqual(false_green_rate(self.archive)["false_greens"], 0)

    def test_an_unverified_claim_is_outside_the_population(self) -> None:
        """Only a claim graded verified can be a false green."""
        first = self.claim(grade="hypothesis")
        self.resolve(first, "failed")
        report = false_green_rate(self.archive)
        self.assertEqual(report["verified_resolved"], 0)
        self.assertEqual(report["verified_unresolved"], 0)


class EmptyArchives(Base):
    def test_no_claims_reports_no_rate_and_no_coverage(self) -> None:
        report = false_green_rate(self.archive)
        self.assertIsNone(report["rate"])
        self.assertIsNone(report["coverage"])
        self.assertEqual(report["verified_unresolved"], 0)


if __name__ == "__main__":
    unittest.main()
