"""The continuity brief reaches a Grok session through the one channel Grok
reads: PreToolUse `additionalContext`.

Grok's own hook guide: SessionStart stdout is ignored, an allowing
UserPromptSubmit hook's stdout is discarded, and a PreToolUse hook's
`additionalContext` is delivered to the model with the results of the call.
So the brief parked at session start must survive the prompt boundary and
ride the first allowed tool call - once - and the fast gate must escalate
that call instead of answering it silently. Obligation 8584.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
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
FAST_GATE = PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

_spec = importlib.util.spec_from_file_location("godmode_gate_fast", FAST_GATE)
fast = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fast)


@contextmanager
def _hosted():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, state, archive


def _run(event: str, payload: dict, project: Path, state: Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    environment.pop("GODMODE_HOST", None)
    environment.pop("CLAUDE_CODE_ENTRYPOINT", None)
    environment["GROK_AGENT"] = "1"
    return subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", timeout=180, env=environment,
    )


def _park(archive: Chronicle) -> Path:
    parked = archive.root / "godmode-brief-echo.json"
    parked.write_text(json.dumps({"brief": "{\"identity\": \"probe\"}"}), encoding="utf-8")
    return parked


class BriefOnPreToolUseTests(unittest.TestCase):
    def test_an_allowed_call_carries_the_parked_brief_once(self) -> None:
        with _hosted() as (project, state, archive):
            parked = _park(archive)
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "git status --short"}, "cwd": str(project)}
            first = _run("pre-action", payload, project, state)
            body = json.loads(first.stdout.strip())
            self.assertEqual(body.get("decision"), "allow", body)
            context = (body.get("hookSpecificOutput") or {}).get("additionalContext", "")
            self.assertIn("godmode continuity brief", context)
            self.assertIn("probe", context)
            self.assertFalse(parked.exists(), "delivered once, then gone")
            second = _run("pre-action", payload, project, state)
            self.assertEqual(second.stdout.strip(), "", "silence is the allow signal")

    def test_the_prompt_boundary_leaves_the_brief_for_the_tool_call(self) -> None:
        with _hosted() as (project, state, archive):
            parked = _park(archive)
            payload = {"hook_event_name": "UserPromptSubmit", "prompt": "hello",
                       "cwd": str(project)}
            _run("user-prompt", payload, project, state)
            self.assertTrue(parked.exists(), "Grok discards this hook's stdout")


class FastGateEscalationTests(unittest.TestCase):
    def test_session_start_marks_the_git_dir_and_the_fast_gate_escalates(self) -> None:
        with _hosted() as (project, state, archive):
            payload = {"hook_event_name": "SessionStart", "cwd": str(project)}
            _run("session-start", payload, project, state)
            marker = project / ".git" / "godmode-brief-pending"
            self.assertTrue(marker.exists(), "the fast gate reads only this marker")
            with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False):
                self.assertTrue(fast.brief_pending(project))
            with mock.patch.dict(os.environ, {"GROK_AGENT": "", "GROK_HOOK_EVENT": ""},
                                 clear=False):
                os.environ.pop("GROK_AGENT", None)
                os.environ.pop("GROK_HOOK_EVENT", None)
                self.assertFalse(fast.brief_pending(project), "other hosts are unaffected")
            # Delivery clears the marker with the brief.
            tool_call = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "git status --short"}, "cwd": str(project)}
            _run("pre-action", tool_call, project, state)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
