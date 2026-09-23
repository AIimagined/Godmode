"""A retired lesson stops pinning the surface it named.

The claim grader refuses to grade a surface `verified` while an active lesson
pins it, and tells the author to "cite the pin or retire it first". Neither
worked. Citing it from the claim does not clear the check, and retirement was
unreachable: the grader skipped a lesson only when that record's own status
read `retired`, records are append-only, and the CLI exposes no path that
writes a status onto an existing record.

So a later record with the same subject and a retired status left the original
active and still pinning, and any surface a lesson ever named could never be
graded verified again. A refusal that instructs an action the product does not
implement is the failure this release exists to eliminate, found inside one of
its own gates.

Retirement is now read the way every other status in this archive is read: the
newest record for a subject wins. That is the same supersession the obligation
and request kinds already rely on, not a new convention.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_sources import guard_pin_reason  # noqa: E402

SUBJECT = "the widget cache invalidation is confirmed by a differential"
CLAIM = "the widget cache invalidation is confirmed by a differential and now holds"
# H5 fix round 1: relevance is now a shared cited stem, and a stem only
# exists where the text carries path/identifier structure (`/`, `.`, `_`,
# `-`) - plain prose like SUBJECT carries none. The guard names a
# structural token so the cited command can actually reach it.
GUARD = "checked by widget_cache.verify before any claim"
CITE = ["cmd:sh widget_cache.verify"]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.archive = Chronicle(resolve_anchor(self.root))

    def lesson(self, status: str | None = None) -> None:
        data: dict = {"value": "x", "generalized_guard": GUARD}
        if status:
            data["status"] = status
        self.archive.append("lesson", SUBJECT, data)

    def pin_reason(self) -> str:
        return guard_pin_reason(self.root, self.archive, CLAIM, CITE)


class AnActiveLessonPins(Base):
    def test_an_active_lesson_produces_the_pin(self) -> None:
        """Positive control: without this a passing test proves nothing."""
        self.lesson()
        self.assertIn("pin already names this surface", self.pin_reason())

    def test_no_lesson_produces_no_advisory(self) -> None:
        self.assertEqual(self.pin_reason(), "")


class RetirementIsReachable(Base):
    def test_a_retired_record_for_the_same_subject_clears_the_pin(self) -> None:
        """The whole point: the instruction the refusal gives must work."""
        self.lesson()
        self.lesson(status="retired")
        self.assertEqual(self.pin_reason(), "")

    def test_a_lesson_retired_at_its_own_record_still_clears(self) -> None:
        """The path that already worked must keep working."""
        self.lesson(status="retired")
        self.assertEqual(self.pin_reason(), "")

    def test_reviving_a_retired_subject_pins_again(self) -> None:
        """Newest wins in both directions, or the rule is a trapdoor."""
        self.lesson()
        self.lesson(status="retired")
        self.lesson()
        self.assertIn("pin already names this surface", self.pin_reason())

    def test_retiring_one_subject_does_not_retire_another(self) -> None:
        self.lesson()
        self.archive.append("lesson", "an unrelated lesson about timers",
                            {"value": "x", "status": "retired"})
        self.assertIn("pin already names this surface", self.pin_reason())


class OtherSettledStatusesAlsoClear(Base):
    def test_superseded_and_withdrawn_clear_the_pin(self) -> None:
        for status in ("superseded", "withdrawn", "revoked"):
            with self.subTest(status=status):
                self.setUp()
                self.lesson()
                self.lesson(status=status)
                self.assertEqual(self.pin_reason(), "", status)


if __name__ == "__main__":
    unittest.main()
