"""A patch outside a declared editable region is refused.

The other half of the frozen-region guard. Redaction removes the temptation by
hiding the text; this removes the option by refusing the write. Either half
alone is defeatable: text can reach an editor through a second path it was not
redacted on, and an editor told only in prose that a region is frozen can talk
itself into editing it anyway.

Acceptance clause 11 asks that removing either half makes a test fail. That is
what `BothHalvesAreLoadBearing` asserts, on one fixture, with two independent
assertions that do not pass vicariously through each other.

Partial overlap is refusal rather than truncation. A patch that half-lands
produces a corrupted file, which is worse than a refused edit.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_mutableregions as R  # noqa: E402

START = R.MARKER_START_TEXT
END = R.MARKER_END_TEXT

#: head / editable body / tail, with a distinctive token in each part.
FIXTURE = f"FROZEN_HEAD\n# {START}\nEDITABLE_BODY\n# {END}\nFROZEN_TAIL\n"


def _span(text: str, token: str) -> tuple[int, int]:
    start = text.index(token)
    return start, start + len(token)


class Containment(unittest.TestCase):
    def test_a_patch_inside_the_region_is_allowed(self) -> None:
        start, end = _span(FIXTURE, "EDITABLE_BODY")
        R.check_patch(FIXTURE, start, end)  # must not raise

    def test_a_patch_in_the_frozen_head_is_refused(self) -> None:
        start, end = _span(FIXTURE, "FROZEN_HEAD")
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, start, end)

    def test_a_patch_in_the_frozen_tail_is_refused(self) -> None:
        start, end = _span(FIXTURE, "FROZEN_TAIL")
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, start, end)

    def test_a_patch_straddling_the_boundary_is_refused_not_trimmed(self) -> None:
        """Half-landing a patch corrupts the file; refusing it does not."""
        body_start, body_end = _span(FIXTURE, "EDITABLE_BODY")
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, body_start - 3, body_end)
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, body_start, body_end + 3)

    def test_a_patch_against_a_file_with_no_regions_is_refused(self) -> None:
        text = "nothing declared editable\n"
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(text, 0, 7)

    def test_an_inverted_span_is_refused(self) -> None:
        start, end = _span(FIXTURE, "EDITABLE_BODY")
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, end, start)


class TheRefusalSaysWhatItProtected(unittest.TestCase):
    def test_the_message_names_the_offsets_and_the_declared_regions(self) -> None:
        """A refusal that does not say what it protected cannot be acted on."""
        start, end = _span(FIXTURE, "FROZEN_HEAD")
        with self.assertRaises(R.FrozenRegionError) as caught:
            R.check_patch(FIXTURE, start, end)
        message = str(caught.exception)
        self.assertIn(str(start), message)
        self.assertIn("editable", message.lower())

    def test_a_file_with_no_regions_says_so_rather_than_naming_a_range(self) -> None:
        with self.assertRaises(R.FrozenRegionError) as caught:
            R.check_patch("x = 1\n", 0, 1)
        self.assertIn("no editable region", str(caught.exception).lower())


class BothHalvesAreLoadBearing(unittest.TestCase):
    """Acceptance clause 11, on one fixture, two independent assertions."""

    def test_half_one_the_frozen_text_is_absent_from_the_editor_view(self) -> None:
        view = R.redact_immutable(FIXTURE)
        self.assertNotIn("FROZEN_HEAD", view)
        self.assertNotIn("FROZEN_TAIL", view)
        self.assertIn("EDITABLE_BODY", view)

    def test_half_two_a_write_into_that_text_is_refused_even_when_seen(self) -> None:
        """Independent of redaction: the span is taken from the real file."""
        start, end = _span(FIXTURE, "FROZEN_HEAD")
        with self.assertRaises(R.FrozenRegionError):
            R.check_patch(FIXTURE, start, end)


if __name__ == "__main__":
    unittest.main()
