"""Tests for the termination algebra + budgets (U-R1, `godmode_stop.py`).

These pin the algebra itself - each predicate, composition's truth table,
the fail-loud spent/reset lifecycle, and `attempt()`'s subprocess-killing
budget - plus one cross-unit test proving a truncated result cannot be
laundered into a confirmed verdict through the archive seam
(`godmode_invariants._verdict_invariants`, owned by Task 1/U-V1, untouched
here).
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_stop import (  # noqa: E402
    And,
    MaxRecords,
    MaxWall,
    MetricPlateau,
    OperatorStop,
    Or,
    SpentStopError,
    Stop,
    attempt,
)


def _records(*kinds: str) -> list[dict]:
    return [{"kind": kind, "data": {}} for kind in kinds]


def _metric_records(*values: float, name: str = "score") -> list[dict]:
    return [{"kind": "metric", "data": {name: v}} for v in values]


@contextmanager
def isolated_archive():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, archive


class MaxRecordsTests(unittest.TestCase):
    def test_fires_once_the_running_total_reaches_n(self) -> None:
        stop = MaxRecords(3)
        self.assertIsNone(stop(_records("action", "action")))
        self.assertFalse(stop.spent)
        reason = stop(_records("action"))
        self.assertIsNotNone(reason)
        self.assertIn("MaxRecords(3)", reason)
        self.assertTrue(stop.spent)

    def test_empty_delta_never_fires(self) -> None:
        stop = MaxRecords(1)
        for _ in range(5):
            self.assertIsNone(stop([]))


class MaxWallTests(unittest.TestCase):
    def test_fires_once_the_budget_elapses(self) -> None:
        stop = MaxWall(0.05)
        self.assertIsNone(stop([]))
        time.sleep(0.08)
        reason = stop([])
        self.assertIsNotNone(reason)
        self.assertIn("MaxWall", reason)


class OperatorStopTests(unittest.TestCase):
    def test_fires_only_once_the_flag_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            flag = Path(raw) / ".godmode-stop"
            stop = OperatorStop(flag)
            self.assertIsNone(stop([]))
            flag.write_text("", encoding="utf-8")
            reason = stop([])
            self.assertIsNotNone(reason)
            self.assertIn(str(flag), reason)


class MetricPlateauTests(unittest.TestCase):
    def test_fires_after_patience_consecutive_flat_observations(self) -> None:
        stop = MetricPlateau("score", eps=0.01, patience=3)
        records = _metric_records(10.0, 10.005, 10.009)
        self.assertIsNone(stop(records[:2]))
        reason = stop(records[2:])
        self.assertIsNotNone(reason)
        self.assertIn("MetricPlateau(score)", reason)

    def test_movement_beyond_eps_resets_the_streak(self) -> None:
        stop = MetricPlateau("score", eps=0.01, patience=3)
        records = _metric_records(10.0, 10.005, 5.0, 5.001, 5.002)
        self.assertIsNone(stop(records[:3]))  # the jump to 5.0 resets the streak
        reason = stop(records[3:])
        self.assertIsNotNone(reason)  # 5.0 -> 5.001 -> 5.002 is a fresh streak of 3

    def test_records_missing_the_metric_are_ignored(self) -> None:
        stop = MetricPlateau("score", eps=0.01, patience=2)
        self.assertIsNone(stop([{"kind": "action", "data": {"other": 1}}]))


class SpentLifecycleTests(unittest.TestCase):
    def test_spent_stop_raises_on_reuse_without_reset(self) -> None:
        stop = MaxRecords(1)
        self.assertIsNotNone(stop(_records("action")))
        with self.assertRaises(SpentStopError):
            stop(_records("action"))

    def test_reset_clears_spent_and_accumulated_state(self) -> None:
        stop = MaxRecords(1)
        stop(_records("action"))
        self.assertTrue(stop.spent)
        stop.reset()
        self.assertFalse(stop.spent)
        # Accumulated state also cleared: a fresh delta of 0 does not fire.
        self.assertIsNone(stop([]))
        self.assertIsNotNone(stop(_records("action")))


class CompositionTruthTableTests(unittest.TestCase):
    """`&` needs every leaf to fire; `|` needs any one. Both name which leaf."""

    def test_and_requires_both_children_to_fire(self) -> None:
        combined = MaxRecords(2) & MaxRecords(3)
        self.assertIsInstance(combined, And)
        # Two records: the n=2 leaf alone has fired; And withholds.
        self.assertIsNone(combined(_records("a", "a")))
        # A third record: both leaves have now fired; And fires, naming both.
        reason = combined(_records("a"))
        self.assertIsNotNone(reason)
        self.assertIn("MaxRecords(2)", reason)
        self.assertIn("MaxRecords(3)", reason)

    def test_or_fires_the_instant_either_child_fires_and_names_it(self) -> None:
        combined = MaxRecords(2) | MaxRecords(10)
        self.assertIsInstance(combined, Or)
        reason = combined(_records("a", "a"))
        self.assertIsNotNone(reason)
        self.assertIn("MaxRecords(2)", reason)
        self.assertNotIn("MaxRecords(10)", reason)

    def test_composite_reset_clears_every_child(self) -> None:
        combined = MaxRecords(1) | MaxRecords(1)
        combined(_records("a"))
        self.assertTrue(combined.spent)
        combined.reset()
        self.assertFalse(combined.spent)
        for child in combined._children:  # type: ignore[attr-defined]
            self.assertFalse(child.spent)

    def test_flat_composition_does_not_nest(self) -> None:
        combined = MaxRecords(1) & MaxRecords(2) & MaxRecords(3)
        self.assertEqual(len(combined._children), 3)  # type: ignore[attr-defined]


class AttemptBudgetTests(unittest.TestCase):
    """`attempt(budget_s)`: yields a deadline, kills an overrunning subprocess,
    and marks the result truncated."""

    @staticmethod
    def _sleeper_script(tmp: Path, seconds: float) -> Path:
        script = tmp / "sleeper.py"
        script.write_text(f"import time\ntime.sleep({seconds})\n", encoding="utf-8")
        return script

    def test_yields_a_deadline_ahead_of_now(self) -> None:
        before = time.monotonic()
        with attempt(5.0) as handle:
            self.assertGreater(handle.deadline, before)
            self.assertLessEqual(handle.deadline, before + 5.5)

    def test_overrun_kills_the_subprocess_and_marks_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            script = self._sleeper_script(Path(raw), seconds=5.0)
            started = time.monotonic()
            with attempt(0.3) as handle:
                result = handle.run([sys.executable, str(script)])
            elapsed = time.monotonic() - started
            self.assertEqual(result["run_state"], "truncated")
            self.assertTrue(handle.truncated)
            # Killed well before the script's own 5s sleep would have finished.
            self.assertLess(elapsed, 4.0)

    def test_completion_within_budget_is_terminated_not_truncated(self) -> None:
        with attempt(5.0) as handle:
            result = handle.run([sys.executable, "-c", "print('done')"])
        self.assertEqual(result["run_state"], "terminated")
        self.assertEqual(result["returncode"], 0)
        self.assertFalse(handle.truncated)


class TruncatedFeedsConfirmedRefusalTests(unittest.TestCase):
    """Cross-unit integration: a truncated `attempt()` result fed into a
    'confirmed' verdict hits the archive-seam refusal
    (`godmode_invariants._verdict_invariants`) with no code here needing to
    know that rule exists."""

    def test_truncated_result_recorded_confirmed_is_refused_at_the_seam(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            script = Path(raw) / "sleeper.py"
            script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
            with attempt(0.2) as handle:
                result = handle.run([sys.executable, str(script)])
            self.assertEqual(result["run_state"], "truncated")

        with isolated_archive() as (_project, archive):
            with self.assertRaises(ArchiveError) as ctx:
                archive.append(
                    "verdict",
                    "budget-cut attempt",
                    {
                        "claim": "the attempt finished",
                        "claimed_value": "1",
                        "witness": {"kind": "file", "ref": "a.py"},
                        "checker": None,
                        "disposition": "confirmed",
                        "run_state": result["run_state"],
                        "acquitted_by": "independent",
                    },
                )
            self.assertIn("truncated", str(ctx.exception))


class WatchdogConsumesOperatorStopTests(unittest.TestCase):
    """`godmode_guardrails.watchdog` consumes `OperatorStop` (U-R1): presence
    of the flag interrupts the boundary scan regardless of the skip pattern."""

    def test_operator_stop_flag_interrupts_the_watchdog(self) -> None:
        from godmode_runtime.godmode_attest import open_session
        from godmode_runtime.godmode_guardrails import OPERATOR_STOP_FLAG, watchdog

        with isolated_archive() as (project, archive):
            session = open_session(archive, "watch")
            self.assertEqual(watchdog(archive, session)["verdict"], "nominal")
            (project / OPERATOR_STOP_FLAG).write_text("", encoding="utf-8")
            verdict = watchdog(archive, session)
            self.assertEqual(verdict["verdict"], "interrupt")
            self.assertIsNotNone(verdict["operator_stop"])


if __name__ == "__main__":
    unittest.main()
