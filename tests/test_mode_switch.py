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


CLAIM_SENTENCE = "The gate now blocks every force-push and prevents data loss"
POST_EDIT = PLUGIN_ROOT / "hooks" / "godmode_post_edit.py"


class LeanTurnTests(unittest.TestCase):
    """R11: outside strict mode an ordinary turn carries little hook text.
    Strict mode keeps the full output (pinned by the older suites)."""

    def _stop(self, project: Path, state: Path, text: str, session: str = "s1") -> str:
        transcript = _transcript(project, text)
        done = _run_hook("stop", project, state, {"session_id": session,
                                                  "transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def _prompt(self, project: Path, state: Path, session: str = "s1") -> str:
        done = _run_hook("user-prompt", project, state, {
            "session_id": session, "prompt": "thanks, continue",
            "hook_event_name": "UserPromptSubmit"})
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_an_unsupported_claim_reaches_the_model_once_and_nowhere_else(self) -> None:
        with _project() as (project, state, _archive):
            stop = self._stop(project, state, f"{CLAIM_SENTENCE}.")
            self.assertNotIn("force-push", stop)
            first = self._prompt(project, state)
            context = json.loads(first)["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(context.count("force-push"), 1)
            self.assertEqual(self._prompt(project, state).strip(), "")

    def test_an_open_ask_is_named_only_in_strict_mode(self) -> None:
        from godmode_runtime.godmode_projectmode import set_project_mode
        from godmode_runtime.godmode_requests import record_request
        reply = "Looked at the deployment pipeline timeout; nothing else touched."
        for mode, expected in (("advise", False), ("strict", True)):
            with self.subTest(mode=mode), _project() as (project, state, archive):
                set_project_mode(archive, mode)
                record_request(archive, "please investigate the flaky deployment pipeline "
                                        "timeout across staging clusters tonight", session="s1")
                shown = self._stop(project, state, reply) + self._prompt(project, state)
                self.assertEqual("operator ask" in shown, expected, shown)

    def _brief(self, project: Path, state: Path, session: str) -> dict:
        done = _run_hook("session-start", project, state, {
            "session_id": session, "hook_event_name": "SessionStart", "source": "startup"})
        self.assertEqual(done.returncode, 0, done.stderr)
        context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        return json.loads(context.splitlines()[1])

    def test_the_brief_is_lean_and_the_doctrine_rides_once_per_project(self) -> None:
        with _project() as (project, state, _archive):
            first = self._brief(project, state, "s1")
            self.assertIn("TWO-REVERSALS", first["doctrine"])
            self.assertIn("red_flags", first)
            for section in ("ledger", "laws", "next_actions"):
                self.assertNotIn(section, first)
            self.assertIn("open_obligations", first["resume"])
            self.assertIn("godmode resume", first["resume"]["more"])
            second = self._brief(project, state, "s2")
            self.assertNotIn("TWO-REVERSALS", second["doctrine"])
            self.assertNotIn("red_flags", second)

    def test_strict_mode_keeps_the_full_brief(self) -> None:
        from godmode_runtime.godmode_projectmode import set_project_mode
        with _project() as (project, state, archive):
            set_project_mode(archive, "strict")
            self._brief(project, state, "s1")
            second = self._brief(project, state, "s2")
            self.assertIn("TWO-REVERSALS", second["doctrine"])
            self.assertIn("ledger", second)
            self.assertIn("laws", second)

    def test_resume_carries_what_the_brief_left_out(self) -> None:
        with _project() as (project, state, _archive):
            done = _cli(project, state, "resume")
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertIn("ledger", payload)
            self.assertIn("laws", payload)

    def test_post_edit_quality_is_one_summary_per_session(self) -> None:
        with _project() as (project, state, _archive):
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"post_edit_quality": True}), encoding="utf-8")
            doc = project / "notes.md"
            doc.write_text("See C:\\Users\\someone\\x for it.\n", encoding="utf-8")

            def edit(session: str) -> str:
                done = subprocess.run(
                    [sys.executable, str(POST_EDIT)], input=json.dumps({
                        "hook_event_name": "PostToolUse", "tool_name": "Edit",
                        "session_id": session, "cwd": str(project),
                        "tool_input": {"file_path": str(doc)}}),
                    capture_output=True, text=True, encoding="utf-8", timeout=120,
                    env=scrubbed_env(GODMODE_STATE_HOME=str(state)))
                self.assertEqual(done.returncode, 0, done.stderr)
                return done.stdout

            first = edit("s1")
            self.assertIn("local-path", first)
            self.assertIn("once per session", first)
            self.assertNotIn("local-path", edit("s1"))
            self.assertIn("local-path", edit("s2"))


if __name__ == "__main__":
    unittest.main()
