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
import time
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
from godmode_runtime.godmode_projectmode import set_project_mode  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

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
            # This asserts the main Stop's own enforcement (decision:
            # block); R1's advise mode is a separate module's concern
            # (test_mode_switch.py).
            set_project_mode(archive, "strict")
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
    environment = scrubbed_env()
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


    def test_parks_from_two_sessions_and_a_parent_are_all_kept(self) -> None:
        with _project() as (project, state, archive):
            echo = archive.root / "godmode-claim-echo.json"
            # The parent session's own Stop already parked a sentence.
            echo.write_text(json.dumps({"sentences": ["parent probe-1111"],
                                        "session": "S-a"}), encoding="utf-8")
            transcript = _transcript(project.parent, DONE_TEXT)
            for session in ("S-b", "S-a"):
                sub = _fire("subagent-stop", project, state, {
                    "hook_event_name": "SubagentStop", "session_id": session,
                    "agent_id": "a-1", "agent_type": "general-purpose",
                    "agent_transcript_path": str(transcript), "cwd": str(project)})
                self.assertEqual(sub.returncode, 0, sub.stderr)
            parked = json.loads(echo.read_text(encoding="utf-8"))
            prompt = _fire("user-prompt", project, state, {
                "hook_event_name": "UserPromptSubmit", "prompt": "go on",
                "session_id": "S-b", "cwd": str(project)})
            left = json.loads(echo.read_text(encoding="utf-8"))
        self.assertEqual(parked.get("session"), "S-a", parked)
        own = " ".join(parked.get("sentences") or [])
        self.assertIn("probe-1111", own)
        self.assertIn("migration", own)
        self.assertIn("migration", " ".join(parked["others"]["S-b"]["sentences"]))
        self.assertIn("migration", prompt.stdout)
        self.assertNotIn("probe-1111", prompt.stdout)
        self.assertIn("probe-1111", json.dumps(left))

    def test_a_park_waits_for_another_process_holding_the_archive_lock(self) -> None:
        holder_code = (
            "import json, sys, time\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from godmode_runtime.godmode_anchor import resolve_anchor\n"
            "from godmode_runtime.godmode_chronicle import Chronicle\n"
            "archive = Chronicle(resolve_anchor(Path(sys.argv[2])))\n"
            "echo = archive.root / 'godmode-claim-echo.json'\n"
            "with archive.write_lock():\n"
            "    before = echo.read_bytes() if echo.exists() else b''\n"
            "    print('held', flush=True)\n"
            "    time.sleep(float(sys.argv[3]))\n"
            "    after = echo.read_bytes() if echo.exists() else b''\n"
            "    echo.write_text(json.dumps({'sentences': ['holder probe-2222'],\n"
            "                                'session': 'S-a', 'at': time.time()}),\n"
            "                    encoding='utf-8')\n"
            "    released = time.time()\n"
            "print(json.dumps({'untouched': before == after, 'released': released}),\n"
            "      flush=True)\n")
        with _project() as (project, state, archive):
            transcript = _transcript(project.parent, DONE_TEXT)
            environment = scrubbed_env()
            environment["GODMODE_STATE_HOME"] = str(state)
            holder = subprocess.Popen(
                [sys.executable, "-c", holder_code, str(SCRIPTS), str(project), "4"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "held")
                sub = _fire("subagent-stop", project, state, {
                    "hook_event_name": "SubagentStop", "session_id": "S-a",
                    "agent_id": "a-1", "agent_type": "general-purpose",
                    "agent_transcript_path": str(transcript), "cwd": str(project)})
                parked_at = time.time()
                out, err = holder.communicate(timeout=60)
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=10)
            self.assertEqual(sub.returncode, 0, sub.stderr)
            self.assertEqual(holder.returncode, 0, err)
            report = json.loads(out.strip().splitlines()[-1])
            parked = json.loads((archive.root / "godmode-claim-echo.json").read_text(
                encoding="utf-8"))
        # Nothing wrote the echo while the other process held the lock, the
        # park finished only after it was released, and it kept what the
        # holder wrote.
        self.assertTrue(report["untouched"], report)
        self.assertGreater(parked_at, report["released"])
        own = " ".join(parked.get("sentences") or [])
        self.assertIn("probe-2222", own)
        self.assertIn("migration", own)


if __name__ == "__main__":
    unittest.main()
