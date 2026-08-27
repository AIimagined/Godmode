"""The brief says how old its last checkpoint is.

Field report (2026-08-27, another project): the session brief surfaced a
checkpoint eight days older than the project's own state file, without
saying so, and the agent read the brief as current. A checkpoint's age is
one subtraction the brief can do for the reader; past a week it also says
plainly to prefer the project's own state document if that is newer.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
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
import godmode_session_hook as hook  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-age-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            yield root, Chronicle(resolve_anchor(root))


class CheckpointAgeTests(unittest.TestCase):
    def test_a_fresh_checkpoint_reports_age_zero_and_no_note(self) -> None:
        with _project() as (root, archive):
            archive.append("checkpoint", "mid-task", {"status": "active"})
            digest = hook._resume_digest(archive, root, {})
        entry = digest["last_checkpoint"]
        self.assertEqual(entry["age_days"], 0)
        self.assertNotIn("note", entry)

    def test_an_old_checkpoint_says_its_age_and_defers_to_the_state_doc(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=timezone.utc)
        record = {"recorded_at": (now - timedelta(days=8, hours=3)).isoformat()}
        age, note = hook.checkpoint_age(record, now=now)
        self.assertEqual(age, 8)
        self.assertIn("8 days", note)
        self.assertIn("state document", note)

    def test_the_digest_names_the_projects_own_resume_doc_when_one_exists(self) -> None:
        # Field report (2026-08-28, another project): the brief carried an
        # 11-day-old checkpoint while docs/STATE.md held the current state.
        # When a project keeps such a document, the brief points at it.
        with _project() as (root, archive):
            (root / "docs").mkdir()
            (root / "docs" / "STATE.md").write_text("# State\n", encoding="utf-8")
            archive.append("checkpoint", "mid-task", {"status": "active"})
            digest = hook._resume_digest(archive, root, {})
        self.assertEqual(digest["last_checkpoint"]["resume_doc"], "docs/STATE.md")

    def test_no_resume_doc_means_no_pointer(self) -> None:
        with _project() as (root, archive):
            archive.append("checkpoint", "mid-task", {"status": "active"})
            digest = hook._resume_digest(archive, root, {})
        self.assertNotIn("resume_doc", digest["last_checkpoint"])

    def test_an_old_checkpoint_note_names_the_resume_doc(self) -> None:
        now = datetime(2026, 8, 28, tzinfo=timezone.utc)
        record = {"recorded_at": (now - timedelta(days=11)).isoformat()}
        age, note = hook.checkpoint_age(record, now=now, resume_doc="docs/STATE.md")
        self.assertEqual(age, 11)
        self.assertIn("docs/STATE.md", note)
        self.assertIn("read it first", note)

    def test_under_a_week_carries_no_note(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=timezone.utc)
        record = {"recorded_at": (now - timedelta(days=6)).isoformat()}
        age, note = hook.checkpoint_age(record, now=now)
        self.assertEqual(age, 6)
        self.assertIsNone(note)


if __name__ == "__main__":
    unittest.main()
