"""Gate and done-bar wording carries no jargon a reader outside the project would trip on."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_refusal_lint import lint_hook_strings, lint_text  # noqa: E402


class RefusalLintTests(unittest.TestCase):
    def test_shipped_hook_strings_pass(self) -> None:
        report = lint_hook_strings(PLUGIN_ROOT / "hooks")
        self.assertTrue(report["passed"], report["findings"])

    def test_bare_tier_code_is_flagged(self) -> None:
        self.assertTrue(lint_text("refused: R5 - stage it"))

    def test_named_tier_passes(self) -> None:
        self.assertEqual(lint_text("refused: R5 (history or remote) - stage it with `godmode authorize stage --from-last-refusal`"), [])

    def test_remedy_without_command_is_flagged(self) -> None:
        self.assertTrue(any("command" in f for f in lint_text("this needs a staged capability; stage it and retry")))

    def test_overlong_sentence_is_flagged(self) -> None:
        self.assertTrue(lint_text("a " * 130 + "."))

    def test_a_path_does_not_split_a_sentence(self) -> None:
        # A "." inside a path/filename is not a sentence terminator - the
        # length rule must see the whole sentence, not fragments either
        # side of `.claude` or `godmode.cmd`.
        long_sentence = (
            "refused: this call touches a path under .claude and another "
            "under bin/godmode.cmd and keeps going long enough on its own "
            "that it alone should trip the length rule without any help "
            "from a second short sentence tacked on after it, and then it "
            "keeps going a little further still to make entirely sure."
        )
        self.assertGreater(len(long_sentence), 240)
        findings = lint_text(long_sentence)
        self.assertTrue(any(f.startswith("sentence over 240 chars") for f in findings), findings)

    def test_an_fstring_refusal_with_a_bare_tier_placeholder_is_named(self) -> None:
        """The bug this round fixes: the old scanner only ever looked at
        bare `ast.Constant` nodes, so an f-string refusal's tier - inside
        a `{...}` placeholder, immediately closed by `)` - was invisible
        to it. `lint_hook_strings` must assemble the f-string and find it,
        naming the file and the line the f-string itself starts on."""
        with tempfile.TemporaryDirectory() as raw:
            hooks_dir = Path(raw) / "hooks"
            hooks_dir.mkdir()
            (hooks_dir / "godmode_session_hook.py").write_text(
                "def deny(preview):\n"
                "    return f\"refused: something ({preview['tier']})\"\n",
                encoding="utf-8",
            )
            report = lint_hook_strings(hooks_dir)
        self.assertFalse(report["passed"], report)
        self.assertTrue(any(
            f["file"] == "hooks/godmode_session_hook.py" and f["line"] == 2
            and "bare tier code" in f["finding"]
            for f in report["findings"]
        ), report["findings"])

    def test_no_scanned_file_does_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            hooks_dir = Path(raw) / "hooks"
            hooks_dir.mkdir()
            report = lint_hook_strings(hooks_dir)
        self.assertEqual(report["scanned"], 0)
        self.assertEqual(report["findings"], [])
        self.assertFalse(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
