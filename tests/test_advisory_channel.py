"""Model-addressed advisories ride the channel the model reads.

Sweep 2026-09-07 (planning-with-files eb8af2f, measured on Claude Code):
`systemMessage` is shown to the operator; the model never sees it. Godmode's
allowed-call advisories (evidence pipe, checkpoint pressure, verify
promotion, observe) and its post-edit findings were all `systemMessage`
only, which is why field reports never saw a promotion land. Each now also
rides `hookSpecificOutput.additionalContext` (Claude, Codex, Grok - Grok
delivers it with the call's result) or `agent_message` (Cursor), while the
operator keeps the `systemMessage`. Stop notices are parked for the next
prompt boundary the way the claim echo already is, and on Grok every parked
context rides the first allowed tool call. Obligation 9860.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
POST_EDIT = PLUGIN_ROOT / "hooks" / "godmode_post_edit.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import HOST_MARKERS  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-advchan-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state, archive


def _fire(event: str, payload: dict, project: Path, state: Path,
          host_env: dict | None = None) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment["GODMODE_STATE_HOME"] = str(state)
    environment.update(host_env or {})
    return subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


def _pretool(command: str, project: Path, session: str = "S-adv") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": str(project),
            "session_id": session}


PIPED_CHECK = "python -m pytest tests/ 2>&1 | tail -5"


class AllowedCallAdvisoryTests(unittest.TestCase):
    def test_claude_gets_the_advisory_as_additional_context(self) -> None:
        with _project() as (project, state, _archive):
            done = _fire("pre-action", _pretool(PIPED_CHECK, project), project, state,
                         {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)
        specific = body.get("hookSpecificOutput") or {}
        self.assertEqual(specific.get("hookEventName"), "PreToolUse")
        self.assertIn("evidence-pipe", specific.get("additionalContext", ""))
        self.assertNotIn("permissionDecision", specific, "an advisory never decides")
        self.assertIn("evidence-pipe", body.get("systemMessage", ""), "operator keeps it")

    def test_cursor_gets_the_advisory_as_agent_message(self) -> None:
        with _project() as (project, state, _archive):
            payload = {"hook_event_name": "beforeShellExecution", "tool_name": "Shell",
                       "tool_input": {"command": PIPED_CHECK}, "cwd": str(project),
                       "session_id": "S-adv"}
            done = _fire("pre-action", payload, project, state, {"GODMODE_HOST": "cursor"})
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)
        self.assertIn("evidence-pipe", body.get("agent_message", ""))
        self.assertIn("evidence-pipe", body.get("user_message", ""))
        self.assertNotIn("permission", body)

    def test_a_quiet_allowed_call_stays_silent(self) -> None:
        with _project() as (project, state, _archive):
            done = _fire("pre-action", _pretool("git status --short", project), project, state,
                         {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((done.stdout or "").strip(), "")


class CursorShellEventTests(unittest.TestCase):
    """Found while writing the advisory test: `beforeShellExecution` was
    adapted as a Cursor event but not counted as a pre-tool event, so the
    hook dumped its preview and exited 0 without a `permission` key."""

    def test_a_force_push_over_before_shell_execution_is_denied_in_cursor_dialect(self) -> None:
        with _project() as (project, state, _archive):
            payload = {"hook_event_name": "beforeShellExecution", "tool_name": "Shell",
                       "tool_input": {"command": "git push --force origin main"},
                       "cwd": str(project), "session_id": "S-adv"}
            done = _fire("pre-action", payload, project, state, {"GODMODE_HOST": "cursor"})
        body = json.loads(done.stdout)
        self.assertEqual(body.get("permission"), "deny", body)
        self.assertIn("irreversible", body.get("user_message", ""))


class PostEditAdvisoryTests(unittest.TestCase):
    def test_findings_ride_additional_context_without_a_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"post_edit_quality": True}), encoding="utf-8")
            doc = project / "notes.md"
            doc.write_text("See C:\\Users\\someone\\x for it.\n\nTODO finish\n", encoding="utf-8")
            payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                       "tool_input": {"file_path": str(doc)}, "cwd": str(project)}
            environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
            done = subprocess.run([sys.executable, str(POST_EDIT)], input=json.dumps(payload),
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=60, cwd=str(project),
                                  env=environment)
        body = json.loads(done.stdout)
        specific = body.get("hookSpecificOutput") or {}
        self.assertEqual(specific.get("hookEventName"), "PostToolUse")
        self.assertIn("local-path", specific.get("additionalContext", ""))
        self.assertNotIn("permissionDecision", specific)
        self.assertNotIn("decision", body)
        self.assertIn("local-path", body.get("systemMessage", ""))


class ParkedNoticeTests(unittest.TestCase):
    def test_parked_stop_notices_are_delivered_at_the_next_prompt(self) -> None:
        with _project() as (project, state, archive):
            (archive.root / "godmode-claim-echo.json").write_text(json.dumps({
                "notices": ["godmode: investigation nudge probe-7731"],
                "session": "S-adv"}), encoding="utf-8")
            done = _fire("user-prompt", {"hook_event_name": "UserPromptSubmit",
                                         "prompt": "go on", "cwd": str(project),
                                         "session_id": "S-adv"},
                         project, state, {"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)
        self.assertIn("probe-7731",
                      (body.get("hookSpecificOutput") or {}).get("additionalContext", ""))

    def test_on_grok_parked_context_survives_the_prompt_and_rides_the_first_call(self) -> None:
        with _project() as (project, state, archive):
            echo = archive.root / "godmode-claim-echo.json"
            echo.write_text(json.dumps({
                "sentences": ["the tests pass now probe-4471"], "session": "S-adv"}),
                encoding="utf-8")
            _fire("user-prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "go on",
                                  "cwd": str(project), "session_id": "S-adv"},
                  project, state, {"GROK_AGENT": "1"})
            self.assertTrue(echo.exists(), "Grok discards prompt-hook stdout")
            done = _fire("pre-action", _pretool("git status --short", project), project, state,
                         {"GROK_AGENT": "1"})
            body = json.loads(done.stdout)
            context = (body.get("hookSpecificOutput") or {}).get("additionalContext", "")
            self.assertIn("probe-4471", context)
            self.assertEqual(body.get("decision"), "allow")
            self.assertFalse(echo.exists())


if __name__ == "__main__":
    unittest.main()
