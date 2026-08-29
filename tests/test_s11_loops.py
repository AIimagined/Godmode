"""S11: the loops maintain themselves.

A: the debrief gauges its own staleness. D: `law amend` executes a
recommendation and newest-wins makes it the law. E: an instruction marker
with no imperative verb behind it is conversation, not a rule - both live
false captures from 2026-08-29 fail that bar. C: the flake registry parses.
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
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    amend_law, debrief, debrief_status, record_instruction_candidate, top_laws,
)


class DebriefGaugeTests(unittest.TestCase):
    def test_no_receipt_ever_reads_stale(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            status = debrief_status(archive)
        self.assertTrue(status["stale"])
        self.assertIsNone(status["last_receipt_seq"])

    def test_a_fresh_debrief_clears_staleness(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            debrief(archive)
            status = debrief_status(archive)
        self.assertFalse(status["stale"])
        self.assertLessEqual(status["records_since"], 1)


class AmendTests(unittest.TestCase):
    def _law(self, archive, subject, guard):
        return archive.append("lesson", subject, {
            "status": "active", "generalized_guard": guard}, evidence=[])

    def test_an_amendment_becomes_the_law(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "one-law", "old guard text here")["sequence"]
            amend_law(archive, seq, "new guard text here, reviewed")
            laws = top_laws(archive, 5)
        subjects = [l["subject"] for l in laws]
        self.assertEqual(subjects.count("one-law"), 1)
        self.assertIn("new guard", laws[0]["guard"])

    def test_amending_a_retired_law_refuses(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "dead-law", "old guard")["sequence"]
            archive.append("lesson", "dead-law", {"status": "retired"}, evidence=[])
            with self.assertRaises(ArchiveError):
                amend_law(archive, seq, "resurrection attempt")

    def test_an_empty_guard_refuses(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "a-law", "guard")["sequence"]
            with self.assertRaises(ArchiveError):
                amend_law(archive, seq, "   ")


class InstructionPrecisionTests(unittest.TestCase):
    def test_the_live_false_capture_no_longer_fires(self) -> None:
        # Verbatim shape of the 2026-08-29 chat-noise capture (seq 4583).
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(record_instruction_candidate(
                archive, "Whenever ready: 9 fragments to v0.3.3 why dont we "
                         "do this now?", session="S-1"))

    def test_a_real_standing_rule_still_fires(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_instruction_candidate(
                archive, "always run the godmode-governance preview before "
                         "any multi-file removal or untracking", session="S-1")
        self.assertIsNotNone(record)

    def test_a_marker_with_a_distant_verb_does_not_fire(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(record_instruction_candidate(
                archive, "never in all my years of looking at broken pipelines "
                         "and flaky suites did the batch run clean", session="S-1"))


class FlakyRegistryTests(unittest.TestCase):
    def test_registry_parses_and_names_the_known_flake(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "dev"))
        import run_with_flaky_retry as runner

        flaky = runner.known_flaky()
        self.assertIn(
            "tests.test_law.BriefTests.test_session_start_brief_carries_the_top_laws",
            flaky)

    def test_failure_parser_reads_unittest_output(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "dev"))
        import run_with_flaky_retry as runner

        sample = ("FAIL: test_x (tests.test_mod.SomeTests.test_x)\n"
                  "ERROR: test_y (tests.test_other.OtherTests.test_y)\n")
        self.assertEqual(runner.failing_ids(sample),
                         ["tests.test_mod.SomeTests.test_x",
                          "tests.test_other.OtherTests.test_y"])


if __name__ == "__main__":
    unittest.main()
