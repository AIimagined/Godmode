"""C-8: a checkpoint is an audited chain entry that bounds integrity verification.

Fix round 1 (review of fd076bc): the first cut trusted a checkpoint purely
on its OWN stored bytes (its own hash recomputed correctly, its `chain_head`
matching the stored hash of the record before it). Every operand of that
check was inside an attacker's reach - a forged, appended checkpoint whose
`chain_head` is simply read off the last record's stored hash passed the
same way a real one did, turning ANY earlier tamper invisible. The fix: a
checkpoint accelerates verification only once it is REGISTERED - a full
walk (every record, from position 0, no acceleration) proved the chain
intact through it, and recorded `{sequence, record_hash, previous_hash,
record_count}` in `godmode-checkpoint-registry.json`, beside the chain
anchor. An appended or tampered checkpoint that no full walk has seen is
not in the registry and grants nothing.

What this actually buys, stated plainly (see also THREAT-MODEL.md and
`changelog.d/verified-checkpoints.added.md`): tampering the checkpoint
record itself, or anything from the checkpoint forward, is caught on every
read, without a full walk. Tampering a record strictly BEFORE a registered
checkpoint, without touching the checkpoint record itself, is invisible to
an accelerated read and is caught only at the next full walk (`godmode
doctor`, which forces one via `use_checkpoint=False`, or any read where the
file-stat index and the registry both miss).
"""
from __future__ import annotations

import io
import json
import os
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

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime import godmode_chronicle  # noqa: E402
from godmode_runtime import godmode_console  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


def _doctor(project: Path) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = godmode_console.main(["--project", str(project), "doctor"])
    return code, json.loads(out.getvalue())


def _grow(archive, count: int, prefix: str = "r") -> None:
    for i in range(count):
        archive.append("decision", f"{prefix}-{i}", {"status": "ruled"}, evidence=[])


def _direct_grow(archive, count: int, prefix: str = "r") -> None:
    """Same on-disk shape as `_grow`, built under one lock acquisition
    instead of `count` separate `append()` calls - `append()`'s own
    per-call `_chain_tail()` (a directory listing plus a head-file read)
    dominates at fixture sizes in the thousands, and this fixture exists
    specifically to be big. Used only where the record count is large
    enough for that to matter; small fixtures elsewhere still go through
    the public `append()`/`_grow` path.
    """
    with archive.write_lock():
        count_before, tail_hash = archive._chain_tail()
        for i in range(count):
            record = archive._write_record(
                "decision", f"{prefix}-{i}", {"status": "ruled"}, [],
                sequence=count_before + 1, previous_hash=tail_hash,
            )
            count_before += 1
            tail_hash = record["record_hash"]


def _path_for_sequence(archive, sequence: int) -> Path:
    for path in archive.event_paths():
        if path.name.startswith(f"{sequence:012d}-"):
            return path
    raise AssertionError(f"no record file for sequence {sequence}")


