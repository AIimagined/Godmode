"""S12-A: bare `godmode` is the day-one face, `--all` the generated list.

The listing risk (Grok field report): a hundred verbs as the first
impression. The face is presentation only - these pins hold that every
registered verb stays reachable and listed, and that the bare screen
speaks the host's own dialect.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _run(extra_args, env_extra=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("GODMODE_HOST", "GROK_AGENT", "GROK_PLUGIN_ROOT",
                        "GROK_HOOK_EVENT", "CLAUDE_CODE_ENTRYPOINT",
                        "PLUGIN_ROOT", "ANTIGRAVITY_AGENT",
                        "ANTIGRAVITY_CONVERSATION_ID")}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
         *extra_args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120, env=env)


class DayOneFaceTests(unittest.TestCase):
    def test_bare_invocation_shows_the_eight_and_exits_zero(self) -> None:
        done = _run([], {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        for verb in ("init", "resume", "status", "doctor", "forecast",
                     "checkpoint", "capabilities", "guide"):
            self.assertIn(f"godmode {verb}", done.stdout)
        self.assertIn("--all", done.stdout)

    def test_the_day_one_verbs_are_real_registered_verbs(self) -> None:
        from godmode_runtime.godmode_console import (
            _DAY_ONE_VERBS, _build_parser, _subparser_action)

        choices = set(_subparser_action(_build_parser()).choices)
        for name, _blurb in _DAY_ONE_VERBS:
            self.assertIn(name, choices)

    def test_all_lists_every_registered_verb(self) -> None:
        from godmode_runtime.godmode_console import (
            _build_parser, _subparser_action)

        done = _run(["--all"], {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in _subparser_action(_build_parser()).choices:
            self.assertIn(name, done.stdout)

    def test_a_no_ask_host_sees_the_deny_dialect_on_the_face(self) -> None:
        done = _run([], {"GROK_PLUGIN_ROOT": "C:/x"})
        self.assertIn("has no ask", done.stdout)
        self.assertIn("authorize stage", done.stdout)

    def test_a_real_command_still_parses_untouched(self) -> None:
        done = _run(["version"], {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("0.3.", done.stdout)


if __name__ == "__main__":
    unittest.main()
