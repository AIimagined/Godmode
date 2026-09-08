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
            # Thirteenth field report (obligation 9702): three sessions read
            # observed grades as "grading without execution" because the
            # done bar never named the executing form. It names it first.
            reason = payload.get("reason", "")
            self.assertIn("--verify", reason)
            self.assertLess(reason.index("--verify"), reason.index("soften"))

    def test_antigravity_hears_the_block_as_decision_continue(self) -> None:
        """Tenth field report 2026-09-05: Antigravity's Stop contract is
        {"decision": "continue", "reason": ...} to keep the agent working
        (or {} to let it stop); Claude's "block" spelling is discarded there
        and the done bar never fired."""
        with _project() as (project, state, _archive):
            with mock.patch.dict(os.environ, {"ANTIGRAVITY_AGENT": "1"}, clear=False):
                done = _run(project, state, {
                    "transcript_path": str(_transcript(project, f"All wrapped up. {DONE_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "continue", payload)
            self.assertIn("godmode claim", payload.get("reason", ""))

    def test_the_refire_passes_clean(self) -> None:
        with _project() as (project, state, _archive):
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {DONE_CLAIM}.")),
                "stop_hook_active": True})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((done.stdout or "").strip(), "")

    def test_a_recorded_done_claim_is_not_blocked(self) -> None:
        # A done claim no command can settle: recorded observed is enough.
        settled_by_reading = "The migration is complete"
        with _project() as (project, state, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            from godmode_runtime.godmode_attest import record_claim
            record_claim(archive, project, "S-test", settled_by_reading, "observed",
                         cites=["file:README.md"])
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {settled_by_reading}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            body = (done.stdout or "").strip()
            if body:
                self.assertNotEqual(json.loads(body).get("decision"), "block")

    def test_a_run_shaped_done_claim_on_an_asserted_grade_is_named_once(self) -> None:
        # Twenty-first field report (obligations 10118, 10245): "all tests
        # pass" recorded observed on a README citation was passing the bar.
        # The grade is composed from executed predicates now; an asserted
        # one is named once, with the executed check as the remedy.
        with _project() as (project, state, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            from godmode_runtime.godmode_attest import record_claim
            record_claim(archive, project, "S-test", DONE_CLAIM, "observed",
                         cites=["file:README.md"])
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {DONE_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "block")
            self.assertIn("executed check", payload["reason"])
            self.assertIn("--verify", payload["reason"])

    def test_a_run_shaped_done_claim_verified_by_an_attestation_passes(self) -> None:
        import subprocess as _sp
        import sys as _sys
        with _project() as (project, state, archive):
            from godmode_runtime.godmode_attest import open_session, record_claim, run_check
            _sp.run(["git", "init", "-q"], cwd=project, check=True)
            _sp.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                     "--allow-empty", "-m", "first"], cwd=project, check=True)
            session = open_session(archive, "S-test")
            command = [_sys.executable, "-c", "import sys; sys.exit(0)"]
            outcome = run_check(archive, session, project, "suite", command)
            record_claim(archive, project, session, DONE_CLAIM, "observed",
                         cites=[outcome["citation"]])
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, f"Done. {DONE_CLAIM}."))})
            self.assertEqual(done.returncode, 0, done.stderr)
            body = (done.stdout or "").strip()
            if body:
                self.assertNotEqual(json.loads(body).get("decision"), "block", body)

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

    def test_truncated_statement_list_names_the_remainder(self) -> None:
        # Field report 2026-09-03: "3 of those statements" with only two
        # quoted read as a counting bug in the field. The cap stays at two
        # quotes; the remainder now names itself.
        with _project() as (project, state, _archive):
            text = ("Finished. The migration is complete and all tests pass. "
                    "The importer is complete and all checks pass. "
                    "The exporter is complete and all probes pass.")
            done = _run(project, state, {
                "transcript_path": str(_transcript(project, text))})
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            self.assertEqual(payload.get("decision"), "block")
            reason = payload.get("reason", "")
            counted = int(reason.split(" of those statements")[0].rsplit(None, 1)[-1])
            if counted > 2:
                self.assertIn(f"(+{counted - 2} more)", reason)


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


class ProgressReportTests(unittest.TestCase):
    """Honest mid-task updates are not completion declarations - a
    sentence carrying its own incompleteness marker skips the gate."""

    def test_progress_update_is_not_blocked(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(
                project, "The suite is complete so far; the catalog check "
                         "is still running and the render is awaiting it.")
            done = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            self.assertNotIn('"block"', done.stdout)

    def test_plain_done_still_blocks(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(project, DONE_CLAIM)
            done = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            self.assertIn('"block"', done.stdout)


class PendingListTests(unittest.TestCase):
    """Field report on 0.3.15 day one: 'Pending list above stands' was
    blocked - describing open work is the opposite of declaring done."""

    def test_a_pending_list_reply_is_not_blocked(self) -> None:
        with _project() as (project, state, _archive):
            transcript = _transcript(
                project, "The export lane is done and shipped; the retry "
                         "queue and the webhook stay pending, and the "
                         "backfill is blocked on credentials.")
            done = _run(project, state, {
                "transcript_path": str(transcript), "session_id": "S1",
                "cwd": str(project)})
            self.assertNotIn('"block"', done.stdout)
