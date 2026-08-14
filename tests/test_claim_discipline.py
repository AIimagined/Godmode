"""Claim-discipline detectors M19-M21 and the truncation-honest compressor.

Absorbed from a recorded lessons corpus:

- M19 carried-status-unverified: a "pending sweep" that reports labels is not
  a sweep - six of nine listed items were already shipped (L-189/L-192/L-243).
- M20 remedy-on-hypothesis: a remedy was designed for "a weak fallback model
  rewrote the video" before any differential ran; the diff showed a different
  mechanism entirely (L-267/L-236).
- M21 absence-without-control: an empty recursive search became a premise
  twice in one hour, and a search harness that could not run reported the
  world as empty (L-269/L-294/L-68).
- Compressor: a head-only clip deleted exactly the line a blank-video RCA
  needed; a cap that bites must say so (L-187).

Each detector test carries the planted violation seen red and the adjacent
innocent form seen green.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_compress import compress_record  # noqa: E402
from godmode_runtime.godmode_mistakes import (  # noqa: E402
    absence_without_control,
    carried_status_unverified,
    remedy_on_hypothesis,
)


def _claim(sequence: int, text: str, evidence: list[str] | None = None,
           grade: str = "", subject: str = "subject") -> dict:
    return {
        "kind": "claim", "sequence": sequence, "subject": subject,
        "data": {"text": text, "grade": grade},
        "evidence": evidence or [],
    }


class CarriedStatusTests(unittest.TestCase):
    def test_a_pending_list_without_a_check_is_blocked(self) -> None:
        findings = carried_status_unverified([
            _claim(1, "carried forward: the render QC gap is still open")])
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["blocking"])

    def test_a_verified_carried_status_is_clean(self) -> None:
        findings = carried_status_unverified([
            _claim(1, "the render QC gap is still open",
                   evidence=["file:lib/renderQc.py", "seq:12"])])
        self.assertEqual(findings, [])

    def test_a_swept_list_naming_its_sweep_is_clean(self) -> None:
        findings = carried_status_unverified([
            _claim(1, "3 pending items after re-check",
                   evidence=["searched:registry rows 1-43 against lib/"])])
        self.assertEqual(findings, [])

    def test_fresh_prose_without_status_vocabulary_is_clean(self) -> None:
        findings = carried_status_unverified([
            _claim(1, "the gate now refuses unsigned uploads")])
        self.assertEqual(findings, [])


class RemedyOnHypothesisTests(unittest.TestCase):
    def test_a_plan_citing_a_hypothesis_root_is_reported(self) -> None:
        records = [
            _claim(1, "the fallback model rewrote the video",
                   grade="hypothesis", subject="blank-video"),
            {"kind": "plan", "sequence": 2, "subject": "blank-video",
             "data": {"state": "active"}, "evidence": ["seq:1"]},
        ]
        findings = remedy_on_hypothesis(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["detector"], "remedy-on-hypothesis")

    def test_a_plan_on_a_confirmed_subject_is_clean(self) -> None:
        records = [
            _claim(1, "the fallback model rewrote the video",
                   grade="hypothesis", subject="blank-video"),
            _claim(2, "the extractor cut the scene at a nested close tag",
                   grade="confirmed", subject="blank-video",
                   evidence=["file:lib/director.py"]),
            {"kind": "plan", "sequence": 3, "subject": "blank-video",
             "data": {"state": "active"}, "evidence": ["seq:1", "seq:2"]},
        ]
        self.assertEqual(remedy_on_hypothesis(records), [])

    def test_a_plan_citing_only_confirmed_claims_is_clean(self) -> None:
        records = [
            _claim(1, "the cap bit at 32768", grade="confirmed",
                   subject="truncation", evidence=["file:lib/aiRace.ts"]),
            {"kind": "plan", "sequence": 2, "subject": "truncation",
             "data": {"state": "active"}, "evidence": ["seq:1"]},
        ]
        self.assertEqual(remedy_on_hypothesis(records), [])


class AbsenceWithoutControlTests(unittest.TestCase):
    def test_an_extent_stated_absence_without_a_control_is_advised(self) -> None:
        findings = absence_without_control([
            _claim(1, "no references found across the whole tree",
                   evidence=["searched:rg calls_x src/ tests/"])])
        self.assertEqual(len(findings), 1)

    def test_reversed_word_order_absence_idioms_are_caught(self) -> None:
        # Found by an adversarial pass: only "nothing found" (not "found
        # nothing") was covered, so "the search turned up nothing" and its
        # siblings passed through both M18 and M21 completely undetected.
        for text in (
            "the search turned up nothing across every module",
            "the query came back empty after checking all rows",
            "the scan yielded nothing across the whole repo",
        ):
            findings = absence_without_control([
                _claim(1, text, evidence=["searched:rg pattern ."])])
            self.assertEqual(len(findings), 1, text)
        self.assertFalse(findings[0]["blocking"])

    def test_a_controlled_absence_is_clean(self) -> None:
        findings = absence_without_control([
            _claim(1, "no references found across the whole tree",
                   evidence=["searched:rg calls_x src/",
                             "control:rg calls_y src/ -> 14 hits"])])
        self.assertEqual(findings, [])

    def test_a_second_method_absence_is_clean(self) -> None:
        findings = absence_without_control([
            _claim(1, "no callers anywhere in the repo",
                   evidence=["searched:rg pattern src/",
                             "second:runtime probe raised NameError"])])
        self.assertEqual(findings, [])

    def test_an_extent_free_absence_is_left_to_m18(self) -> None:
        # One defect, one detector: the extent-free form is M18's finding.
        findings = absence_without_control([
            _claim(1, "nothing found for that symbol")])
        self.assertEqual(findings, [])


class TruncationHonestCompressorTests(unittest.TestCase):
    def test_a_clipped_subject_is_marked(self) -> None:
        record = {"kind": "claim", "sequence": 7, "subject": "x" * 300,
                  "data": {"grade": "confirmed"}}
        view = compress_record(record)
        self.assertEqual(len(view["subject"]), 120)
        self.assertEqual(view["mask"]["subject_truncated_at"], 120)

    def test_a_short_subject_carries_no_marker(self) -> None:
        record = {"kind": "claim", "sequence": 7, "subject": "short",
                  "data": {"grade": "confirmed"}}
        view = compress_record(record)
        self.assertNotIn("subject_truncated_at", view["mask"])

    def test_a_subject_at_exactly_the_cap_is_not_marked(self) -> None:
        # length == cap with nothing removed is complete, not clipped; the
        # marker is for bites, and a false marker teaches readers to skip it.
        record = {"kind": "claim", "sequence": 7, "subject": "x" * 120,
                  "data": {"grade": "confirmed"}}
        view = compress_record(record)
        self.assertNotIn("subject_truncated_at", view["mask"])


if __name__ == "__main__":
    unittest.main()
