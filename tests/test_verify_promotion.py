"""Raw check commands get pointed at `godmode verify`, once per session.

A test run typed raw produces an exit code the archive never sees; the
same run wrapped in `godmode verify` produces an attestation the claim
gate can cite. The pre-action hook already reads every command, so the
promotion happens there: one advisory sentence on the first raw
check-shaped command of a session, silence after (a nag on every test
run would teach dismissal), and silence for commands already invoking
godmode.
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
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-verifyprom-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state


def _fire(project: Path, state: Path, command: str,
          session: str = "S-verifyprom") -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    payload = {"tool_name": "Bash", "tool_input": {"command": command},
               "cwd": str(project), "hook_event_name": "PreToolUse",
               "session_id": session}
    return subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


class VerifyPromotionTests(unittest.TestCase):
    def test_first_raw_check_gets_the_advisory(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "python -m pytest tests/")
            self.assertEqual(done.returncode, 0, done.stderr)
            body = json.loads(done.stdout)
            self.assertIn("godmode verify", body.get("systemMessage", ""))

    def test_second_raw_check_is_silent(self) -> None:
        with _project() as (project, state):
            _fire(project, state, "python -m pytest tests/")
            done = _fire(project, state, "npm test")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("godmode verify", done.stdout or "")

    def test_wrapped_check_is_silent(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "godmode verify unit -- python -m pytest")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("systemMessage", done.stdout or "")

    def test_non_check_command_is_silent(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "git log --oneline -5")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("godmode verify", done.stdout or "")


if __name__ == "__main__":
    unittest.main()
