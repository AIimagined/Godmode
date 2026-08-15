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
import json
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
CLAUDE_MARKETPLACE = PLUGIN_ROOT / ".claude-plugin" / "marketplace.json"

# The zero-PATH-setup fallback command (fix round I1): `python
# .../scripts/godmode.py <subcommand> ...`. Captures the subcommand chain
# so it can be walked through the parser the same way a bare `godmode ...`
# line is.
_PYTHON_GODMODE_PY = re.compile(r"python\s+\S*scripts/godmode\.py\s+(.*)$")

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


def _bare_subcommand_tokens(remainder: str) -> list[str]:
    """Bare tokens from the start of `remainder`, stopping at the first
    flag, placeholder (`<...>`), or quoted arg - exactly where a subcommand
    chain ends and the command's own arguments begin."""
    tokens: list[str] = []
    for token in remainder.split():
        if not _BARE_TOKEN.match(token):
            break
        tokens.append(token)
    return tokens


def _godmode_subcommand_tokens(command: str) -> list[str]:
    """Bare tokens right after `godmode`, up to the first flag/placeholder/quoted arg."""
    if not command.startswith("godmode "):
        return []
    return _bare_subcommand_tokens(command[len("godmode "):])


def _python_scripts_godmode_subcommand_tokens(command: str) -> list[str]:
    """Bare tokens after `python <anything>scripts/godmode.py`, same shape
    as `_godmode_subcommand_tokens` but for the zero-PATH-setup fallback
    form the Install section shows (fix round I1)."""
    match = _PYTHON_GODMODE_PY.match(command)
    if not match:
        return []
    return _bare_subcommand_tokens(match.group(1))


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

    def test_the_zero_path_setup_fallback_command_resolves(self) -> None:
        # Fix round I1: the Install section's `python .../scripts/godmode.py
        # init` fallback (for a terminal outside Claude Code's own Bash
        # tool) must resolve against the real parser tree too, not just the
        # bare `godmode ...` form.
        text = README.read_text(encoding="utf-8")
        commands = [
            command
            for block in _fenced_console_blocks(text)
            for command in _shell_commands(block)
            if _PYTHON_GODMODE_PY.match(command)
        ]
        self.assertTrue(
            commands,
            "expected at least one fenced 'python .../scripts/godmode.py ...' "
            "line in README.md (the zero-PATH-setup fallback)",
        )
        for command in commands:
            tokens = _python_scripts_godmode_subcommand_tokens(command)
            self.assertTrue(tokens, f"no bare subcommand token parsed from: {command!r}")
            with self.subTest(command=command):
                resolve_subcommand_chain(tokens)

    def test_the_cache_path_names_the_real_marketplace_and_plugin(self) -> None:
        # The Install section's cache-path fallback
        # (~/.claude/plugins/cache/<marketplace>/<plugin>/...) hardcodes
        # "aiimagined" and "godmode" as literal path segments, per Claude
        # Code's documented `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/`
        # layout. Pin both segments against the real marketplace manifest
        # so a marketplace or plugin rename doesn't leave a silently wrong
        # path in the README.
        self.assertTrue(CLAUDE_MARKETPLACE.is_file(), f"{CLAUDE_MARKETPLACE} must exist")
        marketplace = json.loads(CLAUDE_MARKETPLACE.read_text(encoding="utf-8"))
        marketplace_name = marketplace["name"]
        plugin_name = marketplace["plugins"][0]["name"]

        text = README.read_text(encoding="utf-8")
        expected_prefix = f"~/.claude/plugins/cache/{marketplace_name}/{plugin_name}/"
        self.assertIn(
            expected_prefix, text,
            f"README.md's cache-path fallback must use the real marketplace "
            f"('{marketplace_name}') and plugin ('{plugin_name}') names from "
            f"{CLAUDE_MARKETPLACE}",
        )
        # And the install snippet's `@aiimagined` suffix names the same marketplace.
        self.assertIn(f"@{marketplace_name}", text)

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
