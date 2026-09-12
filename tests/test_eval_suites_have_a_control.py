"""No skill suite measures firing without also measuring not-firing.

A routing suite made only of prompts the skill should answer cannot tell a
skill that routes well from one that fires on everything. The near-negative is
the control: a prompt close enough to be tempting that the skill must decline.

The planned task here was a passive arm - run the task with nothing acting, and
take that score as the floor every other arm must clear. That idea came from a
simulation where the environment moves on its own. It does not transfer to a
routing grader, which scores on whether a tool was invoked: with nothing
acting, the score is zero by construction and the arm carries no information.
Recorded as not applicable rather than built as a number that always reads the
same.

What the idea was reaching for already exists here, and this pins it: every
suite carries at least one near-negative, so a suite added later cannot ship
with positives alone.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_evals as E  # noqa: E402

SUITES = E.load_suites(PLUGIN_ROOT)


class EverySuiteHasBothArms(unittest.TestCase):
    def test_there_are_suites_to_check(self) -> None:
        """Guard against a loader change turning this file into a no-op."""
        self.assertGreaterEqual(len(SUITES), 5, sorted(SUITES))

    def test_every_suite_has_at_least_one_positive(self) -> None:
        for name, suite in SUITES.items():
            with self.subTest(suite=name):
                self.assertTrue(suite.get("positive"), f"{name} has no positive case")

    def test_every_suite_has_at_least_one_near_negative(self) -> None:
        """The control. Without it a suite cannot distinguish routing from
        firing on everything."""
        for name, suite in SUITES.items():
            with self.subTest(suite=name):
                self.assertTrue(suite.get("near_negative"),
                                f"{name} has no near-negative; it cannot measure "
                                f"a skill that fires on everything")

    def test_every_suite_carries_behaviour_assertions(self) -> None:
        for name, suite in SUITES.items():
            with self.subTest(suite=name):
                self.assertTrue(suite.get("behavior_assertions"),
                                f"{name} asserts no behaviour beyond routing")


class TheArmsAreDistinct(unittest.TestCase):
    def test_no_prompt_appears_as_both_a_positive_and_a_negative(self) -> None:
        """The same text on both sides makes the suite unfalsifiable."""
        for name, suite in SUITES.items():
            positives = {str(p).strip().lower() for p in suite.get("positive", [])}
            negatives = {str(n).strip().lower() for n in suite.get("near_negative", [])}
            with self.subTest(suite=name):
                self.assertEqual(positives & negatives, set())


if __name__ == "__main__":
    unittest.main()
