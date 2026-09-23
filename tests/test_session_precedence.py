"""The brief shows a declaration before an inference, and per-day catch-up after a gap."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_lens import precedence_block, catch_up_block  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class PrecedenceTests(unittest.TestCase):
    def test_declared_before_inferred_and_conflict_named(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            # Real plan records carry `steps` at the top level of `data`, as
            # `text`/`status` pairs (see tests/test_field_report_part5.py and
            # godmode_lens.ledger_block, which reads `data["steps"]`
            # directly - not the plan contract's `steps` string field from
            # godmode_plan.py, which is prose, not a list of step dicts).
            archive.append("plan", "ship it", {"status": "active", "steps": [
                {"text": "write tests", "status": "todo"}]})
            archive.append("checkpoint", "day end", {"status": "in-progress", "summary": "paused", "next": ["refactor the parser"]})
            block = precedence_block(archive)
            sources = [row["source"] for row in block["precedence"]]
            self.assertEqual(sources[: sources.index("inferred")], ["declared"] * sources.index("inferred"))
            conflict = next((c for c in block["conflicts"] if c["field"] == "next"), None)
            self.assertIsNotNone(conflict, block)
            # Fix round 2: both sides of this conflict are declared (the
            # checkpoint's `next` and the plan's own pending step), so the
            # row names each side's source instead of calling either one
            # "inferred".
            self.assertEqual(
                set(conflict),
                {"field", "declared", "declared_by", "conflicts_with", "conflicts_with_source"},
            )
            self.assertNotIn("inferred", conflict)
            self.assertEqual(conflict["declared_by"], "checkpoint")
            self.assertEqual(conflict["conflicts_with_source"], "plan")

    def test_long_step_text_does_not_trigger_a_truncation_false_conflict(self) -> None:
        # Fix round 1: `ledger_block` truncates a step's text to 80 chars for
        # display, but the conflict check must compare full text on both
        # sides - otherwise a checkpoint whose `next` names the same step
        # verbatim, when that step's text is longer than 80 chars, is
        # reported as a spurious conflict purely from the truncation.
        long_step = ("write comprehensive integration tests covering every edge "
                     "case of the retry wrapper and its backoff schedule end to end")
        self.assertGreater(len(long_step), 80)
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("plan", "ship it", {"status": "active", "steps": [
                {"text": long_step, "status": "todo"}]})
            archive.append("checkpoint", "day end", {"status": "in-progress", "summary": "paused",
                                                       "next": [long_step]})
            block = precedence_block(archive)
            self.assertEqual(block["conflicts"], [])

    def test_catch_up_per_day(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("checkpoint", "start", {"status": "in-progress", "summary": "s", "next": []})
            records = archive.read_events()
            # simulate two later days by rewriting recorded_at is not allowed; instead the helper takes an explicit `now`.
            # `now` is derived from the record's own timestamp, never a calendar literal: a pinned date
            # silently turned this test red once the real clock passed it.
            from datetime import datetime, timedelta
            recorded = datetime.fromisoformat(str(records[-1]["recorded_at"]))
            block = catch_up_block(archive, now=(recorded + timedelta(days=2)).isoformat())
            self.assertGreaterEqual(len(block["catch_up"]), 1)
            self.assertTrue(all({"day", "records", "kinds"} <= set(row) for row in block["catch_up"]))


if __name__ == "__main__":
    unittest.main()
