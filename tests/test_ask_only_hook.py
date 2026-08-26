"""`ask_only` at the pre-tool boundary, run exactly as the host runs it.

A category outside the list at R2/R3 is allowed with an `action` record
naming the silence; a listed category still asks; R4 still asks and R5
still denies whatever the list says.
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
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_sentinel import POLICY_FILENAME  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-askhook-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("session", "open", {"status": "open"})
            # `git checkout -- <file>` classifies as git-history-or-remote (R3),
            # so that is the listed category the second test exercises.
            (root / POLICY_FILENAME).write_text(
                json.dumps({"ask_only": ["worktree-discard", "git-history-or-remote"]}),
                encoding="utf-8")
            yield root, archive


def _decide(project: Path, tool: str, tool_input: dict) -> str:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow"
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return str(specific.get("permissionDecision", "allow"))


class AskOnlyHookTests(unittest.TestCase):
    def test_an_unlisted_r2_ask_is_allowed_and_recorded_as_silenced(self) -> None:
        with _project() as (root, archive):
            decision = _decide(root, "Bash", {"command": "node -e \"console.log(1)\""})
            silenced = [r for r in archive.read_events(verify=False)
                        if r.get("kind") == "action"
                        and (r.get("data") or {}).get("silenced_by") == "ask_only"]
        self.assertEqual(decision, "allow")
        self.assertEqual(len(silenced), 1, "the silence must leave a record")
        self.assertEqual(silenced[0]["data"]["category"], "interpreter-opaque-inline")

    def test_a_listed_category_still_asks(self) -> None:
        with _project() as (root, _archive):
            decision = _decide(root, "Bash", {"command": "git checkout -- notes.md"})
        self.assertEqual(decision, "ask")

    def test_r4_still_asks_whatever_the_list_says(self) -> None:
        with _project() as (root, _archive):
            decision = _decide(root, "Bash", {"command": "rm -rf build"})
        self.assertEqual(decision, "ask")


if __name__ == "__main__":
    unittest.main()
