"""A file may declare which of its regions a machine-authored edit may touch.

Enforced twice, and the second half is the point. A rule stated only in the
prompt is a rule the editor can argue itself out of: it sees the frozen text,
decides this case is different, and edits it. So the region is *withheld from
what the editor is shown* (this module) and *a patch outside it is refused*
(the containment half, tested here too).

Markers nest. A pairwise scan that assumes start/end alternate is wrong the
first time someone nests a region inside another, and someone will - so ranges
resolve with a stack over position-sorted markers.

Markers are recognised behind the comment syntaxes a mixed repository actually
uses, because a marker that only works in Python is a marker that silently does
nothing in the YAML file next to it - failing open, which is the wrong
direction for a guard.
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


class Ranges(unittest.TestCase):
    def test_a_file_with_no_markers_has_no_mutable_range(self) -> None:
        """Absent markers mean nothing is declared editable, not everything."""
        self.assertEqual(R.mutable_ranges("a = 1\nb = 2\n"), [])

    def test_one_region_is_the_text_between_its_markers(self) -> None:
        text = f"head\n# {START}\nbody\n# {END}\ntail\n"
        ranges = R.mutable_ranges(text)
        self.assertEqual(len(ranges), 1)
        start, end = ranges[0]
        self.assertIn("body", text[start:end])
        self.assertNotIn("head", text[start:end])
        self.assertNotIn("tail", text[start:end])

    def test_two_sequential_regions_are_two_ranges(self) -> None:
        text = (f"a\n# {START}\none\n# {END}\nb\n# {START}\ntwo\n# {END}\nc\n")
        ranges = R.mutable_ranges(text)
        self.assertEqual(len(ranges), 2, ranges)

    def test_nested_regions_resolve_with_a_stack(self) -> None:
        text = (f"# {START}\nouter\n# {START}\ninner\n# {END}\nmore\n# {END}\n")
        ranges = R.mutable_ranges(text)
        self.assertEqual(len(ranges), 2, ranges)
        widest = max(ranges, key=lambda r: r[1] - r[0])
        self.assertIn("inner", text[widest[0]:widest[1]])
        self.assertIn("more", text[widest[0]:widest[1]])

    def test_an_unclosed_start_yields_no_range(self) -> None:
        """Failing closed: an unterminated region is not 'editable to EOF'."""
        text = f"a\n# {START}\nbody\n"
        self.assertEqual(R.mutable_ranges(text), [])

    def test_an_unmatched_end_is_ignored(self) -> None:
        text = f"a\n# {END}\nbody\n"
        self.assertEqual(R.mutable_ranges(text), [])


class CommentSyntaxes(unittest.TestCase):
    def test_the_marker_is_recognised_behind_each_supported_prefix(self) -> None:
        for opener, closer in (("#", ""), ("//", ""), ("--", ""),
                               ("<!--", "-->"), ("/*", "*/"), (";", "")):
            with self.subTest(opener=opener):
                text = f"a\n{opener} {START} {closer}\nbody\n{opener} {END} {closer}\nb\n"
                ranges = R.mutable_ranges(text)
                self.assertEqual(len(ranges), 1, f"{opener!r} not recognised")
                self.assertIn("body", text[ranges[0][0]:ranges[0][1]])

    def test_a_bare_marker_with_no_comment_prefix_still_works(self) -> None:
        text = f"a\n{START}\nbody\n{END}\nb\n"
        self.assertEqual(len(R.mutable_ranges(text)), 1)


class Redaction(unittest.TestCase):
    def test_the_editor_view_contains_the_mutable_body(self) -> None:
        text = f"secret_head\n# {START}\nbody\n# {END}\nsecret_tail\n"
        view = R.redact_immutable(text)
        self.assertIn("body", view)

    def test_the_editor_view_hides_every_immutable_body(self) -> None:
        text = f"secret_head\n# {START}\nbody\n# {END}\nsecret_tail\n"
        view = R.redact_immutable(text)
        self.assertNotIn("secret_head", view)
        self.assertNotIn("secret_tail", view)

    def test_each_elision_is_marked_rather_than_silently_dropped(self) -> None:
        """A silent elision reads as a complete file and invites a rewrite."""
        text = f"head\n# {START}\nbody\n# {END}\ntail\n"
        view = R.redact_immutable(text)
        self.assertIn(R.ELISION, view)
        self.assertGreaterEqual(view.count(R.ELISION), 2)

    def test_a_file_with_no_markers_redacts_to_a_single_elision(self) -> None:
        view = R.redact_immutable("nothing declared editable\n")
        self.assertNotIn("nothing declared editable", view)
        self.assertIn(R.ELISION, view)

    def test_nested_regions_do_not_duplicate_the_inner_body(self) -> None:
        text = f"# {START}\nouter\n# {START}\ninner\n# {END}\n# {END}\n"
        view = R.redact_immutable(text)
        self.assertEqual(view.count("inner"), 1, view)


if __name__ == "__main__":
    unittest.main()
