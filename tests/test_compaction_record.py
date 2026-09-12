"""A compaction leaves a record.

Godmode does not compact anything - the host does - so the transferable part of
the compaction problem is not where the truncation boundary falls. It is that a
compaction is a context eviction which, by definition, destroys the evidence
that it happened. After two compactions a session cannot tell you it compacted
at all, let alone twice, and every judgement it then makes about "what I have
seen so far" rests on a gap it cannot see.

The hook already receives `pre-compact` and uses it to capture in-flight work.
It did not record the event itself, so the ledger had no way to say a
compaction had occurred. This writes that record: the moment, the trigger the
host declared, and the archive sequence at the time, which is what lets a later
reader place the boundary in the timeline.

Nothing here reads transcript content. A compaction record is about the event,
not about what was evicted.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_constants import ACTION_SUBJECTS  # noqa: E402
from godmode_runtime.godmode_session_log import record_compaction  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive = Chronicle(resolve_anchor(Path(self._tmp.name)))

    def actions(self) -> list[dict]:
        return [r for r in self.archive.select(kind="action", limit=50)
                if r["subject"] == "context-compacted"]


class TheEventIsRecorded(Base):
    def test_a_compaction_writes_one_action_record(self) -> None:
        record_compaction(self.archive, session="s1", trigger="auto")
        self.assertEqual(len(self.actions()), 1)

    def test_the_subject_is_registered_vocabulary(self) -> None:
        """An unregistered subject is a rule that silently never fires."""
        self.assertIn("context-compacted", ACTION_SUBJECTS)

    def test_the_record_carries_the_trigger_the_host_declared(self) -> None:
        record_compaction(self.archive, session="s1", trigger="manual")
        self.assertEqual(self.actions()[0]["data"]["trigger"], "manual")

    def test_an_absent_trigger_is_recorded_as_unstated_not_guessed(self) -> None:
        record_compaction(self.archive, session="s1", trigger=None)
        self.assertEqual(self.actions()[0]["data"]["trigger"], "unstated")

    def test_an_unknown_trigger_is_not_stored_verbatim(self) -> None:
        """Closed enum: a host may send anything, and a free string is where a
        content leak would ride along."""
        record_compaction(self.archive, session="s1", trigger="something novel")
        self.assertEqual(self.actions()[0]["data"]["trigger"], "other")

    def test_two_compactions_are_two_records(self) -> None:
        record_compaction(self.archive, session="s1", trigger="auto")
        record_compaction(self.archive, session="s1", trigger="auto")
        self.assertEqual(len(self.actions()), 2)

    def test_the_record_places_the_boundary_in_the_timeline(self) -> None:
        """A sequence is what lets a later reader say what preceded the gap."""
        record_compaction(self.archive, session="s1", trigger="auto")
        data = self.actions()[0]["data"]
        self.assertIsInstance(data.get("at_sequence"), int)
        self.assertGreaterEqual(data["at_sequence"], 0)


class ItNeverCostsTheOperatorTheEvent(Base):
    def test_a_refusing_archive_does_not_raise(self) -> None:
        """Bookkeeping about bookkeeping must not break the compaction."""

        class Refusing:
            def append(self, *a, **k):
                raise RuntimeError("archive locked")

            def select(self, *a, **k):
                return []

        result = record_compaction(Refusing(), session="s1", trigger="auto")
        self.assertFalse(result["recorded"])
        self.assertTrue(result.get("reason"))


class NoTranscriptContentIsStored(Base):
    def test_the_record_holds_only_closed_vocabulary_and_numbers(self) -> None:
        record_compaction(self.archive, session="s1", trigger="auto")
        data = self.actions()[0]["data"]
        self.assertEqual(set(data) - {"trigger", "at_sequence", "session"}, set())


if __name__ == "__main__":
    unittest.main()