def _tamper_data(archive, sequence: int, key: str = "status", value: str = "tampered") -> Path:
    """The standard tamper style used across this suite: rewrite a stored
    field, leave the stored `record_hash` stale (never re-stamped) - the
    same shape `test_chronicle_cache.py`'s own tamper test uses."""
    path = _path_for_sequence(archive, sequence)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data"][key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class CheckpointStoresChainHeadAndCount(unittest.TestCase):
    def test_a_checkpoint_stores_the_head_and_count_before_it(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 3)
            before = archive.read_events()
            record = archive.append("checkpoint", "handoff", {"status": "progress"})
        self.assertEqual(record["data"]["record_count"], 3)
        self.assertEqual(record["data"]["chain_head"], before[-1]["record_hash"])

    def test_the_first_ever_record_being_a_checkpoint_has_no_chain_head(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = archive.append("checkpoint", "handoff", {"status": "progress"})
        self.assertEqual(record["data"]["record_count"], 0)
        self.assertIsNone(record["data"]["chain_head"])


class VerifyBoundsWorkToTheTailAfterARegisteredCheckpoint(unittest.TestCase):
    def _enter(self):
        cm = isolated_project()
        result = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return result

    def _archive_with_checkpoint(self, before: int, after: int, *, fast: bool = False):
        project, state, anchor, archive = self._enter()
        archive.initialize()
        grow = _direct_grow if fast else _grow
        grow(archive, before, prefix="before")
        archive.append("checkpoint", "mid", {"status": "progress"})
        _grow(archive, after, prefix="after")
        return project, state, anchor, archive

    def test_a_verify_after_a_registered_checkpoint_hashes_a_bounded_count(self) -> None:
        # Divergence from the spec's/brief's 20 000-record fixture,
        # recorded rather than silently substituted: each record write is
        # an fsync'd atomic file write (`_atomic_json`), measured at ~12ms
        # even via the fast direct-write helper below - 20 000 of them
        # would cost roughly four minutes just to BUILD the fixture, before
        # any assertion runs, which is impractical for a unit test that
        # this suite runs on every change. 3 000 is the largest fixture
        # this file uses, chosen to keep the whole module under a minute
        # while still being two orders of magnitude bigger than the tail
        # it must stay bounded against.
        _p, _s, _a, archive = self._archive_with_checkpoint(before=3000, after=3, fast=True)
        # The checkpoint is not yet registered - nothing has done a full
        # walk since it was appended. This first read is exactly that walk
        # (see `full_walk` in `verify()`): it hashes every record once, and
        # as a side effect registers the checkpoint for every later read.
        records = archive.read_events()
        self.assertEqual(len(records), 3004)  # 3000 + checkpoint + 3
        self.assertTrue(archive.checkpoint_registry.is_file(),
                        "the priming read did not register the checkpoint")
        with mock.patch.object(godmode_chronicle, "_record_hash",
                               wraps=godmode_chronicle._record_hash) as hashed:
            result = archive.verify(records, trusted_prefix=0)
        self.assertTrue(result["ok"], result.get("message"))
        # Bounded by the tail (3) plus the checkpoint's own self-check -
        # nowhere near the 3000 records before it.
        self.assertLessEqual(hashed.call_count, 10)

    def test_without_a_checkpoint_verify_hashes_every_record(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 50)
            records = archive.read_events()
            with mock.patch.object(godmode_chronicle, "_record_hash",
                                   wraps=godmode_chronicle._record_hash) as hashed:
                result = archive.verify(records, trusted_prefix=0)
        self.assertTrue(result["ok"])
        self.assertEqual(hashed.call_count, 50)

    def test_mutating_a_record_after_the_checkpoint_fails_verify_naming_it(self) -> None:
        _p, _s, _a, archive = self._archive_with_checkpoint(before=20, after=3)
        archive.read_events()  # registers the checkpoint
        tampered_path = _tamper_data(archive, 22)  # first record after the checkpoint
        records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
        result = archive.verify(records, trusted_prefix=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_broken_path"], tampered_path.name)

    def test_an_old_style_checkpoint_with_no_c8_fields_still_verifies(self) -> None:
        # A checkpoint written before this feature existed carries no
        # chain_head/record_count at all - a plain record, never a trust
        # boundary and never a verification failure (ruling: absence is
        # not tampering). Built via the internal write path (bypassing
        # append()'s C-8 injection) so the rest of the chain links up
        # exactly as a real pre-C-8 archive's would.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 5, prefix="before")
            with archive.write_lock():
                count, tail_hash = archive._chain_tail()
                archive._write_record("checkpoint", "legacy", {"status": "progress"}, [],
                                      sequence=count + 1, previous_hash=tail_hash)
            _grow(archive, 2, prefix="after")
            records = archive.read_events()
            legacy = [r for r in records if r["subject"] == "legacy"][0]
            self.assertNotIn("chain_head", legacy["data"])
            result = archive.verify(records, trusted_prefix=0)
        self.assertTrue(result["ok"], result.get("message"))


class ARegisteredCheckpointsOwnTamperIsCaughtImmediately(unittest.TestCase):
    """Probe E (review): corrupting only the checkpoint's own `previous_hash`
    and re-stamping its `record_hash` used to pass - the boundary never
    compared the checkpoint against anything it did not also control. Once
    a checkpoint is registered, its three pinned fields are compared
    against what a full walk actually saw, and a disagreement grants
    nothing - it falls through to the full walk below, which still catches
    this exact forgery on its own: the checkpoint's re-stamped
    `previous_hash` no longer equals the actual hash of the record before
    it, so the chain-link check breaks and names the checkpoint itself.
    The registry is an accelerator, never an authority; it never reports a
    break on its own."""

    def test_forging_the_registered_checkpoints_previous_hash_is_caught_by_the_full_walk(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 3, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 21
            path = _path_for_sequence(archive, 21)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["previous_hash"] = "1" * 64
            payload["data"]["chain_head"] = "1" * 64
            payload["record_hash"] = godmode_chronicle._record_hash(payload)
            path.write_text(json.dumps(payload), encoding="utf-8")
            records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
            result = archive.verify(records, trusted_prefix=0)
        self.assertFalse(result["ok"])
        # Named by the full walk's own chain-link check, not by the registry
        # comparison - the forged checkpoint record itself, sequence 21.
        self.assertEqual(result["first_broken_sequence"], 21)
        self.assertEqual(result["first_broken_path"], path.name)
        self.assertIn("chain link", result["message"])

    def test_a_poisoned_registry_entry_over_an_intact_archive_still_reads_and_reregisters(self) -> None:
        """The registry sidecar itself is corrupted - not the archive it
        describes - so the disagreement branch falls through to a full
        walk that finds every record honest. The read still succeeds (the
        registry cannot brick a read it disagrees with), and that full
        walk re-registers the checkpoint's true fields, healing the
        sidecar for the next call."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 3, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 21
            registry_path = archive.checkpoint_registry
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            for entry in payload["entries"]:
                if entry["sequence"] == 21:
                    entry["previous_hash"] = "f" * 64
            registry_path.write_text(json.dumps(payload), encoding="utf-8")
            records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
            result = archive.verify(records, trusted_prefix=0)
            self.assertTrue(result["ok"], result.get("message"))
            healed = json.loads(registry_path.read_text(encoding="utf-8"))
        healed_entry = next(e for e in healed["entries"] if e["sequence"] == 21)
        self.assertNotEqual(healed_entry["previous_hash"], "f" * 64)


class PreBoundaryTamperIsCaughtOnlyAtTheNextFullWalk(unittest.TestCase):
    """States plainly what the accelerated path does and does not catch
    (the changelog fragment's own wording): a tamper strictly before a
    REGISTERED checkpoint, without touching the checkpoint record itself,
    passes an accelerated read and is caught only once something forces a
    full walk again - `use_checkpoint=False` (what `cmd_doctor` passes) or
    `GODMODE_VERIFY_READS=1` (bypasses the registry entirely)."""

    def _archive(self):
        archive = self._enter()
        archive.initialize()
        _grow(archive, 20, prefix="before")
        archive.append("checkpoint", "mid", {"status": "progress"})
        _grow(archive, 3, prefix="after")
        archive.read_events()  # registers the checkpoint at sequence 21
        return archive

    def _enter(self):
        cm = isolated_project()
        _p, _s, _a, archive = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return archive

    def test_an_accelerated_read_does_not_see_it(self) -> None:
        archive = self._archive()
        _tamper_data(archive, 10)  # well before the checkpoint at sequence 21
        records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
        result = archive.verify(records, trusted_prefix=0)
        self.assertTrue(result["ok"], result.get("message"))

    def test_the_next_full_walk_catches_it(self) -> None:
        archive = self._archive()
        tampered_path = _tamper_data(archive, 10)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
        result = archive.verify(records, trusted_prefix=0, use_checkpoint=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_broken_path"], tampered_path.name)

    def test_godmode_verify_reads_forces_the_same_full_walk(self) -> None:
        archive = self._archive()
        tampered_path = _tamper_data(archive, 10)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
        with mock.patch.dict(os.environ, {"GODMODE_VERIFY_READS": "1"}, clear=False):
            result = archive.verify(records, trusted_prefix=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["first_broken_path"], tampered_path.name)


class AppendedForgedCheckpointGrantsNothing(unittest.TestCase):
    """Probe D (review): tamper an old record, then append ONE more
    checkpoint whose chain_head is simply read off the (now internally
    inconsistent) last record's stored hash. Before the registry, this
    forged checkpoint became a trust boundary and hid the earlier tamper.
    It is never registered (no full walk has seen it), so it grants no
    acceleration, and the earlier tamper still surfaces."""

    def test_the_earlier_tamper_still_surfaces_after_a_forged_checkpoint_append(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            tampered_path = _tamper_data(archive, 10)
            # The attacker's own append - mechanically identical to a real
            # one (uses the live head hint, not a full re-verify), so this
            # is exactly what "one more file" costs them.
            archive.append("checkpoint", "forged", {"status": "progress"})
            records = [json.loads(p.read_text(encoding="utf-8")) for p in archive.event_paths()]
            result = archive.verify(records, trusted_prefix=0)
        self.assertFalse(result["ok"], "a forged, unregistered checkpoint must not grant trust")
        self.assertEqual(result["first_broken_path"], tampered_path.name)


class ExpungeAndReanchorClearTheRegistry(unittest.TestCase):
    def test_expunge_before_a_registered_checkpoint_leaves_the_archive_readable(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 10, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 5, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 11
            self.assertTrue(archive.checkpoint_registry.is_file())
            archive.expunge(3, "leaked secret shape")
            # The registry must not survive a re-seal that changed what an
            # earlier full walk actually proved.
            self.assertFalse(archive.checkpoint_registry.is_file())
            records = archive.read_events()  # must not raise
            result = archive.verify(records)
        self.assertTrue(result["ok"], result.get("message"))

    def test_reanchor_after_truncation_past_a_registered_checkpoint_leaves_the_archive_readable(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 10, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 5, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 11
            self.assertTrue(archive.checkpoint_registry.is_file())
            # Truncate the tail (delete the last 3 record files) so the
            # anchor is stale and reanchor() has something to do.
            paths = sorted(archive.event_paths())
            for path in paths[-3:]:
                path.unlink()
            archive.head.unlink(missing_ok=True)
            archive._events_cache_key = None
            # reanchor() clears the registry (`_drop_events_cache(rewrite=
            # True)`), then does its own full walk of the surviving records
            # to accept them - that walk re-registers the checkpoint on the
            # spot, since truncation alone (unlike expunge) never disturbs
            # a surviving record's own `data`. The acceptance criterion is
            # that the archive stays readable and intact, not that the
            # registry stays empty.
            archive.reanchor()
            records = archive.read_events()  # must not raise
            result = archive.verify(records)
        self.assertTrue(result["ok"], result.get("message"))


class CheckpointEvidenceMustResolve(unittest.TestCase):
    def test_a_checkpoint_with_a_non_resolving_file_evidence_is_refused(self) -> None:
        from godmode_runtime.godmode_console import main
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code = main(["--project", str(project), "checkpoint", "handoff",
                        "--status", "progress",
                        "--evidence", "file:does-not-exist.py"])
        self.assertNotEqual(code, 0)

    def test_a_checkpoint_with_a_non_resolving_seq_evidence_is_refused(self) -> None:
        from godmode_runtime.godmode_console import main
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code = main(["--project", str(project), "checkpoint", "handoff",
                        "--status", "progress",
                        "--evidence", "seq:9999"])
        self.assertNotEqual(code, 0)

    def test_a_checkpoint_with_a_resolving_file_evidence_is_accepted(self) -> None:
        from godmode_runtime.godmode_console import main
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "real.py").write_text("x = 1\n", encoding="utf-8")
            code = main(["--project", str(project), "checkpoint", "handoff",
                        "--status", "progress",
                        "--evidence", f"file:real.py"])
        self.assertEqual(code, 0)


class DoctorFailsOnAPreBoundaryTamperBehindARegisteredCheckpoint(unittest.TestCase):
    """N1 (re-review): `cmd_doctor` already forces the one full walk this
    codebase schedules (`verify(records, use_checkpoint=False)`), but threw
    the result away - `healthy` and the exit code came only from `issues`,
    which nothing ever populated from `verification`. A tamper strictly
    before a registered checkpoint therefore reached the terminal state
    `healthy: true`, exit 0, even though the walk that just ran found and
    named the break. Fix: `cmd_doctor` now appends an error-severity issue
    (`archive-chain-broken`) whenever `verification["ok"]` is false, so
    `healthy`/`exit_code` follow the walk's own finding."""

    def test_doctor_exits_nonzero_and_reports_unhealthy(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 3, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 21
            tampered_path = _tamper_data(archive, 10)  # strictly before the boundary
            code, report = _doctor(project)
        self.assertNotEqual(code, 0, report)
        self.assertFalse(report["healthy"], report)
        self.assertFalse(report["archive"]["ok"], report["archive"])
        broken = [i for i in report["issues"] if i["code"] == "archive-chain-broken"]
        self.assertEqual(len(broken), 1, report["issues"])
        self.assertEqual(broken[0]["severity"], "error")
        self.assertIn(tampered_path.name, report["archive"]["first_broken_path"])

    def test_doctor_stays_healthy_when_the_walk_finds_nothing(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _grow(archive, 5, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 2, prefix="after")
            code, report = _doctor(project)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["healthy"], report)
        self.assertTrue(report["archive"]["ok"], report["archive"])
        self.assertFalse([i for i in report["issues"] if i["code"] == "archive-chain-broken"])


class DoctorReachesItsForcedFullWalkPastAPoisonedRegistry(unittest.TestCase):
    """B1 (final review): a poisoned registry sidecar used to raise
    `ArchiveError` out of `cmd_doctor`'s own preliminary `read_events()`
    call, before doctor ever reached its forced full walk at
    `use_checkpoint=False` - the one command meant to recover from exactly
    this. `cmd_doctor` now reads unverified (`read_events(verify=False)`)
    and lets its own explicit `verify(..., use_checkpoint=False)` decide
    health, so a poisoned-but-inert registry entry no longer bricks the
    recovery path, and a poisoned registry over a genuinely tampered
    record still reports the break."""

    def test_registry_poisoned_over_an_intact_archive_doctor_is_healthy(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 3, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 21
            registry_path = archive.checkpoint_registry
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            for entry in payload["entries"]:
                if entry["sequence"] == 21:
                    entry["previous_hash"] = "f" * 64
            registry_path.write_text(json.dumps(payload), encoding="utf-8")
            code, report = _doctor(project)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["healthy"], report)
        self.assertTrue(report["archive"]["ok"], report["archive"])
        self.assertFalse([i for i in report["issues"] if i["code"] == "archive-chain-broken"])

    def test_registry_poisoned_over_a_tampered_record_doctor_is_unhealthy(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _grow(archive, 20, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 3, prefix="after")
            archive.read_events()  # registers the checkpoint at sequence 21
            registry_path = archive.checkpoint_registry
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
            for entry in payload["entries"]:
                if entry["sequence"] == 21:
                    entry["previous_hash"] = "f" * 64
            registry_path.write_text(json.dumps(payload), encoding="utf-8")
            tampered_path = _tamper_data(archive, 10)  # strictly before the checkpoint
            code, report = _doctor(project)
        self.assertNotEqual(code, 0, report)
        self.assertFalse(report["healthy"], report)
        self.assertFalse(report["archive"]["ok"], report["archive"])
        broken = [i for i in report["issues"] if i["code"] == "archive-chain-broken"]
        self.assertEqual(len(broken), 1, report["issues"])
        self.assertEqual(broken[0]["severity"], "error")
        self.assertIn(tampered_path.name, report["archive"]["first_broken_path"])


class RegistryReadNeverRaises(unittest.TestCase):
    """N2 (re-review): `_read_checkpoint_registry` caught
    `(OSError, json.JSONDecodeError)`, but `Path.read_text(encoding="utf-8")`
    on non-UTF-8 bytes raises `UnicodeDecodeError`, a `ValueError` subclass
    that is NOT a `JSONDecodeError` - it escaped out of `read_events()`,
    contradicting both the function's own docstring and the "hook never
    raises" constraint. Fix: widen to `(OSError, ValueError)`, the same
    precedent `_read_index` already uses."""

    def test_non_utf8_registry_bytes_read_as_no_registry(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 5, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 2, prefix="after")
            archive.checkpoint_registry.parent.mkdir(parents=True, exist_ok=True)
            archive.checkpoint_registry.write_bytes(b"\xff\xfe{")
            # Must not raise anywhere on the read path.
            records = archive.read_events()
            result = archive.verify(records)
            self.assertTrue(result["ok"], result.get("message"))
            # Treated as "no registry": the full walk that follows
            # re-derives and rewrites it clean.
            payload = json.loads(archive.checkpoint_registry.read_text(encoding="utf-8"))
            self.assertIn("entries", payload)


class RegistryWriteNeverRaises(unittest.TestCase):
    """N3 (re-review): `_write_checkpoint_registry` caught `OSError` only,
    but `_atomic_json` raises `ArchiveError` (not an `OSError` subclass) when
    the destination cannot be written - escaping `verify()` on the read
    path, where no write had ever been able to raise before this feature.
    Fix: catch `(OSError, ArchiveError)`, swallowed best-effort, same as the
    chain anchor and the read index."""

    def test_registry_path_is_a_directory_write_is_swallowed(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 5, prefix="before")
            archive.checkpoint_registry.mkdir(parents=True, exist_ok=True)
            # A full walk that wants to register this checkpoint must not
            # raise just because the registry's own path is unwritable.
            archive.append("checkpoint", "mid", {"status": "progress"})
            records = archive.read_events()
            result = archive.verify(records)
        self.assertTrue(result["ok"], result.get("message"))

    def test_atomic_json_archive_error_on_the_read_path_is_swallowed(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _grow(archive, 5, prefix="before")
            archive.append("checkpoint", "mid", {"status": "progress"})
            _grow(archive, 2, prefix="after")
            with mock.patch.object(
                godmode_chronicle, "_atomic_json",
                side_effect=ArchiveError("read-only state home"),
            ):
                records = archive.read_events()
                result = archive.verify(records)
        self.assertTrue(result["ok"], result.get("message"))


if __name__ == "__main__":
    unittest.main()
