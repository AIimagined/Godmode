"""Obligations that are the same duty in different clothes.

Field report, 2026-09-01 (second project): a version-bearing subject
("live-verify 0.7.109", "live-verify at 0.8.17") mints a NEW obligation
every bump, subject-keyed supersession never links them, and the turn
nag surfaces the corpses beside the living one - accumulating where it
should supersede. Two fixes: the nag collapses salient-term siblings to
the newest, and recording an obligation that overlaps an open one draws
an advisory naming the elder so it gets closed or superseded on the spot.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "hooks", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_session_hook import _open_obligations_touched  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-oblsib-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield archive


class SiblingCollapseTests(unittest.TestCase):
    def test_the_nag_surfaces_only_the_newest_sibling(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.7.109",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "live-verify engine version 0.8.22",
                           {"value": "run the live verify pass against the engine"})
            touched = _open_obligations_touched(
                archive, "next step is the live verify pass against the engine build")
            self.assertEqual(len(touched), 1)
            self.assertTrue(touched[0].startswith(
                "live-verify engine version 0.8.22"), touched)
            self.assertIn("muted", touched[0])

    def test_unrelated_obligations_still_both_surface(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.22",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "ledger fed per research sweep",
                           {"value": "every shared source lands in the ledger"})
            touched = _open_obligations_touched(
                archive, "ran the live-verify engine version pass and fed the "
                         "research ledger with the shared source")
            self.assertEqual(len(touched), 2)


class RecordTimeAdvisoryTests(unittest.TestCase):
    def test_recording_a_sibling_draws_the_advisory(self) -> None:
        from godmode_runtime.godmode_mistakes import obligation_sibling_advisory
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass against the engine"})
            advisory = obligation_sibling_advisory(
                archive, "live-verify engine version 0.8.22",
                "run the live verify pass against the engine")
            self.assertIn("0.8.17", advisory)
            self.assertIn("supersede", advisory)

    def test_a_closed_elder_draws_nothing(self) -> None:
        from godmode_runtime.godmode_mistakes import obligation_sibling_advisory
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass",
                            "status": "closed"})
            advisory = obligation_sibling_advisory(
                archive, "live-verify engine version 0.8.22",
                "run the live verify pass against the engine")
            self.assertIsNone(advisory)


if __name__ == "__main__":
    unittest.main()


class EchoSessionScopeTests(unittest.TestCase):
    """A parked claim echo belongs to the session that wrote the reply.

    Field report #4: after a restart, the echo nagged a NEW session about
    a sentence it never wrote and could not verify. Delivery now requires
    the same session; a mismatch deletes the parking file undelivered -
    continuity across restarts is the resume path's job.
    """

    def test_cross_session_echo_is_dropped_undelivered(self) -> None:
        import json
        import subprocess
        with _archive() as archive:
            echo = archive.root / "godmode-claim-echo.json"
            echo.write_text(json.dumps({
                "sentences": ["the guard count is 55 of 55"],
                "session": "S-old"}), encoding="utf-8")
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            environment = dict(os.environ)
            done = subprocess.run(
                [sys.executable, str(hook), "user-prompt",
                 "--project", str(_project_of(archive))],
                input=json.dumps({"prompt": "continue", "session_id": "S-new",
                                  "hook_event_name": "UserPromptSubmit"}),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=environment)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("55", done.stdout or "")
            self.assertFalse(echo.exists())

    def test_same_session_echo_still_delivers(self) -> None:
        import json
        import subprocess
        with _archive() as archive:
            echo = archive.root / "godmode-claim-echo.json"
            echo.write_text(json.dumps({
                "sentences": ["the guard count is 55 of 55"],
                "session": "S-same"}), encoding="utf-8")
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "user-prompt",
                 "--project", str(_project_of(archive))],
                input=json.dumps({"prompt": "continue", "session_id": "S-same",
                                  "hook_event_name": "UserPromptSubmit"}),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=os.environ.copy())
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("55", done.stdout or "")


def _project_of(archive) -> Path:
    # The bed project root: _archive() creates <tmp>/project and resolves
    # the anchor from it; the chronicle root sits under the state home, so
    # walk from the anchor instead of guessing.
    return Path(archive.anchor.project_root)


class RequestTurnSurfaceTests(unittest.TestCase):
    """S18: a stated-but-unactioned operator request joins the same
    per-turn surface obligations use - drip-fed mid-task asks resurface
    when a reply touches their subject, not only at handover review."""

    def test_a_related_reply_surfaces_the_open_request(self) -> None:
        import json
        import subprocess
        with _archive() as archive:
            from godmode_runtime.godmode_requests import record_request
            record_request(archive, "also sweep the engine repo and check "
                                    "parity without missing upgrades",
                           session="S-req")
            transcript = Path(archive.anchor.project_root) / "t.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "go"}}),
                json.dumps({"type": "assistant", "message": {
                    "role": "assistant", "content": [{"type": "text",
                    "text": "Finished the brand axis; the engine repo parity "
                            "sweep for upgrades is still ahead of us."}]}}),
            ]), encoding="utf-8")
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "stop",
                 "--project", str(_project_of(archive))],
                input=json.dumps({"transcript_path": str(transcript),
                                  "session_id": "S-req2"}),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=dict(os.environ))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("stated request", done.stdout or "")

    def test_a_closed_request_stays_silent(self) -> None:
        import json
        import subprocess
        with _archive() as archive:
            from godmode_runtime.godmode_requests import record_request
            record = record_request(archive, "also sweep the engine repo and "
                                             "check parity for upgrades",
                                    session="S-req")
            archive.append("request", record["subject"],
                           {"digest": record["data"]["digest"],
                            "status": "closed", "value": "done"})
            transcript = Path(archive.anchor.project_root) / "t.jsonl"
            transcript.write_text("\n".join([
                json.dumps({"type": "user", "message": {"content": "go"}}),
                json.dumps({"type": "assistant", "message": {
                    "role": "assistant", "content": [{"type": "text",
                    "text": "The engine repo parity sweep for upgrades went "
                            "well today."}]}}),
            ]), encoding="utf-8")
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "stop",
                 "--project", str(_project_of(archive))],
                input=json.dumps({"transcript_path": str(transcript),
                                  "session_id": "S-req2"}),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=dict(os.environ))
            self.assertNotIn("stated request", done.stdout or "")


class StandingObligationTests(unittest.TestCase):
    """The recorded field pair: a standing per-task obligation has no
    subject for salient matching, so it died on every long turn despite
    being recorded. A record carrying standing: true surfaces at EVERY
    stop unconditionally - and ignores the quiet posture, because an
    operator-mandated per-task duty is definition-of-done, not advisory."""

    def _stop(self, archive, session="S-standing"):
        import json
        import subprocess
        transcript = Path(archive.anchor.project_root) / "t.jsonl"
        transcript.write_text("\n".join([
            json.dumps({"type": "user", "message": {"content": "go"}}),
            json.dumps({"type": "assistant", "message": {
                "role": "assistant", "content": [{"type": "text",
                "text": "Progress on the completely unrelated widget work."}]}}),
        ]), encoding="utf-8")
        hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
        return subprocess.run(
            [sys.executable, str(hook), "stop",
             "--project", str(_project_of(archive))],
            input=json.dumps({"transcript_path": str(transcript),
                              "session_id": session}),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180, env=dict(os.environ))

    def test_a_standing_obligation_surfaces_without_any_match(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "per-task effectiveness report",
                           {"value": "one verdict paragraph after every task",
                            "standing": True})
            done = self._stop(archive)
            self.assertIn("per-task effectiveness report", done.stdout or "")

    def test_standing_survives_quiet_posture(self) -> None:
        import json
        with _archive() as archive:
            root = _project_of(archive)
            (root / ".godmode-authorization-policy.json").write_text(
                json.dumps({"nag_posture": "quiet"}), encoding="utf-8")
            archive.append("obligation", "per-task effectiveness report",
                           {"value": "one verdict paragraph after every task",
                            "standing": True})
            done = self._stop(archive)
            self.assertIn("per-task effectiveness report", done.stdout or "")

    def test_a_closed_standing_obligation_stays_silent(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "per-task effectiveness report",
                           {"value": "duty", "standing": True,
                            "status": "closed"})
            done = self._stop(archive)
            self.assertNotIn("per-task effectiveness report", done.stdout or "")
