"""The staleness verdict is decided by a clock a test can hold still.

S5's planned task was an injectable clock for the iteration loop, on the
assumption that wall-clock time reached its decision path. It does not: the
loop decides on measured spend, context size, repeated failures and a window of
commits, none of which is a time read. An injectable clock there would have
been code with no caller.

The time-based decision that does exist is the staleness verdict. A baseline
older than a day warns, and the comparison is against `datetime.now()`, so a
test could only assert it by writing a timestamp far enough in the past to be
safely stale - which is a test that passes because of arithmetic nobody chose,
and cannot check the boundary at all.

The threshold is the interesting part and the only part worth pinning: one
minute either side of a day must decide differently, and no test can ask that
question of a clock it does not control.

Age alone is deliberately not staleness: when the working tree is available and
its inventory diff is clean, a dormant repository does not warn. That rule came
from a field report, and it is asserted here so an injected clock cannot be
mistaken for permission to warn on age alone.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_lens import detect_context_issues  # noqa: E402

FIXED_NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


def _inventory_record(captured: datetime, sequence: int = 1) -> dict:
    return {
        "kind": "inventory",
        "sequence": sequence,
        "subject": "baseline",
        "data": {"captured_at": captured.isoformat(), "files": {}},
    }


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.anchor = resolve_anchor(Path(self._tmp.name))

    def codes(self, age: timedelta, *, current_inventory=None) -> set[str]:
        records = [_inventory_record(FIXED_NOW - age)]
        issues = detect_context_issues(
            self.anchor, records, current_inventory, now=FIXED_NOW)
        return {i["code"] for i in issues}


class TheThresholdIsDecidable(Base):
    def test_just_over_a_day_is_stale(self) -> None:
        self.assertIn("stale-baseline", self.codes(timedelta(days=1, minutes=1)))

    def test_just_under_a_day_is_not_stale(self) -> None:
        self.assertNotIn("stale-baseline", self.codes(timedelta(days=1) - timedelta(minutes=1)))

    def test_the_reported_age_is_computed_from_the_injected_clock(self) -> None:
        records = [_inventory_record(FIXED_NOW - timedelta(hours=50))]
        issues = detect_context_issues(self.anchor, records, None, now=FIXED_NOW)
        stale = [i for i in issues if i["code"] == "stale-baseline"]
        self.assertTrue(stale)
        self.assertIn("50h", stale[0]["detail"])


class AgeAloneIsNotStaleness(Base):
    def test_an_old_baseline_over_an_unchanged_tree_does_not_warn(self) -> None:
        """Field report: a 117h-old baseline warned while the diff was clean."""
        codes = self.codes(timedelta(days=9), current_inventory={"files": {}})
        self.assertNotIn("stale-baseline", codes)


class TheDefaultIsStillTheRealClock(Base):
    def test_omitting_the_clock_uses_wall_time(self) -> None:
        """The injection is for tests; production reads the real clock."""
        records = [_inventory_record(datetime.now(timezone.utc) - timedelta(days=3))]
        issues = detect_context_issues(self.anchor, records, None)
        self.assertIn("stale-baseline", {i["code"] for i in issues})

    def test_a_fresh_baseline_under_the_real_clock_does_not_warn(self) -> None:
        records = [_inventory_record(datetime.now(timezone.utc) - timedelta(minutes=5))]
        issues = detect_context_issues(self.anchor, records, None)
        self.assertNotIn("stale-baseline", {i["code"] for i in issues})


if __name__ == "__main__":
    unittest.main()
