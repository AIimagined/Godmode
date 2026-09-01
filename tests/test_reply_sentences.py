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
