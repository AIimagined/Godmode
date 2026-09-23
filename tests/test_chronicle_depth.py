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
            # N-9: verify() names the break instead of raising.
            broken = archive.verify()
            self.assertFalse(broken["valid"])
            self.assertFalse(broken["ok"])
            self.assertEqual(broken["first_broken_path"], first.name)

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
        # D-3: this used to project the MEDIAN of 200 timed appends to a
        # 10s ceiling - a wall-clock proxy for "the typical cost stays flat
        # instead of growing with every record" (22.65s for 200 appends
        # under the old O(history) reverify-per-write). The read-count
        # sibling test above already proves O(1) reads at N=200; what it
        # does not show is FLATNESS - that append #1 costs the same as
        # append #200. Asserted here directly, on the same read budget,
        # comparing an early append's count against a late one's: equal
        # (and small) means flat, growing would mean O(history) again.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            # One unmeasured append first: the head cache does not exist
            # until something writes it, so the very first call on a fresh
            # archive takes the slow (empty-history) path regardless of
            # algorithm - comparing warm cost to warm cost is the point,
            # not comparing cold-start to warm.
            archive.append("action", "warm-up", {"value": -1}, evidence=[])
            original = Chronicle._read_json
            reads_by_index: dict[int, int] = {}

            def counting(path):
                counting.current.append(path.name)
                return original(path)
            counting.current = []

            with mock.patch.object(Chronicle, "_read_json", staticmethod(counting)):
                for index in range(200):
                    counting.current = []
                    archive.append("action", f"bench-{index}", {"value": index}, evidence=[])
                    if index in (0, 199):
                        reads_by_index[index] = len(
                            [n for n in counting.current if n.endswith(".godmode.json")])
            self.assertEqual(
                reads_by_index[0], reads_by_index[199],
                f"a warm append read {reads_by_index[0]} record files at history "
                f"length 2 but {reads_by_index[199]} at history length 201 - cost is "
                "growing with history again",
            )
            self.assertLessEqual(reads_by_index[199], 2)
            self.assertEqual(archive.verify()["records"], 201)


class EnforceIndexColdProcessTests(unittest.TestCase):
    def test_fresh_chronicle_append_reads_a_bounded_number_of_records(self) -> None:
        # Blocking 1 (task-4-review.md): a FRESH `Chronicle` instance (every
        # hook invocation, every write-only CLI call is one) used to pay a
        # full `read_events()` walk on its first non-lesson append, hunting
        # for enforce-carrying lessons that on almost every real archive do
        # not exist - measured 3,082 ms / 4,003 record reads at N=4,000 in
        # the review, 285 ms / 1,003 at N=1,000. The `godmode-enforce.
        # index.json` sidecar this fix adds is written on every caught-up
        # append (see `_write_record`), so the LIVE archive's own last
        # append already left it fresh for the head a fresh instance opens.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for index in range(1000):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            self.assertTrue((archive.root / "godmode-enforce.index.json").is_file())

            fresh = Chronicle(anchor)
            original = Chronicle._read_json
            reads: list[str] = []

            def counting(path):
                reads.append(path.name)
                return original(path)

            with mock.patch.object(Chronicle, "_read_json", staticmethod(counting)):
                fresh.append("action", "measured", {"value": "tail"}, evidence=[])
            record_reads = [name for name in reads if name.endswith(".godmode.json")]
            self.assertLessEqual(
                len(record_reads), 2,
                f"a fresh Chronicle's first append on a 1000-record archive "
                f"read {len(record_reads)} record files hunting for enforce "
                "lessons",
            )
            self.assertTrue(archive.verify()["valid"])

    def test_fresh_chronicle_falls_back_once_when_sidecar_absent(self) -> None:
        # The fallback path (sidecar missing entirely) still finds a real
        # enforce lesson - correctness first, the sidecar is only ever a
        # cost optimisation on top of it.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for index in range(50):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            archive.append(
                "lesson", "no-todo",
                {"value": "guard", "generalized_guard": "no TODOs", "status": "active",
                 "enforce": {"kind": "decision", "predicate": "value contains TODO"}},
            )
            (archive.root / "godmode-enforce.index.json").unlink()

            fresh = Chronicle(anchor)
            with self.assertRaises(ArchiveError):
                fresh.append("decision", "ship-it", {"value": "a TODO here", "status": "active"})

    def test_hook_append_then_fresh_cli_append_stays_flat(self) -> None:
        # I-1 fix round 2 (Blocking 1): `writer == "hook"` writes never call
        # `_sync_enforce_index` (`_enforced_refusal`'s own early return for
        # hooks), so a hook append used to leave the on-disk sidecar
        # describing the PREVIOUS head - stale the instant it happened - and
        # the next fresh non-hook process would then miss the sidecar's key
        # check and re-pay a full `read_events()` walk. `_write_record` now
        # adopts the sidecar (keyed on the pre-append `(sequence - 1,
        # previous_hash)` it already has in hand) on every append that is
        # not caught up in-process, hook or not, so a hook append leaves the
        # sidecar exactly as fresh as any other append does.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for index in range(1000):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            self.assertTrue((archive.root / "godmode-enforce.index.json").is_file())

            # A fresh Chronicle instance appending as a hook - every real
            # hook invocation is exactly this: a brand-new process whose
            # own `_enforce_index_upto` starts at 0.
            hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
            hook_process = Chronicle(anchor)
            with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
                hook_record = hook_process.append(
                    "action", "hook-write", {"value": "n"}, evidence=[])
            self.assertEqual(hook_record["writer"], "hook")

            # The NEXT fresh process (an ordinary CLI append) must still
            # read a bounded number of record files - the hook append above
            # must not have left the sidecar stale.
            fresh = Chronicle(anchor)
            original = Chronicle._read_json
            reads: list[str] = []

            def counting(path):
                reads.append(path.name)
                return original(path)

            with mock.patch.object(Chronicle, "_read_json", staticmethod(counting)):
                fresh.append("action", "measured-after-hook", {"value": "tail"}, evidence=[])
            record_reads = [name for name in reads if name.endswith(".godmode.json")]
            self.assertLessEqual(
                len(record_reads), 2,
                f"a fresh Chronicle's append right after a hook append read "
                f"{len(record_reads)} record files - the hook append left "
                "the enforce sidecar stale",
            )
            self.assertTrue(archive.verify()["valid"])


