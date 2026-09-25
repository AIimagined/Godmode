"""An agent's own tool call may not start a password-bearing `authorize` verb.

`authorize stage|setup|grant|issue` opens the operator's password dialog. An
agent cannot type the password, but it can ask for it to be typed, and a
prompt raised on an agent's behalf teaches the operator to answer it. The
gate refuses those calls in every mode and names the remedy the operator
performs themselves: the same command with a leading `!`, which never passes
the gate. `authorize request` and `authorize requests` are the verbs meant
for agents and stay free.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
HOOK = HOOKS / "godmode_session_hook.py"
TESTS = PLUGIN_ROOT / "tests"
for entry in (SCRIPTS, HOOKS, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import godmode_gate_fast as fast  # noqa: E402
from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    GATE_MODE_OBSERVE, POLICY_FILENAME, CapabilityBroker, classify_action,
    stage_from_refusal)
from test_godmode_runtime import isolated_project  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

CATEGORY = "operator-authorization-from-agent"
PASSWORD = "correct horse battery"
STAGE = "godmode authorize stage --operation 'git push origin main'"

REFUSED = (
    ("godmode authorize stage --from-last-refusal", "Bash"),
    ("bin/godmode authorize setup", "Bash"),
    ("python scripts/godmode.py authorize stage --from-last-refusal", "Bash"),
    ("python C:/x/scripts/godmode.py --project . authorize grant --request R-1", "Bash"),
    ('"C:/Users/u/.claude/plugins/godmode/bin/godmode" authorize issue --operation "git push"',
     "Bash"),
    ("git status && godmode authorize stage --operation x", "Bash"),
    ("git status; godmode authorize stage --operation x", "Bash"),
    ("godmode status | godmode authorize stage --operation x", "Bash"),
    ("echo $(godmode authorize stage --operation x)", "Bash"),
    ("(godmode authorize stage --operation x)", "Bash"),
    ("bash -c 'godmode authorize stage --operation x'", "Bash"),
    ('& "C:\\Users\\u\\godmode\\bin\\godmode.cmd" authorize stage --operation x', "PowerShell"),
    ("python scripts\\godmode.py authorize stage --from-last-refusal", "PowerShell"),
    ('powershell -Command "godmode authorize stage --operation x"', "PowerShell"),
    ("cd x; godmode authorize setup", "PowerShell"),
)

FREE = (
    "godmode authorize request --operation 'git push origin main' --purpose 'ship it'",
    "godmode authorize requests",
    "python scripts/godmode.py authorize requests --state requested",
    "echo godmode authorize stage",
)

_HOST_ENV = None


def setUpModule() -> None:
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()


def _decide(project: Path, command: str, tool: str = "Bash", **extra: str) -> dict:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": {"command": command}, "cwd": str(project), **extra}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project))
    body = (done.stdout or "").strip()
    if not body:
        return {"decision": "allow", "reason": ""}
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return {"decision": str(specific.get("permissionDecision") or "allow"),
            "reason": str(specific.get("permissionDecisionReason", ""))}


class ClassifierTests(unittest.TestCase):
    def test_every_launcher_and_compound_form_is_refused_outright(self) -> None:
        for command, tool in REFUSED:
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT, tool_name=tool)
                self.assertEqual(verdict["category"], CATEGORY, verdict)
                self.assertEqual(verdict["tier"], "R5")
                self.assertTrue(verdict["protected"])

    def test_the_agent_verbs_and_mentions_are_not_that_category(self) -> None:
        for command in FREE:
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertNotEqual(verdict["category"], CATEGORY)
                self.assertFalse(verdict["protected"], verdict)


class FastGateTests(unittest.TestCase):
    def test_the_fast_gate_never_allows_a_godmode_call(self) -> None:
        table = json.loads((HOOKS / "gate_table.json").read_text(encoding="utf-8"))
        for command, tool in REFUSED + ((STAGE, "Bash"),):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(
                    {"hook_event_name": "PreToolUse", "tool_name": tool,
                     "tool_input": {"command": command}}, table), "escalate")


class HookTests(unittest.TestCase):
    def assert_refused(self, outcome: dict) -> None:
        self.assertEqual(outcome["decision"], "deny", outcome)
        self.assertIn("`!", outcome["reason"])
        self.assertIn("authorize request", outcome["reason"])

    def test_refused_attended_and_names_the_bang_remedy(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            self.assert_refused(_decide(project, STAGE))
            self.assert_refused(_decide(project, "python scripts\\godmode.py authorize setup",
                                        tool="PowerShell"))

    def test_refused_under_auto_mode_and_unattended(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            self.assert_refused(_decide(project, STAGE, permission_mode="auto"))
            self.assert_refused(_decide(project, STAGE, permission_mode="bypassPermissions"))

    def test_refused_in_observe_mode(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / POLICY_FILENAME).write_text(
                json.dumps({"gate_mode": GATE_MODE_OBSERVE}), encoding="utf-8")
            self.assert_refused(_decide(project, STAGE))

    def test_a_staged_capability_does_not_open_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(STAGE, PASSWORD)
            self.assert_refused(_decide(project, STAGE))

    def test_the_refusal_is_never_offered_to_from_last_refusal(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            self.assert_refused(_decide(project, STAGE))
            with self.assertRaises(AuthorizationError):
                stage_from_refusal(archive)

    def test_authorize_request_passes(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            outcome = _decide(project, "godmode authorize request --operation "
                                       "'git push origin main' --purpose 'ship it'")
            self.assertEqual(outcome["decision"], "allow", outcome)
            self.assertEqual(_decide(project, "godmode authorize requests")["decision"],
                             "allow")


if __name__ == "__main__":
    unittest.main()
