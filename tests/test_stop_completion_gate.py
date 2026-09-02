"""The completion gate at the Stop boundary: done is blocked once, not argued.

An advisory the model reads next turn is the right posture for ordinary
claim discipline. A DONE declaration resting on an unrecorded claim is
different: the turn is ending, the operator is about to trust it, and
next-turn advice arrives after the belief has landed. The stop hook now
blocks that one shape - a done/fixed/pass-shaped sentence among the
unrecorded claims - with the exact recording commands as the corrective
reason. Bounded by construction: the host re-fires the stop with
stop_hook_active set, and that path has always returned clean, so the
block happens at most once per stop. Everything else stays advisory.
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

DONE_CLAIM = "The migration is complete and all tests pass"
# is_claim-shaped (promise verb) but NOT done-shaped - the advisory path.
PLAIN_CLAIM = "The gate prevents accidental writes outside the tree"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-stopgate-") as temporary:
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
        encoding="utf-8", errors="replace", timeout=180, env=environment)


class CompletionGateTests(unittest.TestCase):
    def test_an_unrecorded_done_claim_blocks_once(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"All wrapped up. {DONE_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "block")
            self.assertIn("godmode claim", payload.get("reason", ""))

    def test_the_refire_passes_clean(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {DONE_CLAIM}.")),
                "stop_hook_active": True})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((done.stdout or "").strip(), "")

    def test_a_recorded_done_claim_is_not_blocked(self) -> None:
        with _project() as (project, state, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            from godmode_runtime.godmode_attest import record_claim
            record_claim(archive, project, "S-test", DONE_CLAIM, "observed",
                         cites=["file:README.md"])
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {DONE_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            body = (done.stdout or "").strip()
            if body:
                self.assertNotEqual(json.loads(body).get("decision"), "block")

    def test_an_ordinary_unrecorded_claim_stays_advisory(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Progress: {PLAIN_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertNotEqual(payload.get("decision"), "block")
            self.assertIn("claim-shaped", payload.get("systemMessage", ""))

    def test_the_block_is_one_json_object(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Finished. {DONE_CLAIM}."))})
            json.loads(done.stdout)  # exactly one object, or raises


if __name__ == "__main__":
    unittest.main()


class SoftenedDodgeTests(unittest.TestCase):
    """'A softened rewording would have passed the same gate' - the
    re-fire after a block, with no claim recorded since, says so."""

    def test_reword_without_claim_is_named_on_refire(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, DONE_CLAIM)
            blocked = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            self.assertIn('"block"', blocked.stdout)
            refire = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project), "stop_hook_active": True})
            self.assertIn("passed by rewording", refire.stdout)

    def test_claim_between_block_and_refire_is_clean(self) -> None:
        with _project() as (project, state, archive):
            transcript = _transcript(project, DONE_CLAIM)
            _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            archive.append("claim", "migration complete",
                           {"text": DONE_CLAIM, "grade": "observed",
                            "session": "S1"})
            refire = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project), "stop_hook_active": True})
            self.assertNotIn("passed by rewording", refire.stdout)

    def test_second_refire_is_silent(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, DONE_CLAIM)
            _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            first = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project), "stop_hook_active": True})
            second = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project), "stop_hook_active": True})
            self.assertIn("passed by rewording", first.stdout)
            self.assertNotIn("passed by rewording", second.stdout)
