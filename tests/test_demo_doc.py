"""docs/DEMO.md is a script, not a slide - every command it shows must be a
real CLI surface, not a plausible-looking invention.

This pins that mechanically rather than by review: parse every fenced
`console` block in the doc for `$ godmode ...` lines, and walk each one
through the actual argparse subcommand tree (`_build_parser`), the same
tree `godmode <sub> --help` resolves against. A doc edit that renames a
subcommand, or invents one that was never wired, fails this test - not a
reader's transcript.
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

DEMO_DOC = PLUGIN_ROOT / "docs" / "DEMO.md"

# A leading run of bare identifier tokens (letters/digits/hyphen), the shape
# every subcommand name in this project's parser takes. Stops at the first
# flag, quoted value, or path - exactly where the subcommand chain ends and
# the command's own arguments begin, so the tail need not be shell-parsed.
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


def _godmode_subcommand_tokens(command: str) -> list[str]:
    """Bare tokens right after `godmode`, up to the first flag/quoted arg."""
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


class DemoDocCommandsTests(unittest.TestCase):
    def test_doc_exists_and_has_console_blocks(self) -> None:
        self.assertTrue(DEMO_DOC.is_file(), f"{DEMO_DOC} must exist")
        blocks = _fenced_console_blocks(DEMO_DOC.read_text(encoding="utf-8"))
        self.assertTrue(blocks, "docs/DEMO.md must carry at least one ```console block")

    def test_every_godmode_command_resolves(self) -> None:
        text = DEMO_DOC.read_text(encoding="utf-8")
        commands = [
            command
            for block in _fenced_console_blocks(text)
            for command in _shell_commands(block)
            if command.startswith("godmode ")
        ]
        self.assertTrue(commands, "expected at least one '$ godmode ...' line in docs/DEMO.md")
        for command in commands:
            tokens = _godmode_subcommand_tokens(command)
            self.assertTrue(tokens, f"no bare subcommand token parsed from: {command!r}")
            with self.subTest(command=command):
                resolve_subcommand_chain(tokens)

    def test_scenarios_brief_is_the_real_flag(self) -> None:
        # --brief is a global flag lifted at parse time (godmode_console.main),
        # not a scenarios-specific one - pin that it is at least declared
        # somewhere on the top-level parser, so the doc's flag is not invented.
        parser = _build_parser()
        brief_actions = [
            opt for action in parser._actions for opt in action.option_strings  # noqa: SLF001
            if opt == "--brief"
        ]
        self.assertIn("--brief", brief_actions)


if __name__ == "__main__":
    unittest.main()
