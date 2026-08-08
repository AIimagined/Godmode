"""Which tags have no release, computed rather than remembered.

An agent stated which releases were published from seventeen-hour-old recall,
while holding working API access it had used minutes earlier. The external-claim
detector exists and would have graded that assertion — but it is reachable only
through `record_claim`, so it never sees anything said rather than recorded.
Godmode governs what is written down, not what is said.

Widening the detector is the wrong remedy. It would still depend on the agent
routing its own sentence through a check, which is the failure mode, not the
fix. The fix is to make the fact computable: a handover that says "v0.2.6 is
unpublished" should be reading it, not recalling it.

Comparison only. Nothing here publishes anything, and nothing here talks to a
network unless a caller hands it releases it fetched itself — so the offline
half is testable, which is the half that decides.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_release import compare_releases  # noqa: E402


class ComparisonTests(unittest.TestCase):
    def test_a_tag_with_no_release_is_reported(self) -> None:
        report = compare_releases(tags=["v0.2.5", "v0.2.6"], published=["v0.2.5"])
        self.assertEqual(report["unpublished"], ["v0.2.6"])
        self.assertEqual(report["verdict"], "unpublished-tags")

    def test_everything_published_is_clean(self) -> None:
        report = compare_releases(tags=["v0.2.5"], published=["v0.2.5"])
        self.assertEqual(report["unpublished"], [])
        self.assertEqual(report["verdict"], "all-tags-published")

    def test_a_release_with_no_tag_is_reported_too(self) -> None:
        """A release pointing at a tag that no longer exists is a broken
        download link, and only the comparison can see it."""
        report = compare_releases(tags=["v0.2.5"], published=["v0.2.5", "v0.9.9"])
        self.assertEqual(report["published_without_tag"], ["v0.9.9"])

    def test_the_newest_tag_is_named(self) -> None:
        report = compare_releases(tags=["v0.2.4", "v0.2.10", "v0.2.6"], published=[])
        self.assertEqual(report["newest_tag"], "v0.2.10")

    def test_ordering_is_by_version_not_by_string(self) -> None:
        report = compare_releases(tags=["v0.2.9", "v0.2.10"], published=["v0.2.9"])
        self.assertEqual(report["unpublished"], ["v0.2.10"])


class HonestyTests(unittest.TestCase):
    def test_releases_that_could_not_be_fetched_are_not_read_as_none(self) -> None:
        """Absent is not empty. Reporting "nothing is published" because the
        API could not be reached is exactly the false certainty this replaces.
        """
        report = compare_releases(tags=["v0.2.6"], published=None)
        self.assertEqual(report["verdict"], "insufficient-data")
        self.assertIsNone(report["unpublished"])
        self.assertIn("could not be read", report["reason"])

    def test_a_project_with_no_tags_reports_nothing_to_publish(self) -> None:
        report = compare_releases(tags=[], published=[])
        self.assertEqual(report["verdict"], "no-tags")

    def test_the_report_states_what_it_compared(self) -> None:
        report = compare_releases(tags=["v0.2.5", "v0.2.6"], published=["v0.2.5"])
        self.assertEqual(report["tags_examined"], 2)
        self.assertEqual(report["releases_examined"], 1)


if __name__ == "__main__":
    unittest.main()
