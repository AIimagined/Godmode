"""Guidance stays small and hard rules stay attested.

Both properties pass today, so both tests would pass vacuously if they only
checked the real tree. Each therefore has a case proving the predicate
discriminates: a file over budget is reported, and a HARD rule with no
verification method is reported. A check that has only ever seen a clean tree
is a check nobody has tested.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import guidance_budget as G  # noqa: E402


class TheRealTreeIsWithinBudget(unittest.TestCase):
    def test_guidance_is_within_its_ceilings(self) -> None:
        self.assertEqual(G.guidance_findings(), [])

    def test_every_hard_rule_carries_a_verification_method(self) -> None:
        self.assertEqual(G.attestation_findings(), [])


class TheBudgetPredicateDiscriminates(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, rel: str, lines: int) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(f"line {n}" for n in range(lines)) + "\n")

    def test_a_guidance_file_over_its_ceiling_is_reported(self) -> None:
        self._write("GODMODE.md", G.BUDGETS["GODMODE.md"][0] + 5)
        problems = G.guidance_findings(self.root)
        self.assertTrue(problems)
        self.assertIn("GODMODE.md", problems[0])

    def test_a_guidance_file_at_its_ceiling_is_not_reported(self) -> None:
        """Boundary: the ceiling is inclusive, so exactly-at passes."""
        self._write("GODMODE.md", G.BUDGETS["GODMODE.md"][0])
        self.assertEqual(G.guidance_findings(self.root), [])

    def test_an_oversized_skill_body_is_reported(self) -> None:
        self._write("GODMODE.md", 10)
        self._write("skills/example/SKILL.md", G.SKILL_BODY_BUDGET + 1)
        problems = G.guidance_findings(self.root)
        self.assertTrue(problems)
        self.assertIn("example", problems[0])

    def test_a_missing_budgeted_file_is_reported_rather_than_skipped(self) -> None:
        """An absent file is not a small one."""
        problems = G.guidance_findings(self.root)
        self.assertTrue(problems)
        self.assertIn("missing", problems[0])

    def test_the_message_says_what_to_do(self) -> None:
        self._write("GODMODE.md", G.BUDGETS["GODMODE.md"][0] + 5)
        self.assertIn("Split it", G.guidance_findings(self.root)[0])


class TheCeilingsRestOnAMeasurement(unittest.TestCase):
    def test_each_ceiling_is_above_what_was_measured(self) -> None:
        """A ceiling below its own measurement would fail on day one."""
        for name, (ceiling, measured) in G.BUDGETS.items():
            with self.subTest(file=name):
                self.assertGreater(ceiling, measured)

    def test_the_skill_ceiling_is_above_the_largest_measured_body(self) -> None:
        self.assertGreater(G.SKILL_BODY_BUDGET, G.SKILL_BODY_MEASURED_MAX)

    def test_the_recorded_measurement_still_resembles_the_tree(self) -> None:
        """If the measurement drifts far from reality the margin is a fiction.

        Loose on purpose - this should not fail for one added line - but it
        catches a ceiling whose stated basis has stopped being true.
        """
        actual = len((PLUGIN_ROOT / "GODMODE.md").read_text(encoding="utf-8").splitlines())
        recorded = G.BUDGETS["GODMODE.md"][1]
        self.assertLess(abs(actual - recorded), 20,
                        f"GODMODE.md is {actual} lines; the ceiling was set against {recorded}")


if __name__ == "__main__":
    unittest.main()
