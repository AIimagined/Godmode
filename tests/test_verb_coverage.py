"""Every CLI verb is named by a test, a public doc, and a skill or the command surface.

An unnamed verb ships untested and unfindable. The selftest fails on any
verb missing one of the three.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_selftest import _named_as_a_command, verb_coverage  # noqa: E402


class VerbCoverageTests(unittest.TestCase):
    def test_repo_has_no_orphan_verbs(self) -> None:
        report = verb_coverage(PLUGIN_ROOT)
        self.assertEqual(report["untested"], [], report)
        self.assertEqual(report["undocumented"], [], report)
        self.assertEqual(report["unrouted"], [], report)

    def test_seeded_orphan_is_named(self) -> None:
        # `alpha` is named the strict way (backticked); `beta` is bare prose
        # only - the exact shape the docs/skills rule refuses to count, so a
        # verb whose only mention is incidental English cannot pass as
        # documented or routed.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests").mkdir(); (root / "docs").mkdir(); (root / "skills").mkdir()
        (root / "README.md").write_text(
            "`alpha` does the thing. beta is only mentioned in passing prose.\n",
            encoding="utf-8",
        )
        report = verb_coverage(root, verbs=("alpha", "beta"))
        self.assertIn("beta", report["undocumented"])
        self.assertNotIn("alpha", report["undocumented"])
        self.assertIn("alpha", report["untested"])

    def test_a_root_named_like_the_excluded_segment_keeps_its_own_docs(self) -> None:
        # The exclusion is segment-scoped against the path relative to root:
        # a checkout sitting under a directory that happens to be named like
        # the excluded segment (docs/releases/) must not lose its own
        # top-level docs to a substring match on the wrong path. A
        # gitignored working-documents archive in this
        # project needs no such exclusion at all - it is never tracked, so
        # the tracked-files corpus never sees it in the first place.
        root = Path(tempfile.mkdtemp(prefix="sp-lab-releases-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests").mkdir(); (root / "docs").mkdir(); (root / "skills").mkdir()
        (root / "README.md").write_text("`alpha`\n", encoding="utf-8")
        report = verb_coverage(root, verbs=("alpha",))
        self.assertNotIn("alpha", report["undocumented"])


class NamedAsACommandTests(unittest.TestCase):
    """`_named_as_a_command` directly: the two shapes fix round 2 added."""

    def test_the_verb_may_be_the_first_token_in_a_longer_backticked_span(self) -> None:
        self.assertTrue(_named_as_a_command("docs", "run `docs --lint` before shipping"))
        self.assertTrue(
            _named_as_a_command("release-notes", "then `release-notes check` it")
        )

    def test_a_verb_that_is_not_the_first_token_still_does_not_count(self) -> None:
        # "release" is not the first token of "release-notes check" - a
        # verb appearing mid-span must not borrow a neighbor's mention.
        self.assertFalse(_named_as_a_command("release", "then `release-notes check` it"))

    def test_the_godmode_prefix_is_matched_case_insensitively(self) -> None:
        self.assertTrue(_named_as_a_command("alpha", "Run `Godmode alpha` first."))
        self.assertTrue(_named_as_a_command("alpha", "GODMODE alpha at a sentence start."))
        self.assertTrue(_named_as_a_command("alpha", "godmode alpha, the ordinary case."))


if __name__ == "__main__":
    unittest.main()
