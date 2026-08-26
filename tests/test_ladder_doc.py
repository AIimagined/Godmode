"""C-61: a tiered difficulty ladder for onboarding.

`docs/LADDER.md` is four tiers, each a fenced `console` block. Every
`$ godmode ...` line in it walks the real parser the way README.md's and
DEMO.md's do, so a tier cannot name a command that does not exist. `guide
--tier N` prints one tier, so the day-one reader is never handed the
fleet tier by accident.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_console import _build_parser  # noqa: E402

LADDER = PLUGIN_ROOT / "docs" / "LADDER.md"
_BARE = re.compile(r"^[A-Za-z][\w-]*$")
_TIER = re.compile(r"^## Tier (\d)\b", re.M)


def _console_commands(text: str) -> list[str]:
    commands: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.strip() == "```console":
            inside = True
            continue
        if inside and line.strip() == "```":
            inside = False
            continue
        if inside and line.strip().startswith("$ godmode "):
            commands.append(line.strip()[len("$ godmode "):])
    return commands


def _walk(tokens: list[str]) -> None:
    parser = _build_parser()
    for token in tokens:
        action = next((a for a in parser._actions  # noqa: SLF001
                       if isinstance(a, argparse._SubParsersAction)), None)  # noqa: SLF001
        if action is None:
            return  # a leaf: what follows is the command's own positional
        if token not in action.choices:
            raise AssertionError(f"unknown subcommand hop {token!r} in {tokens}")
        parser = action.choices[token]


class LadderDocTests(unittest.TestCase):
    def test_four_tiers_each_with_commands_the_parser_accepts(self) -> None:
        text = LADDER.read_text(encoding="utf-8")
        tiers = _TIER.findall(text)
        self.assertEqual(tiers, ["1", "2", "3", "4"])
        sections = _TIER.split(text)[1:]  # [num, body, num, body, ...]
        for number, body in zip(sections[0::2], sections[1::2]):
            commands = _console_commands(body)
            self.assertGreaterEqual(len(commands), 3, f"tier {number} is thin")
            for command in commands:
                tokens = []
                for token in command.split():
                    if not _BARE.match(token):
                        break
                    tokens.append(token)
                self.assertTrue(tokens, command)
                _walk(tokens)

    def test_guide_prints_one_tier_only(self) -> None:
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            code = console.main(["guide", "--tier", "2"])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("## Tier 2", text)
        self.assertNotIn("## Tier 3", text)
        self.assertNotIn("## Tier 1", text)


if __name__ == "__main__":
    unittest.main()
