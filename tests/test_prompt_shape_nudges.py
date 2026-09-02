"""The prompt's own shape names the verb, once per shape per session.

"fix the login bug" is a prompt that will end in a fix claim; "push it"
is a prompt that will end at the release boundary. The user-prompt hook
already reads every prompt, so the moment the shape appears it can name
the one godmode verb that moment demands - as delivered context the
MODEL sees, not operator-facing stderr. Receipt-bounded per shape per
session, silent for neutral prompts, and the whole event prints at most
one JSON object (the stop hook's single-print law, learned the hard way,
applies here identically).
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
    with tempfile.TemporaryDirectory(prefix="godmode-promptshape-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state


def _fire(project: Path, state: Path, prompt: str,
          session: str = "S-promptshape") -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    payload = {"prompt": prompt, "session_id": session,
               "hook_event_name": "UserPromptSubmit"}
    return subprocess.run(
        [sys.executable, str(HOOK), "user-prompt", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


def _context(completed: subprocess.CompletedProcess) -> str:
    body = (completed.stdout or "").strip()
    if not body:
        return ""
    parsed = json.loads(body)  # raises on two concatenated objects
    return str((parsed.get("hookSpecificOutput") or {}).get(
        "additionalContext", ""))


class PromptShapeTests(unittest.TestCase):
    def test_fix_shaped_prompt_names_the_incident_verb(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "fix the login bug, it keeps failing")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("incident", _context(done))

    def test_ship_shaped_prompt_names_the_preflight(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "looks good, push it and cut a release")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("preflight", _context(done))

    def test_same_shape_speaks_once_per_session(self) -> None:
        with _project() as (project, state):
            _fire(project, state, "fix the login bug")
            again = _fire(project, state, "still broken, fix it properly")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertNotIn("incident", _context(again))

    def test_neutral_prompt_is_silent(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "explain how the parser handles comments")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(_context(done), "")


if __name__ == "__main__":
    unittest.main()


class NewShapeTests(unittest.TestCase):
    def test_review_shaped_prompt_names_the_verdict_verb(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "can you review the parser changes")
            self.assertIn("verdict", _context(done))

    def test_done_check_names_the_frontier(self) -> None:
        with _project() as (project, state):
            done = _fire(project, state, "is it done? anything pending")
            self.assertIn("status remaining", _context(done))


class CorrectionShapeTests(unittest.TestCase):
    """The operator's catch is the largest lesson source in every field
    corpus - the nudge fires at the catch-moment, once per session."""

    @classmethod
    def setUpClass(cls) -> None:
        import sys as _sys
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in _sys.path:
            _sys.path.insert(0, tests_dir)

    def test_correction_prompt_draws_the_nudge(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_precheck import prompt_shape_nudge
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            text = prompt_shape_nudge(
                archive, "why did you miss the second config file?", "S1")
            self.assertIsNotNone(text)
            self.assertIn("caught a miss", text)

    def test_ordinary_prompt_is_silent(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_precheck import prompt_shape_nudge
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(prompt_shape_nudge(
                archive, "please add a config file for the parser", "S1"))

    def test_second_correction_same_session_is_silent(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_precheck import prompt_shape_nudge
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = prompt_shape_nudge(archive, "you forgot the tests", "S1")
            second = prompt_shape_nudge(archive, "that's wrong again", "S1")
            self.assertIsNotNone(first)
            self.assertIsNone(second)
