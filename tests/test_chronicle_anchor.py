"""B4-1: the hash chain is tamper-evident mid-chain but silent on tail
truncation - deleting the newest record(s) leaves a shorter, internally
valid chain, and the head cache is an explicitly disposable hint that a
deleter can refresh or remove. The sidecar chain anchor closes that: a
separate file recording {length, head_hash}, written after every append,
that reads may only ever catch up to - never fall behind.

The crash window is part of the contract: a record landing before the
anchor write leaves the anchor UNDER-counting by one, which is legal (the
next append repairs it). An anchor that OVER-counts the files is exactly
one thing: records that existed are gone.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402

from test_godmode_runtime import isolated_project  # noqa: E402


def _grow(archive, count: int) -> None:
    for i in range(count):
        archive.append("decision", f"ruling-{i}", {"status": "ruled"},
                       evidence=[])


def _newest_record(archive) -> Path:
    return sorted(archive.events.glob("*.godmode.json"))[-1]


class AnchorRaceSelfHeals(unittest.TestCase):
    """Lesson 4128, third live occurrence 2026-08-28: a reader holding a
    pre-append listing sees anchor N+1 against N records while the writer's
    record is already on disk. The check re-reads fresh state once after a
    beat; only a persistent mismatch raises (that path is pinned below)."""

    def test_a_stale_listing_against_a_newer_anchor_self_heals(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            stale = list(archive.read_events())
            archive.append("decision", "in-flight", {"status": "ruled"},
                           evidence=[])
            result = archive.verify(stale)
        self.assertEqual(result["anchor"], "anchored")


class TailTruncationIsDetected(unittest.TestCase):
    def test_deleting_the_newest_record_raises_on_read(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            archive.head.unlink(missing_ok=True)  # the hint is disposable
            archive._events_cache_key = None      # a fresh process reads cold
            with self.assertRaises(ArchiveError) as caught:
                archive.read_events()
            self.assertIn("tail-truncated", str(caught.exception))

    def test_a_forged_head_hint_does_not_smuggle_an_append_through(self) -> None:
        """The head hint validates count + last record, so a deleter who
        refreshes it would pass `_chain_tail`'s fast path - the anchor check
        must hold on the append path too, not only in verify()."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            remaining = json.loads(
                _newest_record(archive).read_text(encoding="utf-8"))
            archive.head.write_text(json.dumps({
                "sequence": remaining["sequence"],
                "record_hash": remaining["record_hash"],
            }), encoding="utf-8")
            archive._events_cache_key = None
            with self.assertRaises(ArchiveError):
                archive.append("decision", "post-truncation",
                               {"status": "ruled"}, evidence=[])

    def test_a_diverged_prefix_is_caught_even_at_equal_length(self) -> None:
        """Truncate-then-append forges a chain of the ORIGINAL length whose
        head hash differs - length alone must not satisfy the anchor."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            anchor_state = json.loads(
                archive.chain_anchor.read_text(encoding="utf-8"))
            anchor_state["head_hash"] = "0" * 64
            archive.chain_anchor.write_text(json.dumps(anchor_state),
                                            encoding="utf-8")
            archive._events_cache_key = None
            with self.assertRaises(ArchiveError):
                archive.read_events()


class AnchorLifecycle(unittest.TestCase):
    def test_every_append_advances_the_anchor(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 2)
            state = json.loads(archive.chain_anchor.read_text(encoding="utf-8"))
            records = archive.read_events()
            self.assertEqual(state["length"], 2)
            self.assertEqual(state["head_hash"], records[-1]["record_hash"])

    def test_an_absent_anchor_is_reported_not_trusted(self) -> None:
        """Every archive predating this unit has no anchor: reads succeed
        (fresh-adoption path), and verify() STATES the absence."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 2)
            archive.chain_anchor.unlink()
            archive._events_cache_key = None
            report = archive.verify()
            self.assertEqual(report["anchor"], "anchor-absent")
            self.assertTrue(report["valid"])

    def test_the_crash_window_lag_is_legal_and_repaired(self) -> None:
        """Anchor one behind the files = a crash between record and anchor
        writes, not a truncation; the next append catches the anchor up."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            records = archive.read_events()
            archive.chain_anchor.write_text(json.dumps({
                "length": 2, "head_hash": records[1]["record_hash"],
            }), encoding="utf-8")
            archive._events_cache_key = None
            report = archive.verify()
            self.assertEqual(report["anchor"], "anchored")
            _grow(archive, 1)
            state = json.loads(archive.chain_anchor.read_text(encoding="utf-8"))
            self.assertEqual(state["length"], 4)


class ReanchorIsAnOperatorAction(unittest.TestCase):
    def test_db_reanchor_recovers_a_truncated_archive_and_is_chronicled(self) -> None:
        from godmode_runtime import godmode_console as console
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            archive.head.unlink(missing_ok=True)
            archive._events_cache_key = None
            with self.assertRaises(ArchiveError):
                archive.read_events()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                code = console.main(["--project", str(project),
                                     "db", "--reanchor"])
            self.assertEqual(code, 0)
            archive._events_cache_key = None
            records = archive.read_events()  # readable again
            reanchors = [r for r in records
                         if r["kind"] == "action"
                         and r["subject"] == "chain-reanchored"]
            self.assertEqual(len(reanchors), 1)
            data = reanchors[0]["data"]
            self.assertEqual(data["anchored_length"], 2)
            # counts only - the record explains scope, never content
            self.assertTrue(all(isinstance(v, (int, str, bool))
                                for v in data.values()))


class TruncationDegradesTheProofReaders(unittest.TestCase):
    def test_the_gate_ratchet_reads_a_truncated_archive_as_strictest(self) -> None:
        from godmode_runtime.godmode_sentinel import declared_gate_ratchet
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            archive.head.unlink(missing_ok=True)
            archive._events_cache_key = None
            self.assertTrue(declared_gate_ratchet(archive, project,
                                                  "git_backstop"))

    def test_interception_state_reads_a_truncated_archive_as_degraded(self) -> None:
        from godmode_runtime.godmode_hookproof import (
            LEVEL_DEGRADED, interception_state)
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            archive.head.unlink(missing_ok=True)
            archive._events_cache_key = None
            self.assertEqual(
                interception_state(archive, "claude", registration="partial"),
                LEVEL_DEGRADED)

    def test_degraded_reason_names_a_truncated_chain_instead_of_raising(self) -> None:
        # G-4(b): `interception_state` catches its own read's `ArchiveError`
        # and grades this DEGRADED (the test above); `degraded_reason`
        # answers WHY and used to read the same tamper-evident archive a
        # SECOND time unguarded, letting the identical `ArchiveError`
        # escape uncaught instead of naming the cause - the one grade
        # `degraded_reason` could never explain.
        from godmode_runtime.godmode_hookproof import degraded_reason
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 3)
            _newest_record(archive).unlink()
            archive.head.unlink(missing_ok=True)
            archive._events_cache_key = None
            self.assertEqual(
                degraded_reason(archive, "claude", registration="partial"),
                "chain-tampered")


if __name__ == "__main__":
    unittest.main()


class TheAnchorAndTheTombstoneAreSequences(unittest.TestCase):
    """Fix round 2, R2-B3 and R2-B2 - the same shape in two places: a number
    read off the HOT tier alone where a global sequence belongs.

    Nothing in this repo combined `rotate_to_cold` with either `reanchor` or
    `expunge` before this class, which is why both survived round 1.
    """

    @staticmethod
    def _rotate(archive, sequences: list[int]) -> None:
        archive.rotate_to_cold(sequences)
        archive._events_cache_key = None  # noqa: SLF001 - a fresh process reads cold

    @staticmethod
    def _seal_the_tail_cold(archive) -> int:
        """Forge the one state `rotate_to_cold` refuses to create: the chain's
        TRUE tail registered cold with its hot file gone. The record's own
        bytes travel unchanged, exactly as a rotation moves them."""
        import hashlib
        records = archive.read_events(verify=False)
        tail = records[-1]
        text = json.dumps(tail, sort_keys=True, separators=(",", ":")) + "\n"
        (archive.root / "events-cold-1.jsonl").write_text(text, encoding="utf-8")
        archive._write_cold_registry(  # noqa: SLF001
            [tail["sequence"]], {tail["sequence"]: tail["record_hash"]},
            [{"file": "events-cold-1.jsonl", "sequences": [tail["sequence"]],
              "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}])
        for path in archive.events.glob(f"{tail['sequence']:012d}-*.godmode.json"):
            path.unlink()
        archive._events_cache_key = None  # noqa: SLF001
        return int(tail["sequence"])

    def test_reanchor_on_a_rotated_archive_anchors_the_tail_sequence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 8)
            self._rotate(archive, [1, 2])
            outcome = archive.reanchor()
            self.assertEqual(outcome["anchored_length"], 8,
                             "the anchor's length is a sequence, never the hot count")
            # The trailing append then advances it to its own sequence, 9.
            self.assertEqual(outcome["record"], "seq:9")
            self.assertEqual(archive._read_chain_anchor()["length"], 9)  # noqa: SLF001

    def test_a_reanchor_whose_trailing_append_fails_leaves_the_archive_readable(self) -> None:
        # The prop that hid R2-B3: `reanchor`'s last act is an `append` that
        # rewrites the anchor from the new sequence. Remove it - an enforce
        # lesson refusing `action`/`chain-reanchored`, a disk error, a kill
        # between the two - and a hot COUNT in the anchor wedges every read
        # behind a self-contradicting "records 6 ... but 6 remain".
        from godmode_runtime.godmode_chronicle import Chronicle
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 8)
            self._rotate(archive, [1, 2])
            original = Chronicle.append

            def _refuse(self, kind, subject, *args, **kwargs):
                if subject == "chain-reanchored":
                    raise ArchiveError("simulated enforce refusal on the trailing append")
                return original(self, kind, subject, *args, **kwargs)

            with mock.patch.object(Chronicle, "append", _refuse):
                with self.assertRaises(ArchiveError):
                    archive.reanchor()
            archive._events_cache_key = None  # noqa: SLF001
            records = archive.read_events()   # must not raise tail-truncated
            self.assertEqual([r["sequence"] for r in records], list(range(3, 9)))
            self.assertTrue(archive.verify(records)["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_expunge_below_the_cold_tier_mints_past_the_cold_tail(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 5)
            self._rotate(archive, [1, 2])
            outcome = archive.expunge(4, "a secret slipped past the scanner")
            self.assertEqual(outcome["tombstone"]["sequence"], 6)
            self.assertGreater(outcome["tombstone"]["sequence"], 2)
            self.assertTrue(archive.verify(archive.read_events(verify=False))["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_expunge_with_the_true_tail_cold_is_refused_not_forked(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _grow(archive, 5)
            cold_tail = self._seal_the_tail_cold(archive)
            self.assertEqual(cold_tail, 5)
            self.assertEqual([int(p.name[:12]) for p in archive.event_paths()],
                             [1, 2, 3, 4])
            with self.assertRaises(ArchiveError) as caught:
                archive.expunge(3, "a secret slipped past the scanner")
            self.assertIn("cold tier", str(caught.exception))
            # Nothing was rewritten, and no tombstone reused sequence 5.
            archive._events_cache_key = None  # noqa: SLF001
            records = archive.read_events(verify=False)
            self.assertEqual([r["sequence"] for r in records], [1, 2, 3, 4])
            self.assertTrue(archive.verify(records)["ok"])
            self.assertTrue(archive.verify_cold()["ok"], archive.verify_cold())
