"""Codex on Windows and Codex's own ask surface (obligations 10242-10244, 9924).

Read from openai/codex main on 2026-09-08: a command handler takes
`commandWindows` (alias `command_windows`) and on Windows the engine runs
`commandWindows.unwrap_or(command)` under the user's detected shell, which is
PowerShell there; the hook event keys are the PascalCase Claude names and
cover twelve events including `PermissionRequest`; a PermissionRequest hook
answers with `hookSpecificOutput.decision.{behavior: allow|deny, message}`;
a PreToolUse hook may answer `permissionDecision: ask`.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as host_manifests  # noqa: E402
from godmode_runtime.godmode_hostevent import (  # noqa: E402
    HOSTS_WITH_ASK, is_pretool_event, render_decision,
)


class CodexProjectHooksWindowsTests(unittest.TestCase):
    def test_every_projected_handler_carries_a_powershell_command_for_windows(self) -> None:
        doc = host_manifests.codex_project_hooks(PLUGIN_ROOT)
        root = PLUGIN_ROOT.as_posix()
        for event, blocks in doc["hooks"].items():
            for block in blocks:
                for entry in block["hooks"]:
                    windows = entry.get("commandWindows")
                    self.assertIsInstance(windows, str, f"{event}: no commandWindows")
                    # PowerShell: a quoted path in statement position is a
                    # ParserError (Grok field report 2026-09-05), so the call
                    # operator leads, and no sh syntax survives.
                    # The host is named in the command itself: a project-level
                    # hook carries no plugin-root variable for detection to
                    # read (live probe 2026-09-09 anchored as `claude`).
                    self.assertTrue(windows.startswith("$env:GODMODE_HOST='codex'; & \""), windows)
                    self.assertIn(f'{root}/hooks/run-hook.cmd"', windows)
                    self.assertNotIn("${", windows)
                    self.assertTrue(entry["command"].startswith('cd "'), entry["command"])
                    self.assertIn("; GODMODE_HOST=codex ./run-hook.cmd", entry["command"])

    def test_the_projection_declares_permission_request_as_the_ask_surface(self) -> None:
        doc = host_manifests.codex_project_hooks(PLUGIN_ROOT)
        self.assertIn("PermissionRequest", doc["hooks"])
        blocks = doc["hooks"]["PermissionRequest"]
        self.assertTrue(blocks)
        commands = [e["command"] for b in blocks for e in b["hooks"]]
        self.assertTrue(all("godmode_session_hook.py pre-action" in c for c in commands), commands)

    def test_codex_declares_every_shared_event_plus_permission_request(self) -> None:
        shared = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(host_manifests.CODEX_HOOK_EVENTS), set(shared["hooks"]))
        self.assertEqual(set(host_manifests.CODEX_PROJECT_EVENTS),
                         set(shared["hooks"]) | {"PermissionRequest"})

    def test_the_codex_artifact_states_the_plugin_scope_windows_gap(self) -> None:
        gap = host_manifests.HOOK_ARTIFACTS["codex"].get("gap", "")
        self.assertIn("PowerShell", gap)
        self.assertIn("commandWindows", gap)


class CodexDecisionDialectTests(unittest.TestCase):
    def test_permission_request_is_a_pre_tool_event(self) -> None:
        self.assertTrue(is_pretool_event({"hook_event_name": "PermissionRequest"}))

    def test_codex_can_ask(self) -> None:
        self.assertIn("codex", HOSTS_WITH_ASK)
        body, _ = render_decision("codex", "PreToolUse", "ask", "why")
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_a_permission_request_deny_speaks_codex_decision_dialect(self) -> None:
        body, code = render_decision("codex", "PermissionRequest", "deny", "no")
        self.assertEqual(code, 0)
        self.assertEqual(body, {"hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": "no"}}})

    def test_a_permission_request_ask_stays_silent_so_codex_asks_the_operator(self) -> None:
        body, code = render_decision("codex", "PermissionRequest", "ask", "confirm")
        self.assertEqual((body, code), ({}, 0))

    def test_a_permission_request_allow_never_grants_what_codex_would_have_asked(self) -> None:
        # No objection from godmode is not an approval: silence leaves
        # Codex's own approval flow in charge.
        self.assertEqual(render_decision("codex", "PermissionRequest", "allow", ""), ({}, 0))


if __name__ == "__main__":
    unittest.main()
