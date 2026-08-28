"""S7: the boundary carries the net (obligations 4516, 4521, 4523).

4516: removal-shaped denies/asks name the governance preview in the reason.
4521: candidate keywords drop trailing punctuation; a passage the operator
said to disregard feeds neither detector.
4523: a deny relayed through the OpenCode shim records an ACKNOWLEDGED
interception proof - the shim's documented throw stops the tool - while a
self-injected probe still cannot claim acknowledgement.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402


def _run_hook(project: Path, payload: dict, extra_env: dict) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOKS / "godmode_session_hook.py"),
         "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", timeout=120, env=environment,
    )


class KeywordHygieneTests(unittest.TestCase):
    def test_trailing_punctuation_is_stripped(self) -> None:
        from godmode_runtime.godmode_requests import _keywords

        words = _keywords("continue. here. the agent entered intial text")
        self.assertNotIn("continue.", words)
        self.assertNotIn("here.", words)
        self.assertIn("continue", words)
        for token in words:
            self.assertFalse(token.endswith("."), token)
            self.assertGreaterEqual(len(token), 4, token)

    def test_a_disregarded_passage_feeds_neither_detector(self) -> None:
        from godmode_runtime.godmode_law import (
            record_correction_candidate, record_instruction_candidate)

        prompt = ("always include the report section - ignore this as it "
                  "entered here by mistake, you missed it again")
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(record_instruction_candidate(archive, prompt))
            self.assertIsNone(record_correction_candidate(archive, prompt))


class GovernanceNoteTests(unittest.TestCase):
    def test_a_removal_shaped_deny_names_the_preview(self) -> None:
        with isolated_project() as (project, state, _a, archive):
            archive.initialize()
            done = _run_hook(project, {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "rm -rf build"},
            }, {"GODMODE_STATE_HOME": str(state)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("godmode-governance", done.stdout)

    def test_an_unrelated_deny_stays_quiet_about_it(self) -> None:
        with isolated_project() as (project, state, _a, archive):
            archive.initialize()
            done = _run_hook(project, {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            }, {"GODMODE_STATE_HOME": str(state)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("godmode-governance", done.stdout)


class LiveShimProofTests(unittest.TestCase):
    def test_a_shim_marked_deny_records_an_acknowledged_proof(self) -> None:
        from godmode_runtime.godmode_hookproof import last_proof

        with isolated_project() as (project, state, _a, archive):
            archive.initialize()
            done = _run_hook(project, {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            }, {"GODMODE_STATE_HOME": str(state),
                "GODMODE_HOST": "opencode",
                "GODMODE_SHIM_BOUNDARY": "opencode"})
            self.assertEqual(done.returncode, 0, done.stderr)
            archive._events_cache_key = None
            proof = last_proof(archive, "opencode")
        self.assertIsNotNone(proof)
        self.assertTrue(proof["data"].get("host_acknowledgement"))

    def test_without_the_marker_no_proof_is_written(self) -> None:
        from godmode_runtime.godmode_hookproof import last_proof

        with isolated_project() as (project, state, _a, archive):
            archive.initialize()
            _run_hook(project, {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            }, {"GODMODE_STATE_HOME": str(state),
                "GODMODE_HOST": "opencode"})
            archive._events_cache_key = None
            self.assertIsNone(last_proof(archive, "opencode"))

    def test_the_shipped_shim_carries_the_marker(self) -> None:
        body = (PLUGIN_ROOT / "adapters" / "opencode"
                / "godmode.opencode.js").read_text(encoding="utf-8")
        self.assertIn("GODMODE_SHIM_BOUNDARY", body)


if __name__ == "__main__":
    unittest.main()
