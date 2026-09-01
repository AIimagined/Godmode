"""The loop surface: a declared contract, ticked iterations, honest ends.

Godmode does not run loops - the agent drives; godmode records the
contract and holds the line on three things the parked family always
wanted a home for: a readiness audit at declaration (no cap or no stop
condition refuses to declare), graduated stall escalation (two empty
ticks demand a direction change, four demand the operator), and the
terminated-vs-truncated split at close (budget exhaustion may never
impersonate completion: closing `finished` at the cap needs evidence).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_loop import (  # noqa: E402
    close_loop,
    declare_loop,
    tick_loop,
)


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-loop-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield archive


class ReadinessTests(unittest.TestCase):
    def test_a_contract_without_a_cap_refuses_to_declare(self) -> None:
        with _archive() as archive:
            with self.assertRaises(ArchiveError):
                declare_loop(archive, "fix-sweep", max_iterations=0,
                             stop_when=["all batteries green"])

    def test_a_contract_without_a_stop_condition_refuses(self) -> None:
        with _archive() as archive:
            with self.assertRaises(ArchiveError):
                declare_loop(archive, "fix-sweep", max_iterations=5,
                             stop_when=[])

    def test_a_complete_contract_declares(self) -> None:
        with _archive() as archive:
            record = declare_loop(archive, "fix-sweep", max_iterations=5,
                                  stop_when=["all batteries green",
                                             "operator says stop"])
            self.assertEqual(record["data"]["max_iterations"], 5)
            self.assertEqual(len(record["data"]["stop_when"]), 2)


class StallEscalationTests(unittest.TestCase):
    def test_two_empty_ticks_demand_a_direction_change(self) -> None:
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=9,
                         stop_when=["green"])
            tick_loop(archive, "fix-sweep", progress=False)
            report = tick_loop(archive, "fix-sweep", progress=False)
            self.assertEqual(report["empty_streak"], 2)
            self.assertIn("direction", report["escalation"])

    def test_four_empty_ticks_demand_the_operator(self) -> None:
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=9,
                         stop_when=["green"])
            for _ in range(4):
                report = tick_loop(archive, "fix-sweep", progress=False)
            self.assertIn("operator", report["escalation"])

    def test_progress_resets_the_streak(self) -> None:
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=9,
                         stop_when=["green"])
            tick_loop(archive, "fix-sweep", progress=False)
            tick_loop(archive, "fix-sweep", progress=True,
                      note="battery three went green")
            report = tick_loop(archive, "fix-sweep", progress=False)
            self.assertEqual(report["empty_streak"], 1)
            self.assertIsNone(report["escalation"])

    def test_the_cap_refuses_further_ticks(self) -> None:
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=2,
                         stop_when=["green"])
            tick_loop(archive, "fix-sweep", progress=True)
            tick_loop(archive, "fix-sweep", progress=True)
            with self.assertRaises(ArchiveError):
                tick_loop(archive, "fix-sweep", progress=True)


class HonestEndTests(unittest.TestCase):
    def test_finished_at_the_cap_needs_evidence(self) -> None:
        # Budget exhaustion must never impersonate completion.
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=1,
                         stop_when=["green"])
            tick_loop(archive, "fix-sweep", progress=True)
            with self.assertRaises(ArchiveError):
                close_loop(archive, "fix-sweep", outcome="finished")
            record = close_loop(archive, "fix-sweep", outcome="finished",
                                evidence=["cmd:python -m unittest -> OK"])
            self.assertEqual(record["data"]["outcome"], "finished")

    def test_cut_off_needs_no_evidence_and_says_so(self) -> None:
        with _archive() as archive:
            declare_loop(archive, "fix-sweep", max_iterations=3,
                         stop_when=["green"])
            tick_loop(archive, "fix-sweep", progress=False)
            record = close_loop(archive, "fix-sweep", outcome="cut-off")
            self.assertEqual(record["data"]["outcome"], "cut-off")
            self.assertEqual(record["data"]["iterations_used"], 1)


if __name__ == "__main__":
    unittest.main()
