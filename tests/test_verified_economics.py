"""Verified-result economics: debt, completion rate, rule growth, trip wires.

The real metric is not how much ran but how much finished verified.
`economics` reads only existing records: evidence debt is the calibration
ledger's unresolved scored claims read as a liability; the completion
rate is verified-tier items over all terminal items; rule growth is the
direction of the lesson/invariant ratchet; and the recurrence wire names
any failure subject seen three times, pointing at the investigation
workflow. Everything advisory - wires cite, they never block.
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

from godmode_runtime.godmode_attest import record_claim  # noqa: E402
from godmode_runtime.godmode_metrics import economics  # noqa: E402
from godmode_runtime.godmode_status import record_item  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class EconomicsTests(unittest.TestCase):
    def test_empty_archive_reads_honestly_empty(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            block = economics(archive, project)
            self.assertEqual(block["evidence_debt"]["count"], 0)
            self.assertIsNone(block["verified_completion_rate"])
            self.assertEqual(block["trip_wires"], [])

    def test_evidence_debt_matches_the_ledger(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "S-test", "scored, never resolved",
                         "observed", confidence=0.7)
            block = economics(archive, project)
            self.assertEqual(block["evidence_debt"]["count"], 1)

    def test_completion_rate_counts_shown_over_terminal(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "a", "shown", "verified", evidence=["cmd:true"])
            record_item(archive, "b", "said", "verified")
            block = economics(archive, project)
            self.assertAlmostEqual(block["verified_completion_rate"], 0.5)

    def test_recurrence_wire_names_a_third_strike(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for i in range(3):
                archive.append("incident", "timeout in exporter",
                               {"detail": f"strike {i}"})
            wires = economics(archive, project)["trip_wires"]
            self.assertEqual(len(wires), 1)
            self.assertIn("timeout in exporter", wires[0]["detail"])
            self.assertIn("investigation", wires[0]["detail"])

    def test_two_strikes_stay_silent(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for i in range(2):
                archive.append("incident", "timeout in exporter",
                               {"detail": f"strike {i}"})
            self.assertEqual(economics(archive, project)["trip_wires"], [])


if __name__ == "__main__":
    unittest.main()
