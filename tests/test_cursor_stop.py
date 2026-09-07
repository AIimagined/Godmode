"""The done-bar reaches Cursor through Cursor's own stop contract.

Sweep 2026-09-07: a first-party Cursor plugin in the research ledger ends
its stop hook with `{"followup_message": ...}` under a manifest
`loop_limit`; Claude's `{"decision": "block", "reason": ...}` means nothing
there. Godmode's Cursor manifest carried no stop hook at all, so the
done-bar never fired on Cursor. Obligation 9869 (probe found a gap).
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

from godmode_runtime import godmode_host_manifests as host_manifests  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import HOST_MARKERS  # noqa: E402

DONE_TEXT = "Done: the migration is complete and all 12 tests pass."


class CursorStopManifestTests(unittest.TestCase):
    def test_the_cursor_manifest_declares_a_bounded_stop_hook(self) -> None:
        manifest = host_manifests.build_cursor_manifest()
        stops = manifest["hooks"].get("stop") or []
        self.assertTrue(stops, manifest["hooks"].keys())
        self.assertEqual(stops[0].get("loop_limit"), 1)
        self.assertIn("godmode_session_hook.py", json.dumps(stops[0]))
        self.assertIn("stop", host_manifests.CURSOR_HOOK_EVENTS)


class CursorStopRenderTests(unittest.TestCase):
    def test_a_done_claim_becomes_a_followup_message_on_cursor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-cursorstop-") as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                Chronicle(resolve_anchor(project)).initialize()
            transcript = base / "t.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "do it"}}),
                json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "text", "text": DONE_TEXT}]}})]), encoding="utf-8")
            environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
            environment["GODMODE_STATE_HOME"] = str(state)
            environment["GODMODE_HOST"] = "cursor"
            done = subprocess.run(
                [sys.executable, str(HOOK), "stop", "--project", str(project)],
                input=json.dumps({"hook_event_name": "stop", "conversation_id": "c-1",
                                  "status": "completed", "loop_count": 0,
                                  "transcript_path": str(transcript), "cwd": str(project)}),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=180, env=environment)
        body = json.loads(done.stdout)
        self.assertIn("DONE BAR", body.get("followup_message", ""), body)
        self.assertNotIn("decision", body)


if __name__ == "__main__":
    unittest.main()
