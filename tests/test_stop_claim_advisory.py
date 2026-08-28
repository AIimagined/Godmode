"""S4: the claim gate at the message boundary (obligation 4102).

Seven field reports in one day ended "claim still unused" - the verbs wait
to be invoked. The Stop hook moves the check to the moment of claiming: a
claim-shaped sentence in the turn's final text with no record behind it
gets a systemMessage naming it and the recording command. Advisory only -
exit 0 always, silent on ordinary prose, on recorded claims, and on the
host's own re-fire (stop_hook_active).
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
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

HOOK = HOOKS / "godmode_session_hook.py"

CLAIM_SENTENCE = "The gate now blocks every force-push and prevents data loss"
PLAIN_SENTENCE = "I looked at the file and moved two functions around"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-stop-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
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


def _run(project: Path, state: Path, payload: dict) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    return subprocess.run(
        [sys.executable, str(HOOK), "stop", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, env=environment,
    )


class StopAdvisoryTests(unittest.TestCase):
    def test_an_unrecorded_claim_in_the_final_text_is_named(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, f"All done. {CLAIM_SENTENCE}.")
            done = _run(project, state, {"session_id": "s1",
                                         "transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        payload = json.loads(done.stdout)
        self.assertIn("blocks every force-push", payload["systemMessage"])
        self.assertIn("godmode claim", payload["systemMessage"])

    def test_ordinary_prose_is_silent(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, f"{PLAIN_SENTENCE}.")
            done = _run(project, state, {"session_id": "s1",
                                         "transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_a_recorded_claim_is_silent(self) -> None:
        with _project() as (project, state, archive):
            archive.append("claim", CLAIM_SENTENCE[:120],
                           {"text": CLAIM_SENTENCE, "grade": "verified",
                            "session": "s1"}, evidence=["file:x"])
            transcript = _transcript(project, f"Done. {CLAIM_SENTENCE}.")
            done = _run(project, state, {"session_id": "s1",
                                         "transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_the_hosts_re_fire_is_silent(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, f"Done. {CLAIM_SENTENCE}.")
            done = _run(project, state, {"session_id": "s1", "stop_hook_active": True,
                                         "transcript_path": str(transcript)})
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_groks_direct_last_message_is_read_without_a_transcript(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {"session_id": "s1",
                                         "lastAssistantMessage":
                                             f"Finished. {CLAIM_SENTENCE}."})
        self.assertEqual(done.returncode, 0)
        payload = json.loads(done.stdout)
        self.assertIn("systemMessage", payload)


class ClaimEchoTests(unittest.TestCase):
    """S8 (obligation 4538): the advisory's audience was the operator; the
    model that made the claim never saw it. The Stop hook parks the flagged
    sentences and the next prompt boundary delivers them to the model,
    exactly once."""

    def _prompt(self, project: Path, state: Path) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        return subprocess.run(
            [sys.executable, str(HOOK), "user-prompt", "--project", str(project)],
            input=json.dumps({"prompt": "carry on with the next task"}),
            capture_output=True, text=True, encoding="utf-8", timeout=180,
            env=environment,
        )

    def test_a_flagged_reply_is_echoed_to_the_model_once(self) -> None:
        with _project() as (project, state, archive):
            done = _run(project, state, {
                "transcript_path": str(
                    _transcript(project, CLAIM_SENTENCE))})
            self.assertEqual(done.returncode, 0, done.stderr)
            echo = archive.root / "godmode-claim-echo.json"
            self.assertTrue(echo.exists())
            first = self._prompt(project, state)
            self.assertIn("additionalContext", first.stdout)
            self.assertIn("claim-shaped", first.stdout)
            self.assertFalse(echo.exists())
            second = self._prompt(project, state)
            self.assertNotIn("additionalContext", second.stdout)

    def test_a_plain_reply_parks_nothing(self) -> None:
        with _project() as (project, state, archive):
            _run(project, state, {
                "transcript_path": str(_transcript(project, PLAIN_SENTENCE))})
            self.assertFalse((archive.root / "godmode-claim-echo.json").exists())


class BriefEchoTests(unittest.TestCase):
    """S8 addendum: Grok ignores SessionStart stdout, so the brief is
    parked and the first prompt boundary delivers it to the model once."""

    def _session_start(self, project: Path, state: Path,
                       extra_env: dict) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        environment.pop("CLAUDE_CODE_ENTRYPOINT", None)
        environment.pop("GODMODE_HOST", None)
        environment.update(extra_env)
        return subprocess.run(
            [sys.executable, str(HOOK), "session-start",
             "--project", str(project)],
            input="{}", capture_output=True, text=True, encoding="utf-8",
            timeout=180, env=environment,
        )

    def _prompt2(self, project: Path, state: Path) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        return subprocess.run(
            [sys.executable, str(HOOK), "user-prompt", "--project", str(project)],
            input=json.dumps({"prompt": "resume the work"}),
            capture_output=True, text=True, encoding="utf-8", timeout=180,
            env=environment,
        )

    def test_a_grok_session_start_parks_the_brief_and_the_prompt_delivers_it(self) -> None:
        with _project() as (project, state, archive):
            done = self._session_start(project, state,
                                       {"GROK_PLUGIN_ROOT": "C:/x"})
            self.assertEqual(done.returncode, 0, done.stderr)
            echo = archive.root / "godmode-brief-echo.json"
            self.assertTrue(echo.exists())
            first = self._prompt2(project, state)
            self.assertIn("continuity brief", first.stdout)
            self.assertIn("additionalContext", first.stdout)
            self.assertFalse(echo.exists())
            second = self._prompt2(project, state)
            self.assertNotIn("continuity brief", second.stdout)

    def test_a_bare_host_parks_nothing(self) -> None:
        with _project() as (project, state, archive):
            self._session_start(project, state, {})
            self.assertFalse(
                (archive.root / "godmode-brief-echo.json").exists())


if __name__ == "__main__":
    unittest.main()
