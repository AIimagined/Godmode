"""A number in public prose that the runtime can count for itself.

The README badge reads 359 tests. The suite runs 527. `documentation_parity`
reports thirteen of thirteen triggers satisfied, because a badge is not a
tracked trigger, so a stale public numeric claim passed every gate this product
has — which is precisely the class of thing it exists to catch.

Only figures the runtime can compute are checked. A number it cannot count is
left alone rather than guessed at, because a checker that invents an expected
value teaches the reader to ignore it.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_docslint import lint_docs  # noqa: E402


def _project(**files: str) -> tempfile.TemporaryDirectory:
    holder = tempfile.TemporaryDirectory(prefix="godmode-figures-")
    root = Path(holder.name)
    tests = root / "tests"
    tests.mkdir()
    # Three real test functions, so "3 tests" is the truth here.
    (tests / "test_a.py").write_text(
        "def test_one():\n    pass\n\ndef test_two():\n    pass\n", encoding="utf-8")
    (tests / "test_b.py").write_text("def test_three():\n    pass\n", encoding="utf-8")
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return holder


def _codes(report: dict) -> list[str]:
    return [finding["check"] for finding in report["findings"]]


class BadgeTests(unittest.TestCase):
    def test_a_stale_badge_is_reported(self) -> None:
        with _project(**{"README.md": "![t](https://img.shields.io/badge/tests-99%20passing-green)\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("stale-figure", _codes(report))
        detail = " ".join(f["why"] for f in report["findings"])
        self.assertIn("99", detail)
        self.assertIn("3", detail)

    def test_an_accurate_badge_is_clean(self) -> None:
        with _project(**{"README.md": "![t](https://img.shields.io/badge/tests-3%20passing-green)\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("stale-figure", _codes(report))


class ProseTests(unittest.TestCase):
    def test_a_stale_figure_in_a_sentence_is_reported(self) -> None:
        with _project(**{"README.md": "The suite runs 42 tests on every commit.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("stale-figure", _codes(report))

    def test_the_true_figure_in_a_sentence_is_clean(self) -> None:
        with _project(**{"README.md": "The suite runs 3 tests on every commit.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("stale-figure", _codes(report))


class RestraintTests(unittest.TestCase):
    """A checker that invents an expected value teaches the reader to skip it."""

    def test_an_uncountable_number_is_left_alone(self) -> None:
        with _project(**{"README.md": "Used by 4000 developers. Saves 30 minutes a day.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("stale-figure", _codes(report))

    def test_a_number_inside_a_code_block_is_not_a_claim(self) -> None:
        body = "```\nRan 99 tests in 1s\n```\n"
        with _project(**{"README.md": body}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("stale-figure", _codes(report))

    def test_a_historical_record_states_what_was_true_then(self) -> None:
        """A changelog entry saying "464 tests" was accurate when written.
        Reporting every past release as wrong is the fastest way to teach a
        reader to ignore the check."""
        for name in ("CHANGELOG.md", "docs/releases/RELEASE_NOTES_v0.1.0.md"):
            with _project(**{name: "Shipped with 99 tests passing.\n"}) as raw:
                report = lint_docs(Path(raw))
            self.assertNotIn("stale-figure", _codes(report), name)

    def test_a_figure_with_no_exact_local_answer_is_not_checked(self) -> None:
        """`hosts` was tried and removed: the manifest lists three, the project
        also ships three adapters, and the checker called a true badge stale."""
        with _project(**{"README.md": "Supports 6 hosts today.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("stale-figure", _codes(report))

    def test_a_project_with_nothing_countable_reports_nothing(self) -> None:
        holder = tempfile.TemporaryDirectory(prefix="godmode-figures-")
        with holder:
            root = Path(holder.name)
            (root / "README.md").write_text("The suite runs 42 tests.\n", encoding="utf-8")
            report = lint_docs(root)
        self.assertNotIn("stale-figure", _codes(report))


class ThisRepositoryTests(unittest.TestCase):
    """The badge that motivated the check taught a second lesson.

    Correcting 359 to the true count made it stale again two commits later,
    because adding a test invalidates any document stating how many there are.
    The durable fix was the checker's own second remedy — stop stating a number
    that changes on every commit — so what is asserted here is that the
    self-invalidating claim is gone, not that a particular number is right.
    """

    def test_the_shipped_documents_state_no_stale_figure(self) -> None:
        stale = [f for f in lint_docs(PLUGIN_ROOT)["findings"]
                 if f["check"] == "stale-figure"]
        self.assertEqual(stale, [], f"a public document states a figure that is wrong: {stale}")

    def test_the_readme_does_not_state_an_exact_test_count(self) -> None:
        badges = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        import re

        self.assertIsNone(re.search(r"tests-\d+", badges),
                          "a badge stating an exact count goes stale on the next commit")


if __name__ == "__main__":
    unittest.main()
