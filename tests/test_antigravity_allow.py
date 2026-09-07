"""An Antigravity allow is spoken, never silent.

Sweep 2026-09-07 (agentmemory's Antigravity bridge, verified by them on agy
1.0.15): the Antigravity CLI treats a PreToolUse response without a
`decision` as a denial, and a bare `{}` refuses every matched call. Godmode
printed nothing on an Antigravity allow - silence is Claude's allow signal,
not Antigravity's. Both the full hook and the fast gate now answer
`{"decision": "allow"}` on that host, and the tool vocabulary the bridge
lists (view_line_range, propose_code, create_file, ...) is mapped onto the
read/edit/write kinds. Obligation 9862.
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
FAST_GATE = PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import HOST_MARKERS  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-agy-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state


def _run(script: Path, argv: list[str], payload: dict, state: Path) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment["GODMODE_STATE_HOME"] = str(state)
    environment["ANTIGRAVITY_AGENT"] = "1"
    return subprocess.run(
        [sys.executable, str(script), *argv], input=json.dumps(payload),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=environment)


def _call(project: Path, tool: str, args: dict) -> dict:
    # The nested dialect the docs describe, with the bridge's field names.
    return {"toolCall": {"name": tool, "args": args},
            "workspacePaths": [str(project)], "conversationId": "c-agy",
            "hook_event_name": "PreToolUse", "cwd": str(project)}


class SpokenAllowTests(unittest.TestCase):
    def test_the_full_hook_speaks_an_allow(self) -> None:
        with _project() as (project, state):
            done = _run(HOOK, ["pre-action", "--project", str(project)],
                        _call(project, "run_command", {"CommandLine": "git status --short"}), state)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout).get("decision"), "allow", done.stdout)

    def test_the_fast_gate_speaks_an_allow(self) -> None:
        with _project() as (project, state):
            done = _run(FAST_GATE, [], _call(project, "run_command",
                                              {"CommandLine": "git status --short"}), state)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout).get("decision"), "allow", done.stdout)

    def test_a_force_push_still_denies(self) -> None:
        with _project() as (project, state):
            done = _run(FAST_GATE, [], _call(project, "run_command",
                                              {"CommandLine": "git push --force origin main"}), state)
        self.assertEqual(json.loads(done.stdout).get("decision"), "deny", done.stdout)


class BridgeVocabularyTests(unittest.TestCase):
    def test_read_tools_from_the_bridge_are_allowed_as_reads(self) -> None:
        with _project() as (project, state):
            for tool, args in (("view_line_range", {"AbsolutePath": str(project / "notes.md")}),
                               ("grep_search", {"Query": "x", "SearchDirectory": str(project)}),
                               ("list_dir", {"DirectoryPath": str(project)})):
                with self.subTest(tool):
                    done = _run(HOOK, ["pre-action", "--project", str(project)],
                                _call(project, tool, args), state)
                    self.assertEqual(json.loads(done.stdout).get("decision"), "allow", done.stdout)

    def test_edit_tools_from_the_bridge_reach_the_fence(self) -> None:
        with _project() as (project, state):
            inside = _run(HOOK, ["pre-action", "--project", str(project)],
                          _call(project, "propose_code", {"TargetFile": str(project / "notes.md")}),
                          state)
            self.assertEqual(json.loads(inside.stdout).get("decision"), "allow", inside.stdout)
            outside = _run(HOOK, ["pre-action", "--project", str(project)],
                           _call(project, "create_file",
                                 {"AbsolutePath": str(project.parent / "elsewhere.md")}), state)
            # The scope fence asks on a host with a real ask (Antigravity has
            # one); the point here is that the bridge's write tool reached it.
            self.assertEqual(json.loads(outside.stdout).get("decision"), "ask", outside.stdout)


if __name__ == "__main__":
    unittest.main()
