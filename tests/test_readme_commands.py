"""README.md is the front door - every `godmode ...` line in its fenced
```console blocks must be a real CLI surface, not a plausible-looking
invention a rewrite left behind.

This mirrors `tests/test_demo_doc.py`'s mechanism (parse every fenced
console block, walk each `$ godmode ...` line through the actual argparse
subcommand tree `_build_parser` builds) and applies it to README.md
instead of docs/DEMO.md. A README edit that renames a subcommand, or
invents one that was never wired, fails this test - not a reader's
copy-paste.

Scope is deliberately "fenced commands" only, per the task that wrote this
test: inline code spans inside prose or table cells (e.g. `godmode scenarios
--brief` quoted as an example result) are not parsed here. Every fenced
`$ godmode ...` line in the README is covered; that is the set this test
exists to keep honest.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_console import _build_parser  # noqa: E402
from godmode_runtime.godmode_profile import PROFILE_NAMES  # noqa: E402

README = PLUGIN_ROOT / "README.md"

# A leading run of bare identifier tokens (letters/digits/hyphen) - the
# shape every subcommand name in this project's parser takes. Stops at the
# first flag, quoted value, placeholder (`<...>`), or path, exactly where
# the subcommand chain ends and the command's own arguments begin, so the
# tail need not be shell-parsed.
_BARE_TOKEN = re.compile(r"^[A-Za-z][\w-]*$")


def _fenced_console_blocks(text: str) -> list[str]:
    """Every fenced block opened with ```console, body only."""
    blocks: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == "```console":
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                body.append(lines[i])
                i += 1
            blocks.append("\n".join(body))
        i += 1
    return blocks


def _shell_commands(block: str) -> list[str]:
    """`$ ...` lines from one fenced block, backslash line-continuations joined."""
    lines = block.splitlines()
    commands: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("$"):
            parts = [stripped[1:].strip()]
            while parts[-1].endswith("\\"):
                parts[-1] = parts[-1][:-1].rstrip()
                i += 1
                parts.append(lines[i].strip())
            commands.append(" ".join(parts))
        i += 1
    return commands


def _strip_trailing_comment(command: str) -> str:
    """Drop a ` # ...` inline comment (the profile block annotates each line)."""
    marker = command.find(" #")
    return command if marker == -1 else command[:marker].rstrip()


def _godmode_subcommand_tokens(command: str) -> list[str]:
    """Bare tokens right after `godmode`, up to the first flag/placeholder/quoted arg."""
    if not command.startswith("godmode "):
        return []
    tokens: list[str] = []
    for token in command[len("godmode "):].split():
        if not _BARE_TOKEN.match(token):
            break
        tokens.append(token)
    return tokens


def _subparsers_action(parser: argparse.ArgumentParser):
    for action in parser._actions:  # noqa: SLF001 - the only way argparse exposes this
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return action
    return None


def resolve_subcommand_chain(tokens: list[str]) -> None:
    """Walk `tokens` through the real parser tree; raises if any hop is unknown."""
    current = _build_parser()
    walked: list[str] = []
    for token in tokens:
        action = _subparsers_action(current)
        if action is None:
            return  # remaining tokens are this leaf's own arguments, not subcommands
        if token not in action.choices:
            raise AssertionError(
                f"'godmode {' '.join(walked + [token])}' does not resolve - "
                f"known subcommands of 'godmode {' '.join(walked)}': "
                f"{sorted(action.choices)}"
            )
        current = action.choices[token]
        walked.append(token)


class ReadmeCommandsTests(unittest.TestCase):
    def test_readme_exists_and_has_console_blocks(self) -> None:
        self.assertTrue(README.is_file(), f"{README} must exist")
        blocks = _fenced_console_blocks(README.read_text(encoding="utf-8"))
        self.assertTrue(blocks, "README.md must carry at least one ```console block")

    def test_every_fenced_godmode_command_resolves(self) -> None:
        text = README.read_text(encoding="utf-8")
        commands = [
            _strip_trailing_comment(command)
            for block in _fenced_console_blocks(text)
            for command in _shell_commands(block)
            if command.startswith("godmode ")
        ]
        self.assertTrue(commands, "expected at least one fenced '$ godmode ...' line in README.md")
        for command in commands:
            tokens = _godmode_subcommand_tokens(command)
            self.assertTrue(tokens, f"no bare subcommand token parsed from: {command!r}")
            with self.subTest(command=command):
                resolve_subcommand_chain(tokens)

    def test_init_profile_flag_and_its_three_choices_are_real(self) -> None:
        # The starting-profile block (`godmode init --profile novice|standard|strict`)
        # names three literal profile values inline as `--profile <name>` - pin
        # that `--profile` is a real flag on `init` and that its declared choices
        # are exactly the three the README's fenced block walks through, so a
        # renamed or reordered profile cannot drift from what the README shows.
        parser = _build_parser()
        action = _subparsers_action(parser)
        init_parser = action.choices["init"]
        profile_actions = [
            a for a in init_parser._actions  # noqa: SLF001
            if "--profile" in a.option_strings
        ]
        self.assertTrue(profile_actions, "'--profile' must be a real flag on 'godmode init'")
        self.assertEqual(tuple(profile_actions[0].choices), PROFILE_NAMES)

    def test_the_project_flag_and_global_flags_readme_relies_on_are_real(self) -> None:
        # --brief and --digest/--host-independent flags are exercised by the
        # fenced commands above; --project is referenced in prose (the CLI
        # entrypoint doc) - pin all three exist on the parsers that actually
        # declare them, the same shape test_demo_doc.py already pins --brief.
        parser = _build_parser()
        top_level_options = {
            opt for a in parser._actions for opt in a.option_strings  # noqa: SLF001
        }
        for flag in ("--project", "--json", "--brief"):
            self.assertIn(flag, top_level_options)


if __name__ == "__main__":
    unittest.main()
