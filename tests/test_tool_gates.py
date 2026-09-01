"""Declarative per-tool gates: approval demanded at the tool's declaration.

The policy file may declare `tool_gates: {"WebFetch": "ask"}` and every
call of that tool then asks (or denies), composing with the classifier.
Tighten-only by construction: a value other than ask/deny is ignored,
because a policy file must never become a second place allow decisions
come from.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-toolgate-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state


def _fire(project: Path, state: Path, tool: str, tool_input: dict) -> subprocess.CompletedProcess:
    environment = {**os.environ, "GODMODE_STATE_HOME": str(state),
                   "GODMODE_HOST": "claude"}
    payload = {"tool_name": tool, "tool_input": tool_input,
               "cwd": str(project), "hook_event_name": "PreToolUse"}
    return subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


def _decision(done: subprocess.CompletedProcess) -> str:
    body = (done.stdout or "").strip()
    if not body:
        return "allow"
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return str(specific.get("permissionDecision", "allow"))


class ToolGateTests(unittest.TestCase):
    def test_a_declared_gate_asks_on_every_call(self) -> None:
        with _project() as (project, state):
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"tool_gates": {"WebFetch": "ask"}}),
                encoding="utf-8")
            done = _fire(project, state, "WebFetch",
                         {"url": "https://example.com", "prompt": "read"})
            self.assertEqual(_decision(done), "ask")
            self.assertIn("tool_gates", done.stdout)

    def test_an_undeclared_tool_is_untouched(self) -> None:
        with _project() as (project, state):
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"tool_gates": {"WebFetch": "ask"}}),
                encoding="utf-8")
            done = _fire(project, state, "Read", {"file_path": "a.py"})
            self.assertEqual(_decision(done), "allow")

    def test_a_loosening_value_refuses_loudly(self) -> None:
        # "allow" in the policy must not become a second allow source - and
        # per the malformed-policy doctrine it refuses loudly rather than
        # silently degrading, so the operator error is impossible to miss.
        with _project() as (project, state):
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"tool_gates": {"Bash": "allow"}}),
                encoding="utf-8")
            done = _fire(project, state, "Bash", {"command": "git status"})
            self.assertIn(_decision(done), ("ask", "deny"))
            self.assertIn("tool_gates", done.stdout)

    def test_a_declared_deny_denies(self) -> None:
        with _project() as (project, state):
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"tool_gates": {"WebFetch": "deny"}}),
                encoding="utf-8")
            done = _fire(project, state, "WebFetch",
                         {"url": "https://example.com", "prompt": "read"})
            self.assertEqual(_decision(done), "deny")


if __name__ == "__main__":
    unittest.main()
