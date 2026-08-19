"""B4-4: a counts-only "where you left off" digest at session start, and an
interrupted-intent record when a session dies with declared work in flight.

The continuity brief already carries records; what it never answered was the
first question a resuming agent actually asks - was I mid-task? The digest
answers with counts (last checkpoint, open next-actions, unattested HARD
rules, last verdicts), marks entries whose file refs no longer resolve as
stale rather than repeating them as truth, and surfaces an interruption
recorded by SessionEnd/PreCompact ahead of everything else.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

observe = importlib.import_module("test_observe_mode")


def _lifecycle(project: Path, event: str, payload: dict) -> dict:
    done = subprocess.run(
        [sys.executable, str(HOOK), event, "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
    )
    body = (done.stdout or "").strip()
    return json.loads(body) if body else {}


def _interrupted_records(archive) -> list:
    archive._events_cache_key = None
    return [r for r in archive.read_events()
            if r["kind"] == "action" and r["subject"] == "interrupted-intent"]


class InterruptionIsCaptured(unittest.TestCase):
    def test_a_session_ending_with_open_next_actions_records_the_intent(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "midway through the fence work",
                           {"status": "active",
                            "next": ["finish the fence tests", "run the suite"]},
                           evidence=[])
            _lifecycle(project, "session-end", {"summary": ""})
            records = _interrupted_records(archive)
            self.assertEqual(len(records), 1)
            data = records[0]["data"]
            self.assertEqual(data["open_obligations"], 2)
            self.assertIs(data["interrupted"], True)
            # counts + hashes only, never the obligation text
            self.assertNotIn("finish the fence tests", json.dumps(data))
            for value in data.get("subject_hashes", []):
                self.assertRegex(value, r"^[0-9a-f]{16}$")

    def test_a_clean_session_end_records_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "all done",
                           {"status": "complete", "next": []}, evidence=[])
            _lifecycle(project, "session-end", {"summary": ""})
            self.assertEqual(_interrupted_records(archive), [])

    def test_pre_compact_captures_too(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "mid-task",
                           {"status": "active", "next": ["keep going"]},
                           evidence=[])
            _lifecycle(project, "pre-compact", {})
            self.assertEqual(len(_interrupted_records(archive)), 1)

    def test_an_uninitialized_project_stays_silent(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _lifecycle(project, "session-end", {"summary": ""})
            self.assertFalse(archive.initialized())


class ResumeDigestInTheBrief(unittest.TestCase):
    def _brief(self, project: Path) -> dict:
        brief = observe._session_start(project)
        context = brief["hookSpecificOutput"]["additionalContext"]
        _prefix, _, payload = context.partition("\n")
        return json.loads(payload)

    def test_the_digest_carries_the_resume_counts(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "midway",
                           {"status": "active", "next": ["a", "b"]},
                           evidence=[])
            brief = self._brief(project)
            digest = brief["resume"]
            self.assertEqual(digest["last_checkpoint"]["subject"], "midway")
            self.assertEqual(digest["last_checkpoint"]["status"], "active")
            self.assertEqual(digest["open_obligations"], 2)
            self.assertIn("unattested_hard_rules", digest)

    def test_an_interruption_is_surfaced_on_the_next_start(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "mid-task",
                           {"status": "active", "next": ["keep going"]},
                           evidence=[])
            _lifecycle(project, "session-end", {"summary": ""})
            brief = self._brief(project)
            interrupted = brief["resume"]["interrupted"]
            self.assertEqual(interrupted["open_obligations"], 1)

    def test_a_checkpoint_resolved_since_does_not_resurface_the_interruption(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("checkpoint", "mid-task",
                           {"status": "active", "next": ["keep going"]},
                           evidence=[])
            _lifecycle(project, "session-end", {"summary": ""})
            archive._events_cache_key = None
            archive.append("checkpoint", "picked back up",
                           {"status": "complete", "next": []}, evidence=[])
            brief = self._brief(project)
            self.assertNotIn("interrupted", brief["resume"])

    def test_a_missing_file_ref_marks_the_checkpoint_stale(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "notes.txt").write_text("here", encoding="utf-8")
            archive.append("checkpoint", "anchored to files",
                           {"status": "active", "next": ["x"]},
                           evidence=["file:notes.txt", "file:gone.txt"])
            brief = self._brief(project)
            entry = brief["resume"]["last_checkpoint"]
            self.assertIs(entry["stale"], True)
            self.assertEqual(entry["stale_refs"], 1)

    def test_a_fresh_archive_has_no_digest_noise(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            brief = self._brief(project)
            digest = brief.get("resume", {})
            self.assertNotIn("last_checkpoint", digest)
            self.assertNotIn("interrupted", digest)


if __name__ == "__main__":
    unittest.main()
