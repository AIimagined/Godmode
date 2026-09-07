"""SubagentStop reaches the done-bar, advisory only.

Sweep 2026-09-07: a memory plugin in the ledger subscribes SubagentStart/Stop, PostToolUse-
Failure, Notification and TaskCompleted; godmode subscribed none of them,
and a subagent's Stop was where the done-bar was bypassed. `SubagentStop`
(documented by Claude, Codex and Grok alike) now routes to the session
hook, which runs the same claim scan and parks the same echo, but never
blocks: a subagent is not the reply the operator is about to trust.
`PostToolUseFailure` is a Claude-only event and the shared manifest is also
read by Codex, whose loader's tolerance of an undocumented key is unproven;
it stays out until probed. Obligation 9867.
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
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import HOST_MARKERS  # noqa: E402

DONE_TEXT = "Done: the migration is complete and all 12 tests pass."


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-substop-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state, archive


def _transcript(base: Path, text: str) -> Path:
    path = base / "transcript.jsonl"
    lines = [
        json.dumps({"type": "user", "message": {"content": "do the thing"}}),
        json.dumps({"type": "assistant",
                    "message": {"content": [{"type": "text", "text": text}]}}),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fire(event: str, project: Path, state: Path, payload: dict) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment["GODMODE_STATE_HOME"] = str(state)
    environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    return subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


class SubagentStopTests(unittest.TestCase):
    def test_the_shared_manifest_routes_subagent_stop(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = manifest["hooks"].get("SubagentStop") or []
        self.assertTrue(any("subagent-stop" in json.dumps(e) for e in entries), entries)

    def test_a_done_claim_blocks_the_main_stop_but_only_advises_the_subagent(self) -> None:
        with _project() as (project, state, archive):
            transcript = _transcript(project.parent, DONE_TEXT)
            main = _fire("stop", project, state, {
                "hook_event_name": "Stop", "session_id": "S-sub",
                "transcript_path": str(transcript), "cwd": str(project)})
            self.assertEqual(json.loads(main.stdout).get("decision"), "block", main.stdout)
            sub = _fire("subagent-stop", project, state, {
                "hook_event_name": "SubagentStop", "session_id": "S-sub",
                "agent_id": "a-1", "agent_type": "general-purpose",
                "agent_transcript_path": str(transcript), "cwd": str(project)})
            self.assertEqual(sub.returncode, 0, sub.stderr)
            body = json.loads(sub.stdout) if sub.stdout.strip() else {}
            self.assertNotEqual(body.get("decision"), "block", body)
            self.assertIn("claim", body.get("systemMessage", ""), body)
            parked = json.loads((archive.root / "godmode-claim-echo.json").read_text(encoding="utf-8"))
            self.assertTrue(parked.get("sentences") or parked.get("notices"), parked)


if __name__ == "__main__":
    unittest.main()
