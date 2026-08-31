"""The investigation nudge: repeated red with edits between IS the signal.

The discipline was compiled into a skill and left to willpower, and six
consecutive red CI rounds proved willpower is not a control. The stop
hook already reads the session timeline for the temporal claim check;
the same scan now detects the fix-loop shape - one command failing three
times with mutations between the failures and no investigation opened -
and says so in the same single systemMessage the other notices share.
Command text never appears: the timeline stores digests (the 4018
privacy decision), so the nudge counts and points, it does not quote.
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
HOOKS = PLUGIN_ROOT / "hooks"
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

HOOK = HOOKS / "godmode_session_hook.py"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-nudge-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state, archive


def _turn(kind: str, **fields) -> str:
    return json.dumps({"type": kind, **fields})


def _transcript(base: Path, fail_count: int, with_edits: bool = True) -> Path:
    """A session where one test command goes red `fail_count` times, with a
    file edit between each pair of failures."""
    lines = [
        _turn("user", message={"content": "fix the bug"}),
    ]
    for i in range(fail_count):
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"t{i}", "name": "Bash",
                 "input": {"command": "python -m unittest tests.test_thing"}},
            ]},
        }))
        lines.append(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": [{"type": "text", "text": "FAILED (failures=1)"}],
                 "is_error": True},
            ]},
        }))
        if with_edits and i < fail_count - 1:
            lines.append(json.dumps({
                "type": "assistant",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": f"e{i}", "name": "Edit",
                     "input": {"file_path": "thing.py"}},
                ]},
            }))
            lines.append(json.dumps({
                "type": "user",
                "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"e{i}",
                     "content": [{"type": "text", "text": "ok"}]},
                ]},
            }))
    lines.append(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant",
                    "content": [{"type": "text",
                                 "text": "Still looking at it."}]},
    }))
    path = base / "transcript.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run(project: Path, state: Path, transcript: Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    return subprocess.run(
        [sys.executable, str(HOOK), "stop", "--project", str(project)],
        input=json.dumps({"transcript_path": str(transcript)}),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=environment)


class InvestigationNudgeTests(unittest.TestCase):
    def test_three_reds_with_edits_between_draw_the_nudge(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, _transcript(project, 3))
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)  # one object, or raises
            message = payload["systemMessage"]
            self.assertIn("investigation", message)
            self.assertIn("3", message)
            # Privacy: the command text never appears.
            self.assertNotIn("unittest", message)

    def test_two_reds_stay_silent(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, _transcript(project, 2))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("investigation", done.stdout)

    def test_reds_without_edits_between_are_not_a_fix_loop(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, _transcript(project, 3, with_edits=False))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("investigation", done.stdout)

    def test_an_open_incident_this_session_silences_it(self) -> None:
        with _project() as (project, state, archive):
            archive.append("incident", "the thing under investigation",
                           {"detail": "loop opened", "failure_class": None,
                            "turning_point": False})
            done = _run(project, state, _transcript(project, 3))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("investigation", done.stdout)


if __name__ == "__main__":
    unittest.main()