class DoctorSeedsEnforceIndexTests(unittest.TestCase):
    def test_seed_enforce_index_warms_sidecar_without_the_write_lock(self) -> None:
        # I-1 fix round 3 (B1 deployment note): re-review measured that on
        # an archive that has never had `godmode-enforce.index.json`, the
        # tier-3 fallback walk (~13s on 18,964 records) runs inside
        # `append()`'s `write_lock()`, whose acquire deadline is 20s - so
        # the first live write after this feature lands stalls every
        # concurrent writer, hooks included, for that whole window.
        # `godmode doctor` calls `Chronicle.seed_enforce_index()` from its
        # own already-unlocked full walk instead - this proves the method
        # itself never touches `write_lock()`.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for index in range(500):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            (archive.root / "godmode-enforce.index.json").unlink()

            seeder = Chronicle(anchor)
            with mock.patch.object(
                    Chronicle, "write_lock",
                    side_effect=AssertionError(
                        "seed_enforce_index must never acquire the write lock")):
                seeder.seed_enforce_index()
            self.assertTrue((archive.root / "godmode-enforce.index.json").is_file())

            # The NEXT fresh process (a real write, the scenario the
            # deployment note is about) must now read a bounded number of
            # record files - the seed above must have left it fresh.
            fresh = Chronicle(anchor)
            original = Chronicle._read_json
            reads: list[str] = []

            def counting(path):
                reads.append(path.name)
                return original(path)

            with mock.patch.object(Chronicle, "_read_json", staticmethod(counting)):
                fresh.append("action", "measured-after-doctor-seed", {"value": "tail"}, evidence=[])
            record_reads = [name for name in reads if name.endswith(".godmode.json")]
            self.assertLessEqual(
                len(record_reads), 2,
                f"a fresh Chronicle's first append after `godmode doctor` seeded "
                f"the sidecar read {len(record_reads)} record files",
            )
            self.assertTrue(archive.verify()["valid"])

    def test_seed_enforce_index_is_idempotent(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for index in range(10):
                archive.append("action", f"seed-{index}", {"value": index}, evidence=[])
            archive.seed_enforce_index()
            archive.seed_enforce_index()  # must not raise, must not re-walk destructively
            self.assertTrue(archive.verify()["valid"])


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
