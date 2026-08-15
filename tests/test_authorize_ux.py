"""Authorize UX: TTL headroom, real help lines, hosted-session escape hint.

Password touches only R5 (irreversible) operations - day-to-day friction is
zero. The three real rough edges: 180s expired under an agent's ordinary
retry latency; `setup`/`issue` had no --help description at all; and the
refusal never told a hosted-session user how to run the staging command
without leaving the conversation.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class TtlTests(unittest.TestCase):
    def test_default_ttl_is_300(self) -> None:
        from godmode_runtime.godmode_sentinel import _DEFAULT_TTL_SECONDS
        self.assertEqual(_DEFAULT_TTL_SECONDS, 300)

    def test_default_ttl_is_within_the_clamp_range(self) -> None:
        # issue()'s own guard: 10-600 seconds. 300 must stay inside it, or
        # the "default" would be silently rejected the moment it's used.
        from godmode_runtime.godmode_sentinel import _DEFAULT_TTL_SECONDS
        self.assertGreaterEqual(_DEFAULT_TTL_SECONDS, 10)
        self.assertLessEqual(_DEFAULT_TTL_SECONDS, 600)


class AuthorizeHelpTests(unittest.TestCase):
    def test_setup_has_a_real_help_line(self) -> None:
        out = subprocess.run(
            [sys.executable, "scripts/godmode.py", "authorize", "--help"],
            capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
        self.assertIn("password", out.lower())

    def test_setup_subcommand_help_is_not_empty(self) -> None:
        out = subprocess.run(
            [sys.executable, "scripts/godmode.py", "authorize", "setup", "--help"],
            capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
        # argparse always prints "usage:"; a real help line adds prose above
        # the options block, which an empty help= string never does.
        self.assertIn("One-time", out)

    def test_issue_subcommand_help_is_not_empty(self) -> None:
        out = subprocess.run(
            [sys.executable, "scripts/godmode.py", "authorize", "issue", "--help"],
            capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
        self.assertIn("Mint a capability", out)
        self.assertIn("stage", out.lower())


class HostedEscapeHintTests(unittest.TestCase):
    def test_the_hook_refusal_mentions_the_bang_prefix(self) -> None:
        import json
        payload = json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git push --force origin main"},
        })
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"),
             "pre-action"],
            input=payload, capture_output=True, text=True, timeout=30, cwd=PLUGIN_ROOT)
        decision = json.loads(result.stdout)
        reason = decision.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        self.assertIn("leading '!'", reason)
        self.assertIn("authorize stage", reason)


if __name__ == "__main__":
    unittest.main()
