"""B4-5: per-session counts rendered as a time series, gaps stated.

The session-log already writes one `metric` record per session (counts only,
or a stated gap when the transcript could not be read). `godmode trends`
folds those records into a series - and holds the same two disciplines the
ROI reports pinned first: no causal-attribution word ever reaches the
rendered output (CAUSAL_DENYLIST), and an unmeasured session stays a stated
gap, never an interpolated number (C-79: gaps stay gaps).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_roi import CAUSAL_DENYLIST  # noqa: E402
from godmode_runtime.godmode_session_log import record_measurement  # noqa: E402
from godmode_runtime.godmode_trends import render_trends, trends_report  # noqa: E402

from test_godmode_runtime import isolated_project  # noqa: E402


def _transcript(path: Path, turns: int, commands: int) -> Path:
    """A minimal transcript the real `measure()` tallies: `turns` assistant
    turns, `commands` Bash tool calls."""
    lines = []
    for _ in range(turns):
        lines.append(json.dumps({"message": {
            "role": "assistant",
            "usage": {"input_tokens": 100, "output_tokens": 25},
            "content": [],
        }}))
    for i in range(commands):
        lines.append(json.dumps({"message": {
            "role": "user",
            "content": [{"type": "tool_use", "name": "Bash",
                         "input": {"command": f"echo {i}"}}],
        }}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TrendsSeriesIsCountsOnly(unittest.TestCase):
    def test_measured_sessions_fold_into_an_ordered_series(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record_measurement(archive, _transcript(project / "t1.jsonl", 3, 2),
                               session="S-1")
            record_measurement(archive, _transcript(project / "t2.jsonl", 5, 4),
                               session="S-2")
            report = trends_report(archive)
            series = report["series"]
            self.assertEqual(len(series), 2)
            self.assertEqual([row["session"] for row in series], ["S-1", "S-2"])
            self.assertEqual(series[0]["turns"], 3)
            self.assertEqual(series[1]["commands"], 4)
            self.assertTrue(all(row["measured"] for row in series))
            self.assertTrue(all(b.startswith("seq:") for b in report["basis"]))

    def test_an_unmeasured_session_is_a_stated_gap_never_a_number(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record_measurement(archive, _transcript(project / "t1.jsonl", 3, 2),
                               session="S-1")
            record_measurement(archive, None, session="S-2")  # stated gap
            report = trends_report(archive)
            self.assertEqual(report["gaps"], 1)
            gap_row = report["series"][-1]
            self.assertFalse(gap_row["measured"])
            self.assertTrue(gap_row["reason"])
            for field in ("turns", "commands", "test_runs",
                          "tokens_in", "tokens_out"):
                self.assertNotIn(field, gap_row,
                                 "a gap row must never carry a count")

    def test_free_text_never_reaches_the_report(self) -> None:
        """The fold reads a record's counts, never its free-text fields -
        the same outward discipline every other fold here holds."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            marker = "FOURTEEN-PURPLE-OTTERS"
            archive.append("metric", "session measurement",
                           {"measured": True, "turns": 1, "commands": 0,
                            "test_runs": 0, "tokens_in": 1, "tokens_out": 1,
                            "tool_calls": {}, "session": "S-1",
                            "notes": marker}, evidence=[])
            report = trends_report(archive)
            self.assertNotIn(marker, json.dumps(report))
            self.assertNotIn(marker, render_trends(report))


class TrendsRenderHoldsTheCausalDenylist(unittest.TestCase):
    def test_the_render_is_causal_free_and_states_gaps(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record_measurement(archive, _transcript(project / "t1.jsonl", 3, 2),
                               session="S-1")
            record_measurement(archive, None, session="S-2")
            text = render_trends(trends_report(archive))
            for word in CAUSAL_DENYLIST:
                self.assertNotIn(word, text.lower())
            self.assertIn("unmeasured", text)
            self.assertIn("S-1", text)

    def test_a_planted_causal_word_is_caught_by_the_check(self) -> None:
        """The denylist check must bite, not just pass: the exact assertion
        used above, run against a violating text, fails."""
        violating = "this trend saved 4 hours"
        hits = [w for w in CAUSAL_DENYLIST if w in violating.lower()]
        self.assertTrue(hits)

    def test_an_empty_archive_states_absence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            report = trends_report(archive)
            self.assertEqual(report["series"], [])
            self.assertIn("no session measurements", render_trends(report))


class TrendsConsoleCommand(unittest.TestCase):
    def test_godmode_trends_returns_the_report(self) -> None:
        from godmode_runtime import godmode_console as console
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record_measurement(archive, _transcript(project / "t1.jsonl", 2, 1),
                               session="S-1")
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                code = console.main(["--project", str(project), "trends"])
            payload = json.loads(out.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(len(payload["series"]), 1)


if __name__ == "__main__":
    unittest.main()
