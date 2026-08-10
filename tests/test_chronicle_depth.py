"""Depth tests for the chronicle: O(1) append head cache, dedupe, and expunge.

WHY: the hash chain is the product's integrity story. These tests prove that the
append fast path (head cache) never weakens full verification, that dedupe never
writes and never crosses subjects, and that expunge erases secret payloads from
disk entirely while leaving a verifiable, auditable chain behind.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


class HeadCacheTests(unittest.TestCase):
    def test_append_maintains_head_matching_full_verification(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(3):
                archive.append("decision", f"subject-{index}", {"value": index}, evidence=[])
            head = json.loads(archive.head.read_text(encoding="utf-8"))
            verified = archive.verify()
            self.assertEqual(head["sequence"], verified["records"])
            self.assertEqual(head["record_hash"], verified["head_hash"])

    def test_append_after_head_deletion_still_works_and_rebuilds(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            archive.head.unlink()
            record = archive.append("lesson", "guard", {"value": "verify"}, evidence=[])
            self.assertEqual(record["sequence"], 2)
            self.assertTrue(archive.head.is_file())
            head = json.loads(archive.head.read_text(encoding="utf-8"))
            self.assertEqual(head["sequence"], 2)
            self.assertEqual(head["record_hash"], record["record_hash"])
            self.assertTrue(archive.verify()["valid"])

    def test_append_after_head_corruption_falls_back_to_full_scan(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            archive.head.write_text("{not json", encoding="utf-8")
            record = archive.append("lesson", "guard", {"value": "held"}, evidence=[])
            self.assertEqual(record["sequence"], 2)
            head = json.loads(archive.head.read_text(encoding="utf-8"))
            self.assertEqual(head["record_hash"], record["record_hash"])
            self.assertTrue(archive.verify()["valid"])

    def test_stale_head_does_not_fork_the_chain(self) -> None:
        # Crash simulation: a record file exists that the head cache never saw.
        # The fast path must refuse the stale head and fall back, or the next
        # append would reuse a sequence number and fork the chain.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "one", {"value": 1}, evidence=[])
            stale = archive.head.read_text(encoding="utf-8")
            archive.append("decision", "two", {"value": 2}, evidence=[])
            archive.head.write_text(stale, encoding="utf-8")
            record = archive.append("decision", "three", {"value": 3}, evidence=[])
            self.assertEqual(record["sequence"], 3)
            self.assertTrue(archive.verify()["valid"])

    def test_mid_chain_tamper_is_caught_by_verify_even_though_append_skips_it(self) -> None:
        # The equivalence proof for the O(1) path: append no longer re-reads
        # history, so a mid-chain tamper does not stop new writes -- but full
        # verification (verify()/doctor) still catches it. The fast path trades
        # early detection on write, never detection itself.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(3):
                archive.append("decision", f"subject-{index}", {"value": index}, evidence=[])
            first = archive.event_paths()[0]
            payload = json.loads(first.read_text(encoding="utf-8"))
            payload["data"]["value"] = "altered"
            first.write_text(json.dumps(payload), encoding="utf-8")

            appended = archive.append("lesson", "post-tamper", {"value": "x"}, evidence=[])
            self.assertEqual(appended["sequence"], 4)
            with self.assertRaises(ArchiveError):
                archive.verify()

    def test_append_reads_a_bounded_number_of_records_regardless_of_history(self) -> None:
        # The deterministic O(1) proof, immune to machine noise: on a 200-record
        # chain the old append re-read every record file (200+ reads); the head
        # fast path reads only the head hint and the last record. A read budget
        # cannot be gamed by a fast disk the way a wall-clock ceiling can.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(200):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            original = Chronicle._read_json
            reads: list[str] = []

            def counting(path):
                reads.append(path.name)
                return original(path)

            with mock.patch.object(Chronicle, "_read_json", staticmethod(counting)):
                archive.append("action", "measured", {"value": "tail"}, evidence=[])
            record_reads = [name for name in reads if name.endswith(".godmode.json")]
            self.assertLessEqual(
                len(record_reads), 2,
                f"append on a 200-record chain read {len(record_reads)} record files",
            )
            self.assertTrue(archive.verify()["valid"])

    def test_append_cost_does_not_grow_with_history(self) -> None:
        # Generous ceiling: 200 appends took 22.65s under the old O(history)
        # reverify-per-write on this class of machine; the head cache keeps the
        # steady-state cost flat at a few milliseconds. The assertion scales the
        # MEDIAN per-append cost, because a wall-clock total on shared hardware
        # measures antivirus and disk-queue spikes, not the algorithm -- the
        # median still fails for O(history) appends, whose typical cost grows
        # with every record, but tolerates a few unlucky flushes.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            timings: list[float] = []
            for index in range(200):
                started = time.monotonic()
                archive.append("action", f"bench-{index}", {"value": index}, evidence=[])
                timings.append(time.monotonic() - started)
            timings.sort()
            median = timings[len(timings) // 2]
            self.assertLess(
                median * 200, 10.0,
                f"typical append cost projects to {median * 200:.2f}s per 200 records",
            )
            self.assertEqual(archive.verify()["records"], 200)


class DedupeTests(unittest.TestCase):
    def test_dedupe_returns_prior_record_and_writes_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            original = archive.append("decision", "storage", {"value": "local"}, evidence=[])
            duplicate = archive.append(
                "decision", "storage", {"value": "local"}, evidence=[], dedupe=True
            )
            self.assertTrue(duplicate["deduplicated"])
            self.assertEqual(duplicate["record_hash"], original["record_hash"])
            self.assertEqual(duplicate["sequence"], original["sequence"])
            self.assertEqual(len(archive.event_paths()), 1)
            # The marker is presentation-only: nothing on disk carries it.
            on_disk = json.loads(archive.event_paths()[0].read_text(encoding="utf-8"))
            self.assertNotIn("deduplicated", on_disk)
            self.assertTrue(archive.verify()["valid"])

    def test_dedupe_never_crosses_subjects(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            other = archive.append(
                "decision", "retention", {"value": "local"}, evidence=[], dedupe=True
            )
            self.assertNotIn("deduplicated", other)
            self.assertEqual(len(archive.event_paths()), 2)

    def test_dedupe_only_considers_the_most_recent_matching_record(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            archive.append("decision", "storage", {"value": "remote"}, evidence=[])
            appended = archive.append(
                "decision", "storage", {"value": "local"}, evidence=[], dedupe=True
            )
            self.assertNotIn("deduplicated", appended)
            self.assertEqual(len(archive.event_paths()), 3)

    def test_default_behaviour_is_unchanged(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            self.assertEqual(len(archive.event_paths()), 2)


class ExpungeTests(unittest.TestCase):
    # A string the scanner does not recognise, which is the premise: expunge
    # exists for material that got past it. The earlier fixture contained the
    # word `credential`, so once the scanner learned to read a credential named
    # in prose it refused the write and these tests could no longer set up the
    # situation they exist to test. The fixture had to be undetectable, not the
    # scanner more forgiving.
    SECRET = "zzyzx-plaintext-value-4471"  # godmode: allow-secret

    def test_the_fixture_is_genuinely_undetected(self) -> None:
        """Named rather than assumed. If the scanner learns to catch this
        string, every test below stops testing expunge and starts testing the
        scanner - and would say so by erroring on setup, which is a confusing
        way to be told the fixture went stale."""
        from godmode_runtime.godmode_sentinel import find_secret_shapes

        self.assertEqual(find_secret_shapes(self.SECRET), [],
                         "the planted secret is now detected; expunge can no "
                         "longer be set up with it")

    def test_expunge_removes_secret_from_disk_and_keeps_chain_valid(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            target = archive.append(
                "change", "config", {"value": self.SECRET}, evidence=[f"saw {self.SECRET}"]
            )
            archive.append("lesson", "after", {"value": "later"}, evidence=[])
            old_hash = target["record_hash"]

            outcome = archive.expunge(target["sequence"], "credential slipped the scanner")
            self.assertEqual(outcome["expunged"], target["sequence"])
            self.assertEqual(outcome["old_record_hash"], old_hash)

            # The secret is gone from every file in the archive, not merely the
            # record body: filenames, head, config, tombstone -- everything.
            for path in sorted(archive.root.rglob("*")):
                if path.is_file():
                    self.assertNotIn(
                        self.SECRET, path.read_text(encoding="utf-8"), path.name
                    )
                self.assertNotIn(self.SECRET, path.name)

            verified = archive.verify()
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["records"], 4)

            records = archive.read_events()
            rewritten = records[target["sequence"] - 1]
            self.assertEqual(
                rewritten["data"],
                {"expunged": True, "reason": "credential slipped the scanner"},
            )
            self.assertNotEqual(rewritten["record_hash"], old_hash)

    def test_expunge_leaves_an_auditable_tombstone_incident(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            target = archive.append(
                "change", "config", {"value": self.SECRET}, evidence=[]
            )
            archive.expunge(target["sequence"], "credential slipped the scanner")
            tombstone = archive.latest("incident")
            self.assertIsNotNone(tombstone)
            self.assertEqual(tombstone["data"]["expunged_sequence"], target["sequence"])
            self.assertEqual(tombstone["data"]["reason"], "credential slipped the scanner")
            self.assertEqual(
                tombstone["data"]["expunged_record_hash"], target["record_hash"]
            )

    def test_expunge_reseals_subsequent_records(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            target = archive.append("change", "config", {"value": self.SECRET}, evidence=[])
            tail = archive.append("lesson", "after", {"value": "later"}, evidence=[])
            archive.expunge(target["sequence"], "credential slipped the scanner")
            records = archive.read_events()
            self.assertNotEqual(records[1]["record_hash"], tail["record_hash"])
            self.assertEqual(records[1]["previous_hash"], records[0]["record_hash"])
            self.assertTrue(archive.verify()["valid"])

    def test_expunge_rejects_unknown_sequence_and_empty_reason(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=[])
            with self.assertRaises(ArchiveError):
                archive.expunge(7, "no such record")
            with self.assertRaises(ArchiveError):
                archive.expunge(1, "   ")
            self.assertEqual(archive.verify()["records"], 1)


if __name__ == "__main__":
    unittest.main()
