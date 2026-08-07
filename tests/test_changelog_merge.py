"""Merging a version twice must not produce that version twice.

A release is rarely cut in one pass. A fragment arrives after the first merge —
because a gate caught something, which is the system working — and the second
merge inserted a second `## [0.2.3]` heading above the first rather than
folding into it. The duplicate shipped in a tagged release with 464 tests, all
thirteen gates, `changelog check` and the document linter reporting green,
because nothing had ever asked whether a version appears once.

The changelog is the record a reader trusts to say what shipped when. Two
sections for one version make that record ambiguous about its own subject.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_changelog import merge_fragments  # noqa: E402


def _project():
    holder = tempfile.TemporaryDirectory(prefix="godmode-changelog-")
    root = Path(holder.name)
    (root / "changelog.d").mkdir()
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n\n"
        "### Added\n\n- the first thing\n", encoding="utf-8")
    return holder, root


def _fragment(root: Path, name: str, text: str) -> None:
    (root / "changelog.d" / name).write_text(text, encoding="utf-8")


def _headings(root: Path) -> list[str]:
    body = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.findall(r"^## \[([^\]]+)\]", body, flags=re.MULTILINE)


class RepeatedMergeTests(unittest.TestCase):
    def test_a_second_merge_folds_into_the_existing_section(self) -> None:
        holder, root = _project()
        with holder:
            _fragment(root, "one.added.md", "the first capability")
            merge_fragments(root, "0.2.3", "2026-08-08")
            _fragment(root, "two.fixed.md", "the late arrival")
            merge_fragments(root, "0.2.3", "2026-08-08")
            headings = _headings(root)
            body = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(headings.count("0.2.3"), 1, headings)
        self.assertIn("the first capability", body)
        self.assertIn("the late arrival", body)

    def test_entries_from_both_merges_sit_under_their_own_categories(self) -> None:
        holder, root = _project()
        with holder:
            _fragment(root, "one.added.md", "an added thing")
            merge_fragments(root, "0.2.3", "2026-08-08")
            _fragment(root, "two.fixed.md", "a fixed thing")
            merge_fragments(root, "0.2.3", "2026-08-08")
            body = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        section = body.split("## [0.2.3]", 1)[1].split("## [0.1.0]", 1)[0]
        self.assertIn("### Added", section)
        self.assertIn("### Fixed", section)
        self.assertLess(section.index("an added thing"), section.index("a fixed thing"))

    def test_a_second_merge_into_the_same_category_keeps_both_entries(self) -> None:
        holder, root = _project()
        with holder:
            _fragment(root, "one.added.md", "the earlier entry")
            merge_fragments(root, "0.2.3", "2026-08-08")
            _fragment(root, "two.added.md", "the later entry")
            merge_fragments(root, "0.2.3", "2026-08-08")
            body = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        # Scoped to the section: earlier releases carry their own `### Added`,
        # so counting across the file measures the fixture, not the merge.
        section = body.split("## [0.2.3]", 1)[1].split("## [0.1.0]", 1)[0]
        self.assertEqual(section.count("### Added"), 1, section)
        self.assertIn("the earlier entry", section)
        self.assertIn("the later entry", section)

    def test_earlier_releases_are_untouched(self) -> None:
        holder, root = _project()
        with holder:
            _fragment(root, "one.added.md", "something")
            merge_fragments(root, "0.2.3", "2026-08-08")
            _fragment(root, "two.added.md", "something else")
            merge_fragments(root, "0.2.3", "2026-08-08")
            headings = _headings(root)
            body = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(headings, ["Unreleased", "0.2.3", "0.1.0"], headings)
        self.assertIn("the first thing", body)


class ShippedChangelogTests(unittest.TestCase):
    """The repository's own changelog, which carried the duplicate."""

    def test_no_version_appears_twice(self) -> None:
        body = (PLUGIN_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## \[([^\]]+)\]", body, flags=re.MULTILINE)
        duplicates = sorted({h for h in headings if headings.count(h) > 1})
        self.assertEqual(duplicates, [], f"a version appears more than once: {duplicates}")


if __name__ == "__main__":
    unittest.main()
