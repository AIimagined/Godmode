"""Segment-aware tokenization: argument text can never convict a command.

The seed defects were both real denials: a JS `>>>`/`=>` operator inside a
quoted `node -e` script read as an empty-target shell redirect, and the bare
word "release" inside an unquoted file path (`docs/RELEASE-CHECKLIST.md`)
read as the release verb. Both are the same class of mistake - a vocabulary
check searching the whole line instead of the command's own words - so both
are fixed the same way: `split_segments` tokenizes each part of a compound
command, excluding quoted text from `tokens` entirely, and `classify_action`
restricts its vocabulary matching to command-position text built from those
tokens rather than the raw line.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action, split_segments  # noqa: E402


class Segments(unittest.TestCase):
    def test_pipeline_splits_and_strips_quotes(self) -> None:
        segs = split_segments(
            'grep -o "^export \\(function\\|const\\)" src/a.ts | sort -u')
        self.assertEqual([s.head for s in segs], ["grep", "sort"])
        self.assertNotIn("export", segs[0].tokens)  # quoted arg text never enters matching

    def test_heredoc_body_stripped(self) -> None:
        segs = split_segments("git commit -F - <<'EOF'\nfeat: drop table users\nEOF")
        self.assertEqual(segs[0].head, "git")
        self.assertNotIn("drop", [t for s in segs for t in s.tokens])

    def test_redirect_flags_segment(self) -> None:
        segs = split_segments("sort a.txt > out.txt")
        self.assertTrue(segs[0].has_redirect)

    def test_a_read_only_segment_has_no_redirect(self) -> None:
        segs = split_segments("cat README.md")
        self.assertFalse(segs[0].has_redirect)

    def test_a_redirect_operator_only_inside_quotes_is_not_flagged(self) -> None:
        segs = split_segments('node -e "console.log(1 >>> 2)"')
        self.assertFalse(segs[0].has_redirect)

    def test_subcommand_is_the_first_non_flag_non_path_word(self) -> None:
        segs = split_segments("git commit --amend")
        self.assertEqual(segs[0].subcommand, "commit")

    def test_a_bare_positional_path_is_not_read_as_a_subcommand(self) -> None:
        segs = split_segments("tail docs/RELEASE-CHECKLIST.md")
        self.assertEqual(segs[0].head, "tail")
        self.assertIsNone(segs[0].subcommand)

    def test_the_head_is_kept_even_when_it_is_a_relative_path(self) -> None:
        segs = split_segments("./scripts/deploy.sh --dry-run")
        self.assertEqual(segs[0].head, "./scripts/deploy.sh")


class QuotedWordsNeverClassify(unittest.TestCase):
    def test_grep_pattern_with_mutation_words_is_r0(self) -> None:
        self.assertEqual(classify_action('grep "drop table" src/db.py')["tier"], "R0")

    def test_real_mutation_still_caught(self) -> None:
        tiers = ["R0", "R1", "R2", "R3", "R4", "R5"]
        verdict = classify_action("rm -rf build")
        self.assertGreaterEqual(tiers.index(verdict["tier"]), tiers.index("R4"))  # green control


class ArgumentPathsNeverConvict(unittest.TestCase):
    """The FP1 defect this task exists to fix: a bare filename argument
    containing a vocabulary word - not a quoted one - misread as the verb."""

    def test_a_release_checklist_filename_is_not_a_release(self) -> None:
        verdict = classify_action("tail docs/RELEASE-CHECKLIST.md")
        self.assertFalse(verdict["protected"])
        self.assertEqual(verdict["tier"], "R0")

    def test_a_real_release_command_is_still_protected(self) -> None:
        verdict = classify_action("npm run release")
        self.assertTrue(verdict["protected"])


class QuotedOperatorsNeverReadAsRedirects(unittest.TestCase):
    """The other FP1 defect: a JS `=>`/`>>>` or a `<tag>` inside a quoted
    argument misread as an unclosed, empty-target shell redirect."""

    def test_an_arrow_function_inside_a_node_dash_e_script_is_not_a_redirect(self) -> None:
        verdict = classify_action('node -e "const f = l=>l.trim()"')
        self.assertFalse(verdict["protected"])

    def test_a_bitshift_inside_a_node_dash_e_script_is_not_a_redirect(self) -> None:
        verdict = classify_action('node -e "console.log(1 >>> 2)"')
        self.assertFalse(verdict["protected"])

    def test_a_real_redirect_outside_the_tree_is_still_protected(self) -> None:
        verdict = classify_action("cat notes.txt >> /etc/hosts")
        self.assertTrue(verdict["protected"])


if __name__ == "__main__":
    unittest.main()
