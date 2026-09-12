"""A constraint credited to an outside authority is read before it is changed.

R17, the correction-side twin of R11. R11 governs what a source may fund; this
governs what a source may authorise overwriting.

The failure it guards is specific and common: a comment says a value is what it
is because some outside authority requires it, an agent judges the value wrong
on the code's own terms, and changes it. The deviation may have been
deliberate, and the agent is the party least able to tell - it can read the
code and usually has not read the authority.

So this does not decide correctness. It fires at the moment of the edit and
says: this line credits an outside authority, so read that authority before
changing what it says. An advisory, not a refusal, because the line may well be
wrong and the tool cannot know.

Precision matters more than reach here. A line that merely mentions a
specification is documentation; the finding requires an attribution phrase and
a constraint in the same line, because that pairing is what makes the value
someone else's to change.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_attribution import attributed_constraints  # noqa: E402


def checks(text: str) -> list[dict]:
    return attributed_constraints("sample.py", text)


class AttributionPlusConstraintFires(unittest.TestCase):
    def test_a_value_credited_to_a_specification(self) -> None:
        text = "# per RFC 7231 the timeout must be 30 seconds\nTIMEOUT = 30\n"
        self.assertTrue(checks(text))

    def test_a_value_credited_to_upstream_documentation(self) -> None:
        text = "# the vendor docs require a 1024 byte ceiling\nCEILING = 1024\n"
        self.assertTrue(checks(text))

    def test_according_to_with_a_limit(self) -> None:
        text = "# according to the platform manual the maximum is 8\nMAX = 8\n"
        self.assertTrue(checks(text))

    def test_upstream_requires_phrasing(self) -> None:
        text = "// upstream requires this field to stay lowercase\n"
        self.assertTrue(checks(text))

    def test_the_finding_names_the_line_and_carries_a_remedy(self) -> None:
        found = checks("# per RFC 7231 the timeout must be 30 seconds\n")
        self.assertEqual(found[0]["line"], 1)
        self.assertTrue(found[0]["remedy"])
        self.assertEqual(found[0]["check"], "attributed-constraint")


class AttributionWithoutAConstraintIsDocumentation(unittest.TestCase):
    def test_a_bare_reference_to_a_specification_does_not_fire(self) -> None:
        self.assertEqual(checks("# see RFC 7231 for background on caching\n"), [])

    def test_a_link_alone_does_not_fire(self) -> None:
        self.assertEqual(checks("# https://example.org/guide explains the model\n"), [])

    def test_an_ordinary_constraint_with_no_attribution_does_not_fire(self) -> None:
        """Our own rule, our own to change."""
        self.assertEqual(checks("# the timeout must be 30 seconds\nTIMEOUT = 30\n"), [])

    def test_ordinary_prose_does_not_fire(self) -> None:
        self.assertEqual(checks("# parse the timestamp and return it\n"), [])

    def test_the_word_per_in_ordinary_use_does_not_fire(self) -> None:
        """`per file` and `per session` are not attributions."""
        self.assertEqual(checks("# one advisory per file per session\n"), [])


class OnlyCommentsAndProseAreConsidered(unittest.TestCase):
    def test_a_python_comment_is_considered(self) -> None:
        self.assertTrue(checks("# per RFC 5322 the address must be quoted\n"))

    def test_a_markdown_line_is_considered(self) -> None:
        found = attributed_constraints(
            "notes.md", "The API docs require a maximum of 100 items per page.\n")
        self.assertTrue(found)


class TheRepositoryScansWithoutNoise(unittest.TestCase):
    def test_this_projects_own_runtime_produces_few_findings(self) -> None:
        """A detector that fires everywhere is one nobody leaves on.

        This asserts a ceiling rather than zero: some of this codebase really
        does credit outside authorities, and those are true positives.
        """
        runtime = PLUGIN_ROOT / "scripts" / "godmode_runtime"
        total = 0
        for path in sorted(runtime.rglob("*.py")):
            total += len(attributed_constraints(
                path.name, path.read_text(encoding="utf-8", errors="replace")))
        self.assertLess(total, 40, f"{total} findings across the runtime is noise")


if __name__ == "__main__":
    unittest.main()
