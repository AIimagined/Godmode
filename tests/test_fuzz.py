"""A fuzz harness is only worth its runtime if it can fail.

The planted-defect test matters more than the clean sweep: a harness that
reports "no findings" without ever being able to find one is the same false
green this project exists to refuse, so one test breaks a classifier on purpose
and requires the harness to notice.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_fuzz  # noqa: E402
from godmode_runtime.godmode_fuzz import FAMILIES, fuzz  # noqa: E402


class DeterminismTests(unittest.TestCase):
    def test_the_same_seed_reproduces_the_same_run(self) -> None:
        first = fuzz(seed=7, iterations=25)
        second = fuzz(seed=7, iterations=25)
        self.assertEqual(first["families"], second["families"])
        self.assertEqual(first["seed"], 7)

    def test_a_different_seed_explores_different_inputs(self) -> None:
        first = fuzz(seed=1, iterations=25)
        second = fuzz(seed=2, iterations=25)
        self.assertNotEqual(first["corpus_digest"], second["corpus_digest"])

    def test_every_family_runs_and_reports_its_case_count(self) -> None:
        report = fuzz(seed=3, iterations=25)
        self.assertEqual(sorted(report["families"]), sorted(FAMILIES))
        for name, family in report["families"].items():
            self.assertGreater(family["cases"], 0, name)


class PlantedDefectTests(unittest.TestCase):
    def test_a_classifier_that_permits_a_mutation_is_caught(self) -> None:
        """The harness must fail when the runtime is wrong, or it proves nothing."""
        def permissive(operation: str, extra_protected=()) -> dict:
            return {"protected": False, "category": "read-only-inspection",
                    "tier": "R0", "impact": [], "second_confirmation_required": False}

        with mock.patch.object(godmode_fuzz, "classify_action", permissive):
            report = fuzz(seed=11, iterations=40, families=("command",))
        findings = report["families"]["command"]["findings"]
        self.assertTrue(findings, "a permissive classifier produced no finding")
        self.assertGreaterEqual(report["critical"], 1)
        self.assertEqual(report["verdict"], "findings")
        # Reproducible: the finding names the seed and case that produced it.
        self.assertEqual(findings[0]["seed"], 11)
        self.assertIsInstance(findings[0]["case"], int)

    def test_a_path_check_that_accepts_an_escape_is_critical(self) -> None:
        from godmode_runtime import godmode_egress

        with mock.patch.object(godmode_fuzz, "_contained", lambda project, path: Path(path)):
            report = fuzz(seed=5, iterations=30, families=("path",))
        self.assertGreaterEqual(report["critical"], 1)
        self.assertTrue(godmode_egress)  # module import kept meaningful for the reader


class RealRuntimeTests(unittest.TestCase):
    def test_the_runtime_fails_closed_under_fuzzing(self) -> None:
        """Observed reality, asserted by name so a regression changes this loudly."""
        report = fuzz(seed=0, iterations=60)
        self.assertEqual(report["critical"], 0, report["families"])
        self.assertEqual(report["verdict"], "fail-closed", report["families"])

    def test_config_readers_degrade_instead_of_raising(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": raw}, clear=False):
                report = fuzz(seed=4, iterations=30, families=("config",))
        self.assertEqual(report["families"]["config"]["findings"], [])


if __name__ == "__main__":
    unittest.main()
