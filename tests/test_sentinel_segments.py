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


# ---------------------------------------------------------------------------
# Review round 1 - three findings, all fixed through the Segment interface
# itself, not just through classify_action, so a Task 3/4 consumer building a
# new check on Segment gets the fix for free rather than having to rediscover
# it.
# ---------------------------------------------------------------------------


class VocabTokensExcludePathArguments(unittest.TestCase):
    """Finding 1: `Segment.tokens` alone does not carry the command-position
    guarantee - `Segment.vocab_tokens` is the field a new bare-word check
    must use. Exercised through the Segment interface directly, not only
    through classify_action, so the trap (a future check built on `tokens`)
    can't reopen unnoticed."""

    def test_tokens_keeps_the_path_argument_vocab_tokens_does_not(self) -> None:
        # The review's own reproduction: `tokens` is the complete,
        # unfiltered word list (a consumer that needs the real argument -
        # protected-path-read, for one - still has it); `vocab_tokens` is
        # the narrower, purpose-built list a bare-word pattern may trust.
        segment = split_segments("grep -n release docs/RELEASE-CHECKLIST.md")[0]
        self.assertIn("docs/RELEASE-CHECKLIST.md", segment.tokens)
        self.assertNotIn("docs/RELEASE-CHECKLIST.md", segment.vocab_tokens)

    def test_a_bare_word_matched_only_inside_a_path_is_absent_from_vocab_tokens(self) -> None:
        # Unlike the case above, "release" here never appears as its own
        # word - only embedded in the filename - so a check built against
        # `vocab_tokens` joined back into text can never find it.
        segment = split_segments("tail docs/RELEASE-CHECKLIST.md")[0]
        joined = " ".join(segment.vocab_tokens)
        self.assertNotRegex(joined, r"\brelease\b")

    def test_a_genuine_bare_word_argument_stays_in_vocab_tokens(self) -> None:
        # `vocab_tokens` excludes path-SHAPED arguments, not every argument -
        # a real unquoted word (here, grep's own search pattern) is not
        # itself a path and is not excluded.
        segment = split_segments("grep -n release notes.md")[0]
        self.assertIn("release", segment.vocab_tokens)


class EscapedQuotesNeverEndAQuotedSpanEarly(unittest.TestCase):
    """Finding 2 (pre-existing, not introduced by Task 2, but shipped as
    part of this task's own interface): `_executable_text`'s quote-blanking
    now shares `_raw_segments`'s escape rule, so an escaped quote inside a
    double-quoted string can't prematurely end the quoted span and leak a
    vocabulary word into matching."""

    def test_an_escaped_quote_inside_a_quoted_argument_is_r0(self) -> None:
        verdict = classify_action('grep "he said \\"drop table users\\"" file.txt')
        self.assertEqual(verdict["tier"], "R0")
        self.assertFalse(verdict["protected"])

    def test_a_real_quoted_sql_statement_still_stays_protected(self) -> None:
        # Green control: the escape fix must not make a genuine dangerous
        # statement invisible just because it is quoted. Tier is R3, not
        # R5 - the quoted verb is blanked before the SQL-specific pattern
        # runs (a pre-existing, separately-tracked limitation, not this
        # finding's concern) - but it must still be protected.
        verdict = classify_action('psql -c "drop table users"')
        self.assertTrue(verdict["protected"])


class RedirectTargetIsReadFromTheConfirmedOperatorPosition(unittest.TestCase):
    """Finding 3 (pre-existing, not introduced by Task 2, but shipped as
    part of this task's own interface): the redirect target is read from
    `Segment.redirect_target`, located at the position the quote-aware scan
    confirmed as the real operator - never by re-searching the raw text from
    its start, where an earlier quoted `>` would be found first."""

    def test_a_quoted_arrow_before_a_real_redirect_still_finds_the_real_target(self) -> None:
        segment = split_segments('echo "a > b" > /etc/hosts')[0]
        self.assertTrue(segment.has_redirect)
        self.assertEqual(segment.redirect_target, "/etc/hosts")

    def test_the_demonstrated_write_is_classified_as_a_write_outside_the_tree(self) -> None:
        verdict = classify_action('echo "a > b" > /etc/hosts')
        self.assertEqual(verdict["category"], "worktree-file-mutation")
        self.assertTrue(verdict["protected"])

    def test_no_real_redirect_means_no_redirect_target_at_all(self) -> None:
        # Green control: a `>` that only ever appears inside quotes must
        # not be flagged, let alone yield a target.
        segment = split_segments('echo "a > b"')[0]
        self.assertFalse(segment.has_redirect)
        self.assertIsNone(segment.redirect_target)
        verdict = classify_action('echo "a > b"')
        self.assertFalse(verdict["protected"])


if __name__ == "__main__":
    unittest.main()
