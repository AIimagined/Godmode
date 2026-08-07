"""The ranking contract, pinned as regressions.

Rank fusion was prototyped as a replacement and rejected on measurement, so
what remains here is the set of properties the shipped scorer must keep: role
authority carries a segment the task wording missed, relevance can still lift a
lower-weighted document, and the order never depends on input order.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_corpus import Segment, rank  # noqa: E402


def _segment(path: str, weight: float, body: str, line: int = 1) -> Segment:
    return Segment(role="operating-guide", weight=weight, path=path,
                   heading="section", start_line=line, end_line=line + 1, body=body)


class RankContractTests(unittest.TestCase):
    """The guarantees the previous scorer made, which fusion must keep."""

    def test_a_segment_matching_nothing_still_ranks_by_role(self) -> None:
        segments = [
            _segment("LOW.md", 0.2, "nothing relevant here at all"),
            _segment("HIGH.md", 1.0, "unrelated prose about weather"),
        ]
        ordered = [segment.path for segment, _ in rank(segments, "token rotation")]
        self.assertEqual(ordered[0], "HIGH.md")

    def test_relevance_can_lift_a_lower_weighted_document(self) -> None:
        segments = [
            _segment("HIGH.md", 1.0, "weather and gardening notes"),
            _segment("LOW.md", 0.6, "token rotation replay defence and rotation windows"),
        ]
        ordered = [segment.path for segment, _ in rank(segments, "token rotation replay")]
        self.assertEqual(ordered[0], "LOW.md")

    def test_ranking_is_deterministic(self) -> None:
        segments = [_segment(f"D{i}.md", 1.0 - i / 10, f"body {i} rotation") for i in range(6)]
        first = [(s.path, score) for s, score in rank(segments, "rotation")]
        for _ in range(5):
            self.assertEqual([(s.path, score) for s, score in rank(segments, "rotation")], first)

    def test_ties_break_on_path_then_line_not_on_input_order(self) -> None:
        segments = [
            _segment("b.md", 1.0, "same body", line=1),
            _segment("a.md", 1.0, "same body", line=1),
        ]
        forward = [s.path for s, _ in rank(segments, "unrelated")]
        backward = [s.path for s, _ in rank(list(reversed(segments)), "unrelated")]
        self.assertEqual(forward, backward)
        self.assertEqual(forward[0], "a.md")

    def test_freshness_participates_as_a_vote_not_a_nudge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            for name in ("stale.md", "fresh.md"):
                (project / name).write_text("token rotation notes", encoding="utf-8")
            import os, time
            old = time.time() - 86_400 * 30
            os.utime(project / "stale.md", (old, old))
            segments = [_segment("stale.md", 1.0, "token rotation notes"),
                        _segment("fresh.md", 1.0, "token rotation notes")]
            ordered = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            self.assertEqual(ordered[0], "fresh.md")


class BriefEquivalenceTests(unittest.TestCase):
    def test_the_brief_stays_byte_identical_across_runs(self) -> None:
        from godmode_runtime.godmode_corpus import build_brief

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "GODMODE.md").write_text(
                "# Guide\n\nAlways verify before claiming.\n", encoding="utf-8")
            first = json.dumps(build_brief(project, "verify claims", 1200), sort_keys=True)
            second = json.dumps(build_brief(project, "verify claims", 1200), sort_keys=True)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
