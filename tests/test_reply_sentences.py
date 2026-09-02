"""The reply splitter must not manufacture claims out of typography.

Field-observed 2026-09-01, twice in one day: `.split(".")` chopped
"15 commits of 0.3.9" into the fragment "15 commits of 0" (a version
number is not a sentence boundary), and a markdown table row full of
bold markers and separators was flagged as a claim-shaped sentence. A
nag that quotes garbage teaches dismissal - the splitter now breaks
only at a terminator followed by whitespace or end, skips table rows,
and skips sentences quoting godmode's own nag text.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "hooks", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_session_hook import _reply_sentences  # noqa: E402


class ReplySentenceTests(unittest.TestCase):
    def test_version_numbers_do_not_split(self) -> None:
        sentences = _reply_sentences("Unpushed total now: 15 commits of 0.3.9 material. Next push needs a password.")
        self.assertIn("Unpushed total now: 15 commits of 0.3.9 material", sentences)
        self.assertNotIn("Unpushed total now: 15 commits of 0", sentences)

    def test_table_rows_are_skipped(self) -> None:
        sentences = _reply_sentences("| suite | 3702 passed | 2 skipped |\nOrdinary prose sentence stays here.")
        self.assertEqual(sentences, ["Ordinary prose sentence stays here"])

    def test_self_quoting_nag_text_is_skipped(self) -> None:
        sentences = _reply_sentences(
            "The godmode claim nags fired on statements already backed by docs.")
        self.assertEqual(sentences, [])

    def test_question_and_exclamation_still_split(self) -> None:
        sentences = _reply_sentences("The parser handles comments now! Does the lexer keep up? Both are covered.")
        self.assertEqual(len(sentences), 3)


if __name__ == "__main__":
    unittest.main()


class SeparatorTableTests(unittest.TestCase):
    def test_dot_separator_status_lines_are_layout(self) -> None:
        # Field report #4: "tsc 0 · suite 3706 pass · parity 97/97" is a
        # status table drawn with middle dots, not prose - two or more
        # separators mean layout, same as a pipe row.
        sentences = _reply_sentences(
            "Gates green: tsc 0 · suite 3706 pass · parity 97/97.\n"
            "The build finished cleanly after the fix.")
        self.assertEqual(sentences, ["The build finished cleanly after the fix"])


class HeadingAndQuoteTests(unittest.TestCase):
    def test_markdown_headings_are_labels_not_claims(self) -> None:
        # Field report 8: '## What upstream shipped and where it lands'
        # is a section title; "shipped" in a heading must not arm the gate.
        sentences = _reply_sentences(
            "## What upstream shipped and where it lands for us\n"
            "The build finished cleanly after the fix.")
        self.assertEqual(sentences, ["The build finished cleanly after the fix"])

    def test_quoted_completion_vocab_is_not_a_claim(self) -> None:
        # The quoted-vocab false positive (threshold met): an agent that
        # confidently declared "fixed" is a hypothetical, not this
        # session's claim.
        sentences = _reply_sentences(
            'An agent that confidently declared "fixed" and was wrong '
            'burned trust badly there.')
        self.assertEqual(len(sentences), 1)
        import sys as _s
        hooks_dir = str(Path(__file__).resolve().parents[1] / "hooks")
        if hooks_dir not in _s.path:
            _s.path.insert(0, hooks_dir)
        from godmode_session_hook import _strip_quoted
        self.assertNotIn("fixed", _strip_quoted(sentences[0]))


class AsciiEchoTests(unittest.TestCase):
    """Echoed claim text crosses a host codepage godmode does not control.

    Field-observed 2026-09-02: a Windows terminal rendered a reply's section
    sign and em dash as mojibake inside the gate's echo. The echo is now
    flattened to ASCII with readable stand-ins; the record keeps the original.
    """

    def test_typography_gets_readable_stand_ins(self) -> None:
        from godmode_session_hook import _ascii_echo
        flattened = _ascii_echo("The §6a read settles it — E-17 done…")
        self.assertEqual(flattened, "The S.6a read settles it  -  E-17 done...")

    def test_everything_else_survives_ascii(self) -> None:
        from godmode_session_hook import _ascii_echo
        flattened = _ascii_echo("café résumé 中文")
        self.assertTrue(flattened.isascii())
        self.assertIn("caf", flattened)


class FenceAndConditionalTests(unittest.TestCase):
    """Self-observed 2026-09-02: the gate flagged a shell one-liner shown in
    a code fence and a conditional advice sentence as completion claims."""

    def test_fenced_code_is_shown_not_stated(self) -> None:
        reply = ("Run this:\n```\nfor c in 1 2 3; do echo done; done. All "
                 "tests pass here.\n```\nThen pick a number.")
        sentences = _reply_sentences(reply)
        self.assertFalse(any("tests pass" in s for s in sentences), sentences)
        self.assertTrue(any("pick a number" in s for s in sentences))

    def test_unclosed_fence_swallows_to_end(self) -> None:
        sentences = _reply_sentences("```\nthe fix is complete and shipped.")
        self.assertEqual(sentences, [])

    def test_conditional_advice_is_not_a_done_claim(self) -> None:
        import godmode_session_hook as hook

        class _Archive:
            def read_events(self, **kwargs):
                return []
            def select(self, **kwargs):
                return []

        found = hook._unrecorded_done_claims(
            _Archive(),
            "If you'd rather have one fixed color always, that works too.")
        self.assertEqual(found, [])


class AdjectivalFixedTests(unittest.TestCase):
    """Self-observed 2026-09-02: "one fixed color always" armed the gate -
    "fixed" after a determiner is a property, not a repair event."""

    def test_determiner_fixed_is_a_property(self) -> None:
        from godmode_runtime.godmode_attest import looks_like_fix_claim
        for phrase in ("sets one fixed color for every grade",
                       "uses a fixed width layout",
                       "the fixed color survives restarts"):
            self.assertFalse(looks_like_fix_claim(phrase)[0], phrase)

    def test_verbal_fixed_still_matches(self) -> None:
        from godmode_runtime.godmode_attest import looks_like_fix_claim
        for phrase in ("I fixed the encoding bug",
                       "the bug is fixed now",
                       "commit 83eb0e3 fixed both defects"):
            self.assertTrue(looks_like_fix_claim(phrase)[0], phrase)
