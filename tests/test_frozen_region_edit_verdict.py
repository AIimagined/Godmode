"""The edit-boundary verdict that makes acceptance clause 11 real.

The region mechanism was built, tested, and wired to nothing. A complexity
review found it by asking which new modules had a production caller, and no
test could have: a library nobody calls has nothing to fail.

This is the verdict the pre-tool boundary asks. It answers in the shape the
fence and design boundaries beside it already use - allowed, detail, remedy -
so the hook gains a third check rather than a new pattern.

Three decisions, each with a reason that is not obvious:

Opt-in. A file that declares no region allows everything, because every
project predating this has no markers and none may start refusing edits
because the feature shipped.

A whole-file write is refused when regions exist. A write replaces the frozen
text along with everything else, and it carries no span to check, so treating
"no span" as "nothing to check" would make the guard trivially avoidable by
choosing the blunter tool.

A search string absent from the file is allowed through. That edit cannot
apply, the host will say so, and refusing it here would report a frozen-region
violation for an edit that was never going to touch anything.
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

GUARDED = f"FROZEN_HEAD\n# {START}\nEDITABLE_BODY\n# {END}\nFROZEN_TAIL\n"
UNGUARDED = "ordinary = 1\nnothing_declared = 2\n"


class OptIn(unittest.TestCase):
    def test_a_file_with_no_markers_allows_an_edit_anywhere(self) -> None:
        self.assertTrue(R.edit_verdict(UNGUARDED, "ordinary")["allowed"])

    def test_a_file_with_no_markers_allows_a_whole_file_write(self) -> None:
        self.assertTrue(R.edit_verdict(UNGUARDED, None)["allowed"])


class GuardedFiles(unittest.TestCase):
    def test_an_edit_inside_the_region_is_allowed(self) -> None:
        self.assertTrue(R.edit_verdict(GUARDED, "EDITABLE_BODY")["allowed"])

    def test_an_edit_in_the_frozen_head_is_refused(self) -> None:
        self.assertFalse(R.edit_verdict(GUARDED, "FROZEN_HEAD")["allowed"])

    def test_an_edit_in_the_frozen_tail_is_refused(self) -> None:
        self.assertFalse(R.edit_verdict(GUARDED, "FROZEN_TAIL")["allowed"])

    def test_a_whole_file_write_is_refused_when_regions_exist(self) -> None:
        """Otherwise the guard is avoided by choosing the blunter tool."""
        self.assertFalse(R.edit_verdict(GUARDED, None)["allowed"])

    def test_an_edit_straddling_the_boundary_is_refused(self) -> None:
        straddle = f"# {END}\nFROZEN_TAIL"
        self.assertFalse(R.edit_verdict(GUARDED, straddle)["allowed"])

    def test_a_search_string_absent_from_the_file_is_allowed(self) -> None:
        """It cannot apply; refusing it would report a violation that is not one."""
        self.assertTrue(R.edit_verdict(GUARDED, "NOT_IN_THIS_FILE")["allowed"])

    def test_every_occurrence_must_be_inside_not_merely_the_first(self) -> None:
        text = (f"# {START}\nTOKEN here\n# {END}\nTOKEN there\n")
        self.assertFalse(R.edit_verdict(text, "TOKEN")["allowed"])


class TheVerdictIsActionable(unittest.TestCase):
    def test_a_refusal_carries_a_detail_and_a_remedy(self) -> None:
        verdict = R.edit_verdict(GUARDED, "FROZEN_HEAD")
        self.assertTrue(verdict["detail"].strip())
        self.assertTrue(verdict["remedy"].strip())

    def test_the_remedy_names_the_marker_pair(self) -> None:
        verdict = R.edit_verdict(GUARDED, "FROZEN_HEAD")
        self.assertIn(R.MARKER_START_TEXT, verdict["remedy"])

    def test_the_whole_file_refusal_says_why_a_write_differs(self) -> None:
        verdict = R.edit_verdict(GUARDED, None)
        self.assertIn("whole", verdict["detail"].lower())


class ItMatchesTheNeighbouringBoundaryShape(unittest.TestCase):
    def test_every_verdict_has_the_same_keys(self) -> None:
        """The hook treats fence, design and this one alike."""
        for verdict in (R.edit_verdict(GUARDED, "EDITABLE_BODY"),
                        R.edit_verdict(GUARDED, "FROZEN_HEAD"),
                        R.edit_verdict(UNGUARDED, None)):
            self.assertEqual(set(verdict), {"allowed", "detail", "remedy"})



class TheBoundaryHelperIsWired(unittest.TestCase):
    """Clause 11 asks for a demonstration, not a library.

    The mechanism existed and was tested for a full sprint while nothing called
    it. These exercise the hook's own helper - the function the pre-tool
    boundary invokes - against a real file on disk and a real host payload
    shape, so a future edit that unwires it fails here.
    """

    def setUp(self) -> None:
        import tempfile

        HOOKS = PLUGIN_ROOT / "hooks"
        if str(HOOKS) not in sys.path:
            sys.path.insert(0, str(HOOKS))
        import godmode_session_hook as hook

        self.hook = hook
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, body: str) -> str:
        path = self.root / name
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        return str(path)

    def _verdict(self, target: str, old_string):
        payload = {"tool_input": {"file_path": target, "old_string": old_string}}
        if old_string is None:
            payload["tool_input"].pop("old_string")
        return self.hook._frozen_region_verdict(self.root, target, payload)

    def test_an_edit_into_frozen_text_is_refused_through_the_helper(self) -> None:
        target = self._write("guarded.py", GUARDED)
        self.assertFalse(self._verdict(target, "FROZEN_HEAD")["allowed"])

    def test_an_edit_inside_the_region_passes_through_the_helper(self) -> None:
        target = self._write("guarded.py", GUARDED)
        self.assertTrue(self._verdict(target, "EDITABLE_BODY")["allowed"])

    def test_a_file_with_no_markers_is_unaffected(self) -> None:
        """Nothing that worked before starts refusing because this shipped."""
        target = self._write("plain.py", UNGUARDED)
        self.assertTrue(self._verdict(target, "ordinary")["allowed"])

    def test_a_missing_target_fails_open(self) -> None:
        """A file the hook cannot read declares no region to protect."""
        missing = str(self.root / "does-not-exist.py")
        self.assertTrue(self._verdict(missing, "anything")["allowed"])

    def test_a_whole_file_write_over_a_guarded_file_is_refused(self) -> None:
        target = self._write("guarded.py", GUARDED)
        self.assertFalse(self._verdict(target, None)["allowed"])

    def test_a_relative_target_resolves_against_the_project_root(self) -> None:
        self._write("guarded.py", GUARDED)
        self.assertFalse(self._verdict("guarded.py", "FROZEN_HEAD")["allowed"])

if __name__ == "__main__":
    unittest.main()
