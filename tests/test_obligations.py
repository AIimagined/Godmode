"""An obligation that is carried is not thereby still worth doing.

The continuity machinery is good at "do not forget X" and had nothing for
"stop repeating X, it is done". Both are continuity failures; only one was
implemented, so a next-action created validly and made moot by a later event
was restated in every handover until a human noticed.

The case that produced this: "publish the v0.2.2 release page", recorded when
v0.2.2 was the newest release, repeated across three handovers after v0.2.3
and v0.2.4 had superseded it, and retired only when the owner asked why it was
still there.

Findings, never closures. Auto-retiring would be the mirror mistake: the fix
for carrying something too long must not become dropping it too early.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_obligations import (  # noqa: E402
    normalise_obligation, review_obligations,
)


class Handover:
    """A checkpoint record, in the shape the archive stores."""

    def __init__(self, sequence: int, *obligations: str) -> None:
        self.record = {"sequence": sequence, "kind": "checkpoint",
                       "subject": f"handover {sequence}",
                       "data": {"next": list(obligations)}}


def _records(*handovers: Handover) -> list[dict]:
    return [handover.record for handover in handovers]


class NormalisationTests(unittest.TestCase):
    def test_a_version_is_not_part_of_the_obligation(self) -> None:
        """`publish the v0.2.2 page` and `publish the v0.2.5 page` are the same
        standing obligation about different releases, which is exactly what
        makes the earlier one retirable."""
        self.assertEqual(
            normalise_obligation("Owner: publish the v0.2.2 Release page"),
            normalise_obligation("Owner: publish the v0.2.5 Release page"))

    def test_punctuation_and_case_do_not_make_a_new_obligation(self) -> None:
        self.assertEqual(
            normalise_obligation("Owner: update the plugin, then re-test."),
            normalise_obligation("owner update the plugin then re-test"))

    def test_different_obligations_stay_different(self) -> None:
        self.assertNotEqual(
            normalise_obligation("publish the release page"),
            normalise_obligation("rewrite the author identity"))


class RepetitionTests(unittest.TestCase):
    def test_an_obligation_carried_unchanged_is_reported(self) -> None:
        report = review_obligations(_records(
            Handover(1, "Owner: update the plugin and re-test"),
            Handover(2, "Owner: update the plugin and re-test"),
            Handover(3, "Owner: update the plugin and re-test"),
        ))
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("carried-unchanged", codes)

    def test_carrying_something_twice_is_not_yet_a_finding(self) -> None:
        """Two handovers is a task in progress. The signal is persistence."""
        report = review_obligations(_records(
            Handover(1, "Owner: update the plugin"),
            Handover(2, "Owner: update the plugin"),
        ))
        self.assertEqual(report["findings"], [])

    def test_a_finding_says_how_long_it_has_been_carried(self) -> None:
        report = review_obligations(_records(
            Handover(1, "do the thing"), Handover(2, "do the thing"),
            Handover(3, "do the thing"), Handover(4, "do the thing"),
        ))
        finding = report["findings"][0]
        self.assertEqual(finding["carried"], 4)
        self.assertEqual(finding["first_seen"], 1)
        self.assertEqual(finding["last_seen"], 4)


class SupersessionTests(unittest.TestCase):
    def test_an_obligation_about_an_older_version_is_superseded(self) -> None:
        report = review_obligations(_records(
            Handover(1, "Owner: publish the v0.2.2 Release page"),
            Handover(2, "Owner: publish the v0.2.5 Release page"),
        ))
        superseded = [f for f in report["findings"] if f["code"] == "version-superseded"]
        self.assertTrue(superseded)
        self.assertIn("v0.2.2", superseded[0]["obligation"])
        self.assertIn("0.2.5", superseded[0]["detail"])

    def test_the_newest_version_of_an_obligation_is_not_superseded(self) -> None:
        report = review_obligations(_records(
            Handover(1, "publish the v0.2.2 page"),
            Handover(2, "publish the v0.2.5 page"),
        ))
        for finding in report["findings"]:
            self.assertNotIn("v0.2.5", finding["obligation"])

    def test_an_unversioned_obligation_is_never_version_superseded(self) -> None:
        report = review_obligations(_records(
            Handover(1, "rewrite the author identity"),
            Handover(2, "rewrite the author identity"),
        ))
        codes = {f["code"] for f in report["findings"]}
        self.assertNotIn("version-superseded", codes)


class RealHandoverTests(unittest.TestCase):
    """The obligations this module was built for, copied from the archive.

    The first implementation grouped by exact normalised text and found
    nothing in twenty-two real handovers, because real obligations are
    compound sentences that drift in wording while meaning the same thing.
    A detector tested only on tidy synthetic strings is the same mistake the
    gate made four times over.
    """

    HANDOVERS = (
        Handover(48,
                 "Owner: publish the v0.2.3 Release page only - v0.2.2 page is "
                 "superseded and not needed",
                 "Owner: update installed plugin to verify the gate live; confirm CI"),
        Handover(49,
                 "Owner: update plugin to 0.2.4 and re-test live; publish the v0.2.4 "
                 "Release page (skip 0.2.2 and 0.2.3)"),
        Handover(50,
                 "Owner: update plugin to 0.2.5 and re-test; publish the v0.2.5 "
                 "Release page only"),
    )

    def test_the_repeated_release_page_obligation_is_found(self) -> None:
        report = review_obligations(_records(*self.HANDOVERS))
        self.assertNotEqual(report["findings"], [],
                            "the case this module exists for went unreported")
        text = " ".join(f["obligation"] + f["detail"] for f in report["findings"])
        self.assertIn("elease page", text)

    def test_a_compound_obligation_is_more_than_one_obligation(self) -> None:
        """`update the plugin; publish the page` is two things, and joining
        them meant neither could ever be recognised as repeated."""
        report = review_obligations(_records(*self.HANDOVERS))
        self.assertGreater(report["obligations_seen"], len(self.HANDOVERS))

    def test_the_superseded_release_is_named(self) -> None:
        report = review_obligations(_records(*self.HANDOVERS))
        superseded = [f for f in report["findings"] if f["code"] == "version-superseded"]
        self.assertTrue(superseded, report["findings"])


class ContractTests(unittest.TestCase):
    def test_nothing_is_ever_closed_automatically(self) -> None:
        """The fix for carrying something too long must not become dropping it
        too early, so every finding is a question and none is a decision."""
        report = review_obligations(_records(
            Handover(1, "publish the v0.1.0 page"), Handover(2, "publish the v0.2.0 page"),
            Handover(3, "publish the v0.3.0 page"),
        ))
        for finding in report["findings"]:
            self.assertIn("question", finding)
            self.assertNotIn("closed", finding)
            self.assertNotIn("retired", finding)

    def test_a_clean_history_reports_nothing(self) -> None:
        report = review_obligations(_records(
            Handover(1, "first thing"), Handover(2, "second thing"),
            Handover(3, "third thing"),
        ))
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "no-stale-obligations")

    def test_the_report_states_what_it_examined(self) -> None:
        report = review_obligations(_records(
            Handover(1, "rewrite the author identity"),
            Handover(2, "confirm the build pipeline")))
        self.assertEqual(report["handovers_examined"], 2)
        self.assertEqual(report["obligations_seen"], 2)

    def test_an_obligation_of_only_filler_words_counts_as_none(self) -> None:
        """Nothing distinctive is left to compare, so it cannot be grouped —
        and counting it would overstate what was actually examined."""
        report = review_obligations(_records(Handover(1, "the"), Handover(2, "and")))
        self.assertEqual(report["obligations_seen"], 0)


if __name__ == "__main__":
    unittest.main()
