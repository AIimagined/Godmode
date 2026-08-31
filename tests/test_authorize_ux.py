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
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tests._gate_mode_isolation import park_local_policy, restore_local_policy  # noqa: E402


def setUpModule() -> None:
    # HostedEscapeHintTests drives the real hook against THIS repo, so a
    # local observe-mode declaration replaces the refusal it asserts on
    # with an advisory - see _gate_mode_isolation's docstring.
    park_local_policy()
    # And an initialized archive: on a fresh CI checkout no archive exists
    # and the hook rightly reports not-initialized instead of gating - the
    # empty-reason failures on every CI platform were this (instrumented
    # run 33413975881). A developer machine always has one, which is why
    # no local run ever saw it. initialize() is idempotent.
    from godmode_runtime.godmode_anchor import resolve_anchor
    from godmode_runtime.godmode_chronicle import Chronicle
    Chronicle(resolve_anchor(PLUGIN_ROOT)).initialize()


def tearDownModule() -> None:
    restore_local_policy()


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
        import os
        payload = json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git push --force origin main"},
        })
        # The bang-prefix hint is Claude dialect; run under another host
        # (a Codex or Grok session running this suite) the hook rightly
        # renders that host's envelope and this assertion read an empty
        # field (field report, 2026-08-31). Pin the host the assertion is
        # about instead of inheriting whichever host runs the tests.
        environment = {**os.environ, "GODMODE_HOST": "claude"}
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"),
             "pre-action"],
            input=payload, capture_output=True, text=True, timeout=30,
            cwd=PLUGIN_ROOT, env=environment)
        decision = json.loads(result.stdout)
        reason = decision.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        # Full stdout and stderr ride in the failure: on CI this read an
        # empty reason while every local probe denied with a full one
        # (2026-08-31), and the discarded body was the missing instrument.
        context = f"stdout={result.stdout[:400]!r} stderr={result.stderr[:200]!r}"
        self.assertIn("leading '!'", reason, context)
        self.assertIn("authorize stage", reason, context)


class EllipsizeTests(unittest.TestCase):
    """The refusal embeds the operation and its impact list, both bounded -
    but a hard slice cut mid-word (`...godmode authorize stage "git push --f`)
    and left no sign anything was missing. Bounded text a human reads should
    break at a word and say it was cut."""

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "godmode_session_hook_under_test",
            PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.ellipsize = staticmethod(module._ellipsize)

    def test_short_text_is_untouched(self) -> None:
        self.assertEqual(self.ellipsize("git push", 200), "git push")

    def test_text_at_exactly_the_limit_is_untouched(self) -> None:
        text = "x" * 200
        self.assertEqual(self.ellipsize(text, 200), text)

    def test_long_text_breaks_at_a_word_and_is_marked(self) -> None:
        text = ("git push --force origin main " * 10).strip()
        cut = self.ellipsize(text, 60)
        self.assertLessEqual(len(cut), 60)
        self.assertTrue(cut.endswith("..."), cut)
        kept = cut[:-3]
        # what survived is a prefix of the original, and the cut fell on a
        # word boundary - the next original character is the space itself
        self.assertTrue(text.startswith(kept), cut)
        self.assertEqual(text[len(kept)], " ")

    def test_an_unbroken_token_still_cuts_and_is_marked(self) -> None:
        cut = self.ellipsize("a" * 500, 60)
        self.assertLessEqual(len(cut), 60)
        self.assertTrue(cut.endswith("..."))


if __name__ == "__main__":
    unittest.main()
