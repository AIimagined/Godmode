"""R1 ("enforce harm, advise on quality"): the project mode switch.

`advise` (the default) leaves every quality-class Stop gate advisory,
shown at most once per session per gate; `strict` is today's exact
behaviour, unchanged. The harm gates on the pre-action path (tag/release/
push checks) read neither mode and decide identically either way - that
parity is asserted directly, not inferred from the Stop-side tests.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_projectmode import project_mode  # noqa: E402
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import scrubbed_env  # noqa: E402

DONE_CLAIM = "The migration is complete and all tests pass"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-mode-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
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


def _run_hook(event: str, project: Path, state: Path, payload: dict) -> subprocess.CompletedProcess:
    environment = scrubbed_env(GODMODE_STATE_HOME=str(state))
    return subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


def _cli(project: Path, state: Path, *args: str) -> subprocess.CompletedProcess:
    environment = scrubbed_env(GODMODE_STATE_HOME=str(state))
    return subprocess.run(
        [sys.executable, "-B", str(GODMODE_CLI), "--project", str(project), *args],
        capture_output=True, text=True, env=environment)


class DefaultModeTests(unittest.TestCase):
    def test_default_mode_is_advise(self) -> None:
        with _project() as (_project_dir, _state, archive):
            self.assertEqual(project_mode(archive), "advise")


class ConfigModeCliTests(unittest.TestCase):
    def test_mode_strict_round_trips(self) -> None:
        with _project() as (project, state, archive):
            out = _cli(project, state, "config", "mode")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout), {"mode": "advise"})

            out = _cli(project, state, "config", "mode", "strict")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout), {"mode": "strict"})

            out = _cli(project, state, "config", "mode")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout), {"mode": "strict"})
            self.assertEqual(project_mode(archive), "strict")


class StopAdviseModeTests(unittest.TestCase):
    def test_advise_mode_turns_the_done_bar_into_advice_shown_once(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, f"All wrapped up. {DONE_CLAIM}.")
            first = _run_hook("stop", project, state,
                              {"transcript_path": str(transcript), "session_id": "S1"})
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotIn('"decision"', first.stdout)
            self.assertIn("godmode (advice):", first.stdout)
            self.assertIn("THE DONE BAR", first.stdout)

            second = _run_hook("stop", project, state,
                               {"transcript_path": str(transcript), "session_id": "S1"})
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((second.stdout or "").strip(), "")

    def test_strict_mode_still_blocks(self) -> None:
        with _project() as (project, state, _archive):
            out = _cli(project, state, "config", "mode", "strict")
            self.assertEqual(out.returncode, 0, out.stderr)
            transcript = _transcript(project, f"All wrapped up. {DONE_CLAIM}.")
            done = _run_hook("stop", project, state,
                             {"transcript_path": str(transcript), "session_id": "S2"})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "block")


class HarmGateParityTests(unittest.TestCase):
    def test_a_pre_action_push_decision_is_identical_in_both_modes(self) -> None:
        with _project() as (project, state, _archive):
            payload = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin main"},
                "cwd": str(project),
            }
            advise = _run_hook("pre-action", project, state, payload)
            self.assertEqual(advise.returncode, 0, advise.stderr)

            out = _cli(project, state, "config", "mode", "strict")
            self.assertEqual(out.returncode, 0, out.stderr)
            strict = _run_hook("pre-action", project, state, payload)
            self.assertEqual(strict.returncode, 0, strict.stderr)

            self.assertEqual(advise.stdout, strict.stdout)


if __name__ == "__main__":
    unittest.main()
