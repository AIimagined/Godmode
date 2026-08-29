"""S10: the amendment loop (loopy 4112's adopted-but-unbuilt half).

A law delivered three times and never cited is a retire candidate; a law
whose correction recurs after delivery is an amend candidate with the
recurrence named; promotion stays autonomous behind the ladder; and the
debrief receipts itself so the next one starts where this one ended.
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

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    debrief, record_delivery, record_instruction_candidate, top_laws,
)


def _law(archive, subject: str, guard: str) -> int:
    record = archive.append(
        "lesson", subject,
        {"status": "active", "generalized_guard": guard}, evidence=[])
    return record["sequence"]


class DebriefTests(unittest.TestCase):
    def test_a_delivered_never_cited_law_is_a_retire_candidate(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = _law(archive, "old-law", "Always do the old thing first.")
            laws = top_laws(archive, 3)
            for _ in range(3):
                record_delivery(archive, laws, session="S-1")
            report = debrief(archive)
        self.assertIn(seq, report["needs_operator"]["retire_candidate"])

    def test_a_recurring_correction_after_delivery_is_an_amend_candidate(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = _law(archive, "checkpoint-subject-length",
                       "checkpoint subject summaries stay under the record "
                       "length limit before publishing")
            record_delivery(archive, top_laws(archive, 3), session="S-1")
            for session in ("S-2", "S-3"):
                record_instruction_candidate(
                    archive,
                    "always keep the checkpoint subject summaries under the "
                    "record length limit before publishing",
                    session=session)
            report = debrief(archive)
        self.assertIn(seq, report["needs_operator"]["amend_guard"])
        entry = next(e for e in report["laws"] if e["seq"] == seq)
        self.assertGreaterEqual(len(entry["recurred_after_delivery"]), 2)

    def test_a_cited_law_is_kept(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = _law(archive, "good-law", "Always cite before claiming done.")
            laws = top_laws(archive, 3)
            for _ in range(3):
                record_delivery(archive, laws, session="S-1")
            archive.append("action", "applied-it", {}, evidence=[f"seq:{seq}"])
            report = debrief(archive)
        entry = next(e for e in report["laws"] if e["seq"] == seq)
        self.assertEqual(entry["recommendation"], "keep")
        self.assertNotIn(seq, report["needs_operator"]["retire_candidate"])

    def test_promotion_stays_autonomous_behind_the_ladder(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_instruction_candidate(
                archive, "always preview removals before running them",
                session="S-1")
            report = debrief(archive)
        self.assertEqual(len(report["autonomous"]["promote_ready"]), 1)

    def test_the_debrief_receipts_itself_and_windows_advance(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _law(archive, "any-law", "Always check the window.")
            first = debrief(archive)
            second = debrief(archive)
        self.assertEqual(first["stopping_reason"], "window-exhausted")
        self.assertEqual(second["window"]["from_seq"], first["receipt_seq"])
        self.assertGreater(second["receipt_seq"], first["receipt_seq"])


if __name__ == "__main__":
    unittest.main()
