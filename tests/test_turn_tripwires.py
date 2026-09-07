"""Two turn-scoped instruments: a paid-iteration tripwire and a turn baseline.

Nineteenth field report (2026-09-07): nothing stopped six paid iterations
on one lane; the operator's own rule did. With `verify --offline` recording
connection findings, the checks a session has had blocked for dialling out
are counted against a declared ceiling (`paid_iterations` in
`.godmode-ceilings.json`, default 3) and the Stop notices say so once.

Companion, from the sweep the same day: two plugins in the research ledger
take a git baseline at each prompt and diff at Stop, so only the turn's own
change is judged. Godmode records `git stash create` (or HEAD) at every
prompt boundary and, at Stop, names the files changed since it when no check
and no claim landed in between. Obligation 9868.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
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

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from _host_env import HOST_MARKERS  # noqa: E402

_spec = importlib.util.spec_from_file_location("godmode_session_hook", HOOK)
hook = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hook)


def _git(project: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           *args], cwd=str(project), check=True, capture_output=True,
                          text=True).stdout.strip()


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-turnwire-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        _git(root, "init", "-q")
        (root / "app.py").write_text("x = 1\n", encoding="utf-8")
        _git(root, "add", "app.py")
        _git(root, "commit", "-q", "-m", "init")
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, state, archive


def _fire(event: str, project: Path, state: Path, payload: dict) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment["GODMODE_STATE_HOME"] = str(state)
    environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    return subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment)


def _blocked_offline_check(archive: Chronicle, session: str, n: int) -> None:
    for i in range(n):
        archive.append("attestation", f"check:paid-{i}", {
            "status": "blocked", "session": session,
            "result": "exit 0: 2 connection attempt(s) under --offline, first socket.getaddrinfo"})


class PaidIterationTripwireTests(unittest.TestCase):
    def test_three_blocked_offline_checks_trip_the_wire_once(self) -> None:
        with _project() as (project, _state, archive):
            _blocked_offline_check(archive, "S-paid", 3)
            first = hook._tripwire_nudges(archive, "S-paid", project)
            self.assertTrue(any("paid" in n and "3" in n for n in first), first)
            second = hook._tripwire_nudges(archive, "S-paid", project)
            self.assertFalse(any("paid" in n for n in second), second)

    def test_below_the_ceiling_is_quiet_and_the_ceiling_is_declarable(self) -> None:
        with _project() as (project, _state, archive):
            _blocked_offline_check(archive, "S-two", 2)
            self.assertFalse(any("paid" in n for n in hook._tripwire_nudges(archive, "S-two", project)))
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"paid_iterations": 6}), encoding="utf-8")
            _blocked_offline_check(archive, "S-five", 5)
            self.assertFalse(any("paid" in n for n in hook._tripwire_nudges(archive, "S-five", project)))


class TurnBaselineTests(unittest.TestCase):
    def test_a_prompt_records_the_baseline_and_a_stop_names_the_unchecked_change(self) -> None:
        with _project() as (project, state, archive):
            prompt = _fire("user-prompt", project, state, {
                "hook_event_name": "UserPromptSubmit", "prompt": "change app",
                "session_id": "S-turn", "cwd": str(project)})
            self.assertEqual(prompt.returncode, 0, prompt.stderr)
            baseline = archive.root / "godmode-turn-baseline.json"
            self.assertTrue(baseline.exists())
            parked = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertEqual(parked.get("session"), "S-turn")
            self.assertRegex(parked.get("sha", ""), r"^[0-9a-f]{40}$")
            (project / "app.py").write_text("x = 2\n", encoding="utf-8")
            transcript = project.parent / "t.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "change app"}}),
                json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "text", "text": "I changed the value."}]}})]), encoding="utf-8")
            stop = _fire("stop", project, state, {
                "hook_event_name": "Stop", "session_id": "S-turn",
                "transcript_path": str(transcript), "cwd": str(project)})
            body = json.loads(stop.stdout) if stop.stdout.strip() else {}
            self.assertIn("changed this turn", body.get("systemMessage", ""), body)
            self.assertIn("app.py", body.get("systemMessage", ""))
            self.assertFalse(baseline.exists(), "consumed once")

    def test_a_check_recorded_after_the_baseline_keeps_the_stop_quiet(self) -> None:
        with _project() as (project, state, archive):
            _fire("user-prompt", project, state, {
                "hook_event_name": "UserPromptSubmit", "prompt": "change app",
                "session_id": "S-ok", "cwd": str(project)})
            (project / "app.py").write_text("x = 3\n", encoding="utf-8")
            archive.append("attestation", "check:unit", {
                "status": "ran", "session": "S-ok", "result": "exit 0: ok"})
            transcript = project.parent / "t2.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "change app"}}),
                json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "text", "text": "I changed the value."}]}})]), encoding="utf-8")
            stop = _fire("stop", project, state, {
                "hook_event_name": "Stop", "session_id": "S-ok",
                "transcript_path": str(transcript), "cwd": str(project)})
            body = json.loads(stop.stdout) if stop.stdout.strip() else {}
            self.assertNotIn("changed this turn", body.get("systemMessage", ""), body)


if __name__ == "__main__":
    unittest.main()
