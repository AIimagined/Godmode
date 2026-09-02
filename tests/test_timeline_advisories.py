"""Marginal-return advisories from the session's own timeline.

The investigation nudge covers one shape (reds with edits between - a fix
loop). Two more shapes carry zero marginal information and get their own
single sentence at the stop:

- green streak: the same command passing three or more consecutive times
  with no mutation between the passes - re-running an already-green check
  cannot add information; the honest next step is recording the claim it
  supports.
- stale retry: a command that failed, then ran again with NO mutation
  since the failure - nothing changed, so the verdict cannot change.
  The complement of the fix-loop wire (which requires edits between).

Both are counts-only (the timeline stores digests), receipt-bounded to
once per session per shape, and accumulate into the stop hook's single
printed object.
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
    with tempfile.TemporaryDirectory(prefix="godmode-tladv-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state, archive


def _bash_call(index: int, command: str, ok: bool) -> list[str]:
    return [
        json.dumps({"type": "assistant", "message": {
            "role": "assistant", "content": [
                {"type": "tool_use", "id": f"t{index}", "name": "Bash",
                 "input": {"command": command}}]}}),
        json.dumps({"type": "user", "message": {
            "role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{index}",
                 "content": [{"type": "text", "text": "out"}],
                 "is_error": not ok}]}}),
    ]


def _edit_call(index: int) -> list[str]:
    return [
        json.dumps({"type": "assistant", "message": {
            "role": "assistant", "content": [
                {"type": "tool_use", "id": f"e{index}", "name": "Edit",
                 "input": {"file_path": "thing.py"}}]}}),
        json.dumps({"type": "user", "message": {
            "role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"e{index}",
                 "content": [{"type": "text", "text": "ok"}]}]}}),
    ]


def _write(base: Path, lines: list[str]) -> Path:
    closing = json.dumps({"type": "assistant", "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Still working on it."}]}})
    path = base / "transcript.jsonl"
    path.write_text("\n".join([*lines, closing]), encoding="utf-8")
    return path


def _run(project: Path, state: Path, transcript: Path,
         session: str = "S-tladv") -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    return subprocess.run(
        [sys.executable, str(HOOK), "stop", "--project", str(project)],
        input=json.dumps({"transcript_path": str(transcript),
                          "session_id": session}),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=environment)


def _message(done: subprocess.CompletedProcess) -> str:
    body = (done.stdout or "").strip()
    if not body:
        return ""
    return str(json.loads(body).get("systemMessage", ""))


class GreenStreakTests(unittest.TestCase):
    def test_three_consecutive_passes_draw_the_nudge(self) -> None:
        with _project() as (project, state, _archive):
            lines: list[str] = []
            for i in range(3):
                lines += _bash_call(i, "python -m unittest tests.test_thing", ok=True)
            done = _run(project, state, _write(project, lines))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("GREEN ADDS NOTHING", _message(done))

    def test_passes_with_a_mutation_between_stay_silent(self) -> None:
        # Edit between passes = re-verification after a change: information.
        with _project() as (project, state, _archive):
            lines = _bash_call(0, "python -m unittest tests.test_thing", ok=True)
            lines += _edit_call(0)
            lines += _bash_call(1, "python -m unittest tests.test_thing", ok=True)
            lines += _bash_call(2, "python -m unittest tests.test_thing", ok=True)
            done = _run(project, state, _write(project, lines))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("GREEN ADDS NOTHING", _message(done))

    def test_two_passes_stay_silent(self) -> None:
        with _project() as (project, state, _archive):
            lines: list[str] = []
            for i in range(2):
                lines += _bash_call(i, "python -m unittest tests.test_thing", ok=True)
            done = _run(project, state, _write(project, lines))
            self.assertNotIn("GREEN ADDS NOTHING", _message(done))

    def test_once_per_session(self) -> None:
        with _project() as (project, state, _archive):
            lines: list[str] = []
            for i in range(3):
                lines += _bash_call(i, "python -m unittest tests.test_thing", ok=True)
            transcript = _write(project, lines)
            _run(project, state, transcript)
            again = _run(project, state, transcript)
            self.assertNotIn("green", _message(again))


class StaleRetryTests(unittest.TestCase):
    def test_failure_rerun_without_mutation_draws_the_nudge(self) -> None:
        with _project() as (project, state, _archive):
            lines = _bash_call(0, "python -m unittest tests.test_thing", ok=False)
            lines += _bash_call(1, "python -m unittest tests.test_thing", ok=False)
            done = _run(project, state, _write(project, lines))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("cannot be different", _message(done))

    def test_failure_rerun_after_mutation_is_a_legitimate_retry(self) -> None:
        with _project() as (project, state, _archive):
            lines = _bash_call(0, "python -m unittest tests.test_thing", ok=False)
            lines += _edit_call(0)
            lines += _bash_call(1, "python -m unittest tests.test_thing", ok=False)
            done = _run(project, state, _write(project, lines))
            self.assertNotIn("cannot be different", _message(done))

    def test_single_failure_stays_silent(self) -> None:
        with _project() as (project, state, _archive):
            lines = _bash_call(0, "python -m unittest tests.test_thing", ok=False)
            done = _run(project, state, _write(project, lines))
            self.assertNotIn("cannot be different", _message(done))


if __name__ == "__main__":
    unittest.main()
