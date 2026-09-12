"""A cited command either runs as written, or is refused by name.

Incident 12606. A `cmd:` citation is split into argv and executed with no
shell, so `&&`, `|`, `>` and friends become literal arguments. Incident 12486
caught the half of that which fails loudly - a redirect makes the command exit
nonzero, and the claim quietly records at a weaker grade.

The dangerous half exits ZERO. `grep -q PRESENT file && grep -q ABSENT file`
returns 0, because `grep -q` succeeds on its first match and never evaluates
the second conjunct at all. The verifier then reports executed, passed, and
grades the claim `verified` - a false green produced by the mechanism whose
whole purpose is to prevent them.

So a citation carrying grammar the runner will not honour is refused at record
time, naming the token. Refusing is not a lesser outcome than running it: the
alternative is a check that reports on a command nobody ran.

A multi-condition check belongs in a script cited by path. That keeps the
runner's execution model as argv-with-no-shell, which is what makes it
auditable in the first place.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_attest import unsupported_shell_grammar  # noqa: E402


class GrammarTheRunnerWillNotHonour(unittest.TestCase):
    def test_an_and_chain_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("grep -q a f && grep -q b f"), "&&")

    def test_an_or_chain_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("a || b"), "||")

    def test_a_pipe_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("grep a f | wc -l"), "|")

    def test_a_redirect_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("grep -c a f > out.txt"), ">")

    def test_an_input_redirect_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("sort < in.txt"), "<")

    def test_a_semicolon_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("cd x; ls"), ";")

    def test_a_command_substitution_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("test $(wc -l < f) -le 4"), "$(")

    def test_a_backtick_substitution_is_refused(self) -> None:
        self.assertEqual(unsupported_shell_grammar("test `wc -l f` -gt 0"), "`")


class OrdinaryCommandsAreNotRefused(unittest.TestCase):
    def test_a_plain_command_passes(self) -> None:
        self.assertIsNone(unsupported_shell_grammar("pytest -q tests/test_a.py"))

    def test_an_operator_inside_a_quoted_argument_is_not_grammar(self) -> None:
        """`grep -q 'a && b' file` searches for the text, it does not chain."""
        self.assertIsNone(unsupported_shell_grammar("grep -q 'a && b' file.txt"))

    def test_a_redirect_character_inside_a_quoted_pattern_is_not_grammar(self) -> None:
        self.assertIsNone(unsupported_shell_grammar("grep -q 'exit NR>4' file.txt"))

    def test_a_flag_that_merely_contains_an_operator_character_is_fine(self) -> None:
        self.assertIsNone(unsupported_shell_grammar("python -m unittest tests.test_a"))

    def test_a_windows_path_is_not_grammar(self) -> None:
        self.assertIsNone(
            unsupported_shell_grammar(r"python C:\Users\dev\project\run.py --fast"))


class TheRefusalIsActionable(unittest.TestCase):
    def test_the_returned_token_is_the_one_to_remove(self) -> None:
        """A refusal saying "unsupported syntax" cannot be acted on."""
        for text, token in (("a && b", "&&"), ("a | b", "|"), ("a > b", ">")):
            with self.subTest(text=text):
                self.assertEqual(unsupported_shell_grammar(text), token)

    def test_the_first_offending_token_is_reported(self) -> None:
        """Reporting one at a time keeps the message short and the fix obvious."""
        self.assertIn(unsupported_shell_grammar("a | b && c"), {"|", "&&"})


if __name__ == "__main__":
    unittest.main()
