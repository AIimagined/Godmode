"""Session end writes a dated checkpoint even when nobody wrote one.

Field report (2026-08-27, another project): the continuity brief showed a
checkpoint from 08-16 while the project's own state file was at 08-24,
because nothing in that project's ritual writes a godmode checkpoint. Two
gaps behind that. Claude's hooks.json never registered PreCompact or
SessionEnd, so the session-end branch never ran on Claude Code at all;
and when it does run, the host's SessionEnd payload carries no summary,
so the branch declined to write anything. Now: both events are wired, and
a session end with no summary writes a counts-only checkpoint that says
it is automatic - not a handover, but dated today.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-end-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("action", "edit", {"operation": "edit a.py", "gate": "allow"})
            yield root, archive


class SessionEndCheckpointTests(unittest.TestCase):
    def test_claude_manifest_registers_precompact_and_sessionend(self) -> None:
        manifest = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
        for event, arg in (("PreCompact", "pre-compact"), ("SessionEnd", "session-end")):
            self.assertIn(event, manifest["hooks"])
            self.assertIn(arg, json.dumps(manifest["hooks"][event]))

    def test_session_end_without_a_summary_writes_an_auto_checkpoint(self) -> None:
        with _project() as (root, archive):
            payload = json.dumps({"session_id": "s1", "hook_event_name": "SessionEnd",
                                  "cwd": str(root)})
            out = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", out):
                code = hook.main(["session-end", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(code, 0)
        self.assertEqual(len(checkpoints), 1, out.getvalue())
        data = checkpoints[0]["data"]
        self.assertTrue(data["auto"])
        self.assertEqual(data["status"], "auto")
        self.assertEqual(data["counts"].get("action"), 1)
        self.assertNotIn("edit a.py", json.dumps(checkpoints[0]))

    def test_a_summary_still_writes_a_real_checkpoint(self) -> None:
        with _project() as (root, archive):
            payload = json.dumps({"summary": "shipped the thing", "status": "done",
                                  "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main(["session-end", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(checkpoints[0]["subject"], "shipped the thing")
        self.assertNotIn("auto", checkpoints[0]["data"])


if __name__ == "__main__":
    unittest.main()
