"""The fix-loop wire: two failed outcomes on one subject stop the third try.

The operator's own convergence law: an analysis-and-fix that reverses on
the next iteration is a defect in the previous pass, and two reversals
mean stop analysing and go read. The calibration ledger already records
reversals - a scored claim resolved `failed` IS one - so the wire joins
them: when two failed resolutions share their subject matter, the next
verified-or-scored claim on that subject downgrades with both reversals
named, until the record shows the reading happened (an incident or
decision recorded after the second failure, cited on the new claim).
The economics trip wires carry the same family so the doctor names it.
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

from godmode_runtime.godmode_attest import (  # noqa: E402
    record_claim,
    resolve_claim,
)
from godmode_runtime.godmode_metrics import economics  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

SUBJECT = "the matrix verify jobs pass on the aliased runner"


def _failed_round(archive, project, text=SUBJECT):
    (project / "README.md").write_text("x", encoding="utf-8")
    claim = record_claim(archive, project, "S-test", text, "observed",
                        confidence=0.8)
    resolve_claim(archive, project, "S-test", claim["sequence"], "failed",
                  cites=["file:README.md"])
    return claim


class FixLoopWireTests(unittest.TestCase):
    def test_one_reversal_does_not_trip_the_wire(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _failed_round(archive, project)
            third = record_claim(archive, project, "S-test", SUBJECT,
                                 "observed", confidence=0.8)
            self.assertFalse(third["data"]["downgraded"])

    def test_two_reversals_stop_the_third_try(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = _failed_round(archive, project)
            second = _failed_round(archive, project)
            third = record_claim(archive, project, "S-test", SUBJECT,
                                 "observed", confidence=0.8)
            self.assertTrue(third["data"]["downgraded"])
            reason = third["data"]["reason"]
            self.assertIn(f"seq:{first['sequence']}", reason)
            self.assertIn(f"seq:{second['sequence']}", reason)
            self.assertIn("investigation", reason)

    def test_a_verified_claim_is_held_to_the_same_wire(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _failed_round(archive, project)
            _failed_round(archive, project)
            third = record_claim(archive, project, "S-test", SUBJECT,
                                 "verified", cites=["file:README.md"])
            self.assertTrue(third["data"]["downgraded"])
            self.assertIn("reversal", third["data"]["reason"])

    def test_citing_the_reading_clears_the_wire(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _failed_round(archive, project)
            _failed_round(archive, project)
            reading = archive.append(
                "incident", "aliased runner root cause read",
                {"detail": "class-swept every comparison site",
                 "failure_class": None, "turning_point": False})
            third = record_claim(archive, project, "S-test", SUBJECT,
                                 "observed", confidence=0.8,
                                 cites=[f"seq:{reading['sequence']}"])
            self.assertFalse(third["data"]["downgraded"])

    def test_an_unrelated_subject_is_untouched(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _failed_round(archive, project)
            _failed_round(archive, project)
            other = record_claim(archive, project, "S-test",
                                 "the exporter handles empty archives",
                                 "observed", confidence=0.8)
            self.assertFalse(other["data"]["downgraded"])

    def test_the_doctor_names_the_family(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _failed_round(archive, project)
            _failed_round(archive, project)
            wires = economics(archive, project)["trip_wires"]
            loop_wires = [w for w in wires if w["code"] == "fix-loop"]
            self.assertEqual(len(loop_wires), 1)
            self.assertIn("2 reversals", loop_wires[0]["detail"])


if __name__ == "__main__":
    unittest.main()
