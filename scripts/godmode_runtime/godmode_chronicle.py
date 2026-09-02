"""Atomic, hash-chained local continuity records for Godmode."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Iterator
import uuid

import shutil

from .godmode_anchor import ProjectAnchor, anchor_fingerprint, current_host, nongit_archive_root


def writer_fingerprint() -> dict[str, str]:
    """Who is writing: host, model, effort, and the adapter's enforcement level."""
    return {
        # CX-2: delegates to `godmode_anchor.current_host()` rather than
        # re-reading the env vars here, so this record's `host` field can
        # never disagree with what `godmode_hookproof.py`'s proof records or
        # `godmode_hostevent.py`'s adapters call the same session.
        "host": current_host(),
        "model": os.environ.get("GODMODE_MODEL", "unknown"),
        "effort": os.environ.get("GODMODE_EFFORT", "unknown"),
        "enforcement": os.environ.get("GODMODE_ENFORCEMENT", "SOFT"),
        # Where it ran, because a result produced under another runtime is not
        # evidence about this one. Deliberately coarse: the platform family and
        # the interpreter's minor version, never a hostname or a home directory,
        # since this record travels.
        "platform": os.environ.get("GODMODE_PLATFORM_OVERRIDE") or sys.platform,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        # B5: which agent, not merely which host. Host and model are not an
        # identity when two agents run on the same host - without this,
        # concurrent lanes interleave into one indistinguishable stream and
        # the fleet layer can name a lease holder that cannot be found in
        # the archive afterwards. Sourced from `godmode_constants`, which
        # has no runtime dependencies: owning it in the fleet layer would
        # make this module import that one while it imports this, and the
        # atlas reads imports statically, so deferring it inside a function
        # hid the cycle from the interpreter without removing it.
        "agent_id": agent_id(),
    }
from .godmode_constants import (
    EVENT_KINDS,
    RUNTIME_VERSION,
    SCHEMA_VERSION,
    agent_id,
)
from .godmode_errors import ArchiveError
from . import godmode_invariants as _invariants
from .godmode_sentinel import enforce_private_payload


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _record_hash(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# Kind-specific data-shape invariants, enforced by append() at the archive
# seam rather than left to whichever caller happens to build the record.
# append() must never grow one branch per kind - a validator lives in
# godmode_invariants.py (dependency-free, so importing it here creates no
# cycle) and append() only ever asks "does this kind have one?" without
# knowing what any of them actually check. A validator raises ArchiveError
# to refuse; a normal return accepts.
#
# KIND_INVARIANTS is seeded from godmode_invariants.KIND_VALIDATORS AT THIS
# MODULE'S OWN IMPORT, not left to populate itself as a side effect of some
# other module (e.g. godmode_verdict.py) being imported first. That
# distinction is load-bearing: a process that imports godmode_chronicle
# without ever importing the kind-owning module still gets the guarantee,
# because importing godmode_chronicle IS what populates it. (An earlier
# version of this mechanism relied on kind-owning modules self-registering
# at their own import time - a fresh interpreter that imported only the
# archive core saw an empty registry and could append either forbidden
# verdict combination unchecked. Eager seeding from a dependency-free module
# closes that import-order gap.) register_kind_invariant() remains available
# for a validator that genuinely cannot live in godmode_invariants.py, but
# every kind shipped today is seeded eagerly and needs no such call.
KindInvariant = Callable[[dict[str, Any]], None]
KIND_INVARIANTS: dict[str, KindInvariant] = dict(_invariants.KIND_VALIDATORS)


def register_kind_invariant(kind: str, validator: KindInvariant) -> None:
    KIND_INVARIANTS[kind] = validator


class Chronicle:
    """A project-bound archive whose primary records are immutable files."""

    def __init__(self, anchor: ProjectAnchor) -> None:
        self.anchor = anchor
        self.root = Path(anchor.archive_root)
        self.events = self.root / "godmode-events"
        self.config = self.root / "godmode-archive.json"
        self.lock_path = self.root / "godmode-write.lock"
        self.head = self.root / "godmode-head.json"
        # B4-1: the tail-truncation anchor. The hash chain is tamper-evident
        # mid-chain but silent on tail truncation (deleting the newest
        # record(s) leaves a shorter, internally valid chain), and the head
        # cache above is an explicitly disposable hint a deleter can refresh.
        # This sidecar records {length, head_hash} on every append and reads
        # may only ever catch UP to it - an anchor that over-counts the
        # files means records that existed are gone.
        self.chain_anchor = self.root / "godmode-chain-anchor.json"
        self._events_cache_key: tuple[Any, ...] | None = None
        self._events_cache: list[dict[str, Any]] | None = None
        self._accepted_keys_cache_key: tuple[int, int] | None = None
        self._accepted_keys_cache: set[str] | None = None

    def initialized(self) -> bool:
        return self.config.is_file() and self.events.is_dir()

    def accepted_keys(self) -> set[str]:
        """Identities whose records this archive owns.

        Adopting a stranded archive must not rewrite its records: the ledger is
        immutable and hash-chained, so editing history to fit a new identity would
        destroy the very property that makes it trustworthy. Instead the archive
        remembers which identity it grew out of and accepts those records as its own.

        Cached on the config file's own (mtime_ns, size): verify() calls this
        once PER RECORD, so an uncached read re-opened and re-parsed the same
        rarely-changing file up to N times per verify pass - traced live at
        96 redundant reads per verify call on a 96-record archive. `adopt()`
        is the only writer, and a fresh stat on every call means a same-pass
        adopt is still seen on the very next call.
        """
        try:
            stat = self.config.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
        if key is not None and key == self._accepted_keys_cache_key \
                and self._accepted_keys_cache is not None:
            return self._accepted_keys_cache

        keys = {self.anchor.project_key}
        if self.config.is_file():
            try:
                keys.update(self._read_json(self.config).get("adopted_keys", []))
            except ArchiveError:
                pass
        if key is not None:
            self._accepted_keys_cache_key, self._accepted_keys_cache = key, keys
        return keys

    def orphaned(self) -> dict[str, Any] | None:
        """Report an archive stranded at this project's previous identity.

        Running `git init` in an existing project switches the identity from the
        salted application-data key to the Git one, so everything recorded before
        becomes unreachable and the project reads as never initialized. Losing
        continuity silently is the failure this product exists to prevent, so the
        stranded archive is surfaced rather than left for the user to notice.
        """
        if not self.anchor.is_git:
            return None
        previous = nongit_archive_root(self.anchor.project_root)
        if previous == self.root:
            return None
        config = previous / "godmode-archive.json"
        events = previous / "godmode-events"
        if not config.is_file() or not events.is_dir():
            return None
        records = sorted(events.glob("*.json"))
        if not records:
            return None
        return {
            "source": str(previous),
            "records": len(records),
            "adoptable": not self.event_paths(),
            "reason": "project became a Git repository after these records were written",
        }

    def adopt(self, source: Path) -> dict[str, Any]:
        """Relink a stranded archive to this project's current identity.

        Copies the record files verbatim so the hash chain carries over, then
        rewrites only the identity in the config. Refuses to merge two histories:
        combining independent chains would produce a ledger that verifies against
        neither.
        """
        source = Path(source)
        source_events = source / "godmode-events"
        source_config = source / "godmode-archive.json"
        if not source_config.is_file() or not source_events.is_dir():
            raise ArchiveError(f"No adoptable archive at {source}")
        if self.event_paths():
            raise ArchiveError(
                "This archive already holds records; adopting would merge two "
                "independent hash chains. Move or clear the current archive first."
            )

        self.root.mkdir(parents=True, exist_ok=True)
        self.events.mkdir(parents=True, exist_ok=True)
        copied = 0
        for record in sorted(source_events.glob("*.json")):
            shutil.copy2(record, self.events / record.name)
            copied += 1

        payload = self._read_json(source_config)
        inherited = payload.get("project_key")
        payload["project_key"] = self.anchor.project_key
        payload["schema_version"] = SCHEMA_VERSION
        payload["adopted_from"] = "previous-identity"
        adopted = set(payload.get("adopted_keys", []))
        if inherited and inherited != self.anchor.project_key:
            adopted.add(inherited)
        payload["adopted_keys"] = sorted(adopted)
        payload["last_anchor"] = asdict(self.anchor)
        payload["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
        _atomic_json(self.config, payload)

        verified = self.verify()
        return {"adopted": copied, "source": str(source), "chain": verified}

    def initialize(self) -> None:
        # initialize() runs on every append, but creating and re-permissioning
        # directories only matters the first time; four syscalls per write for
        # directories that already exist was pure append overhead.
        if not self.initialized():
            self.root.mkdir(parents=True, exist_ok=True)
            self.events.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.root, 0o700)
                os.chmod(self.events, 0o700)
            except OSError:
                pass
        if self.config.exists():
            existing = self._read_json(self.config)
            if existing.get("project_key") != self.anchor.project_key:
                raise ArchiveError("Archive identity does not match this project")
            if existing.get("schema_version") != SCHEMA_VERSION:
                raise ArchiveError("Archive schema requires an explicit migration")
            refreshed = dict(existing)
            refreshed["last_anchor"] = asdict(self.anchor)
            refreshed["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
            refreshed["runtime_version"] = RUNTIME_VERSION
            refreshed.pop("author", None)
            # initialize() runs on every append; rewriting an identical config
            # each time costs an fsync per write for zero information. Only
            # touch the file when the anchor or runtime actually moved.
            if refreshed != existing:
                _atomic_json(self.config, refreshed)
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "product": "Godmode",
            "runtime_version": RUNTIME_VERSION,
            "project_key": self.anchor.project_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_anchor": asdict(self.anchor),
            "last_anchor_fingerprint": anchor_fingerprint(self.anchor),
        }
        _atomic_json(self.config, payload)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"Unreadable Godmode record: {path.name}") from exc
        if not isinstance(value, dict):
            raise ArchiveError(f"Invalid Godmode record: {path.name}")
        return value

    @contextmanager
    def write_lock(self, timeout_seconds: float = 5.0) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(
                    self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                # No fsync: mutual exclusion comes from O_EXCL creation, which
                # is durable enough for a lock that a crash releases by age-out;
                # the pid/time content is diagnostic only. The flush cost was
                # measurable on every single append.
                os.write(descriptor, f"{os.getpid()}\n{time.time()}\n".encode())
            except FileExistsError:
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > 120:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise ArchiveError("Godmode archive is busy; retry after the active write")
                time.sleep(0.05)
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self.lock_path.unlink(missing_ok=True)

    def event_paths(self) -> list[Path]:
        if not self.events.exists():
            return []
        return sorted(self.events.glob("*.godmode.json"))

    def _events_identity(self) -> str | None:
        """Cheap identity of the WHOLE events directory: every file's stat, hashed.

        NOT just the newest file - a tamper-evidence test caught that design
        directly: mutating an OLDER record's bytes in place (a plain
        write_text on an existing file, no new file added) left the count
        and the newest file's own stat unchanged, so that cache would have
        returned pre-tamper content and made verify() pass on tampered disk
        state. Chronicle's whole purpose is tamper evidence; a cache that
        can silently mask it is worse than no cache.

        Every file's (name, mtime_ns, size) folds into one hash. Still zero
        content reads - stat only - so it stays far cheaper than the parse
        it protects against, while catching a write to ANY record file.
        """
        try:
            names = os.listdir(self.events)
        except OSError:
            return None
        parts: list[str] = []
        for name in sorted(names):
            if not name.endswith(".godmode.json"):
                continue
            try:
                stat = (self.events / name).stat()
            except OSError:
                return None  # a file vanished mid-scan; force a fresh read
            parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
        if not parts:
            return None
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def read_events(self, *, verify: bool = True) -> list[dict[str, Any]]:
        identity = self._events_identity()
        if identity is not None and identity == self._events_cache_key \
                and self._events_cache is not None:
            records = self._events_cache
        else:
            records = [self._read_json(path) for path in self.event_paths()]
            self._events_cache_key, self._events_cache = identity, records
        if verify:
            self.verify(records)
        return records

    def verify(self, records: list[dict[str, Any]] | None = None, *,
               check_anchor: bool = True) -> dict[str, Any]:
        records = self.read_events(verify=False) if records is None else records
        previous: str | None = None
        expected_sequence = 1
        for record in records:
            if record.get("schema_version") != SCHEMA_VERSION:
                raise ArchiveError("Record schema mismatch")
            if record.get("project_key") not in self.accepted_keys():
                raise ArchiveError("Record project identity mismatch")
            if record.get("sequence") != expected_sequence:
                raise ArchiveError("Record sequence is not contiguous")
            if record.get("previous_hash") != previous:
                raise ArchiveError("Record chain link is invalid")
            if record.get("record_hash") != _record_hash(record):
                raise ArchiveError("Record content hash is invalid")
            previous = record["record_hash"]
            expected_sequence += 1
        result = {
            "valid": True,
            "records": len(records),
            "head_hash": previous,
        }
        # B4-1: the chain walk above proves the records present link up; it
        # cannot prove none were removed from the END. Only the anchor can:
        # the chain must still PASS THROUGH the anchored head. Shorter than
        # anchored, or a different hash at the anchored length, is a
        # truncation. Longer is the legal crash-window lag. `check_anchor`
        # exists solely for `reanchor()`, which must verify the surviving
        # structure while the anchor itself is what's stale.
        if check_anchor:
            anchor_state = self._read_chain_anchor()
            if anchor_state is None:
                result["anchor"] = "anchor-absent"
            else:
                gap = self._anchor_gap(anchor_state, records)
                if gap is not None:
                    # Lesson 4128, and its third live occurrence (2026-08-28,
                    # two projects in one day): a concurrent writer appends
                    # the record file and then the anchor, so a reader
                    # holding a pre-append listing can see anchor N+1
                    # against N files - a false truncation that self-heals.
                    # One re-read after a short beat, against FRESH disk
                    # state, separates that race from a real truncation;
                    # only the persistent mismatch raises. The remedy the
                    # alarm names (db --reanchor) is destructive on a false
                    # positive, which is why the beat is worth its 150ms.
                    time.sleep(0.15)
                    fresh_anchor = self._read_chain_anchor()
                    if fresh_anchor is None:
                        gap = None
                    else:
                        fresh = [self._read_json(path) for path in self.event_paths()]
                        gap = self._anchor_gap(fresh_anchor, fresh)
                if gap is not None:
                    self._raise_truncated(*gap)
                result["anchor"] = "anchored"
        return result

    def _read_chain_anchor(self) -> dict[str, Any] | None:
        """The anchored {length, head_hash}, or None when absent/unreadable.

        Unlike the head hint, absence here is REPORTED (`verify()` returns
        `anchor: "anchor-absent"`) rather than silently rebuilt - a fresh or
        pre-anchor archive legitimately has none, and the first append
        writes one; but nothing ever trusts an absent anchor as proof the
        tail is intact."""
        try:
            value = json.loads(self.chain_anchor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        length = value.get("length")
        head_hash = value.get("head_hash")
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            return None
        if length == 0 and head_hash is None:
            return {"length": 0, "head_hash": None}
        if not isinstance(head_hash, str):
            return None
        return {"length": length, "head_hash": head_hash}

    def _write_chain_anchor(self, length: int, head_hash: str | None) -> None:
        """Atomic + fsynced (`_atomic_json`), AFTER the record file lands:
        a crash between the two leaves an anchor that under-counts by one,
        which reads as the legal lag the next append repairs - never as a
        truncation."""
        try:
            _atomic_json(self.chain_anchor, {"length": length, "head_hash": head_hash})
        except OSError:
            # An anchor that cannot be written must not fail the append its
            # record already sealed. It must also not leave the PREVIOUS
            # anchor standing: that one now under-counts the files, and an
            # under-counting anchor is exactly the shape `verify` reads as
            # the legal crash-window lag - so a persistent write failure
            # would look like a healthy archive forever. Removing it makes
            # the next read say `anchor-absent`, which is the honest answer,
            # and the next successful append re-establishes it.
            self.chain_anchor.unlink(missing_ok=True)

    @staticmethod
    def _anchor_gap(anchor_state: dict[str, Any],
                    records: list[dict[str, Any]]) -> tuple[int, int] | None:
        """(anchored, remaining) when the chain does not pass through the
        anchored head; None when it does."""
        length = int(anchor_state["length"])
        if length > len(records):
            return length, len(records)
        if length and records[length - 1].get("record_hash") != anchor_state["head_hash"]:
            return length, len(records)
        return None

    @staticmethod
    def _raise_truncated(anchored: int, remaining: int) -> None:
        raise ArchiveError(
            f"tail-truncated: the chain anchor records {anchored} sealed "
            f"records but {remaining} remain, or the chain no longer passes "
            "through the anchored head - the newest records were removed or "
            "replaced. Recover them, or run `godmode db --reanchor` as an "
            "explicit operator decision (the reanchor itself is chronicled)."
        )

    def _read_head(self) -> dict[str, Any] | None:
        """Best-effort read of the head cache; anything doubtful reads as absent.

        The head cache is an optimisation, never an authority: a corrupt or
        implausible head must degrade to the full-chain scan rather than fail an
        append or, worse, be trusted.
        """
        try:
            value = json.loads(self.head.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        sequence = value.get("sequence")
        record_hash = value.get("record_hash")
        if not isinstance(sequence, int) or sequence < 0:
            return None
        if sequence == 0 and record_hash is None:
            return {"sequence": 0, "record_hash": None}
        if not isinstance(record_hash, str):
            return None
        return {"sequence": sequence, "record_hash": record_hash}

    def _write_head(self, sequence: int, record_hash: str | None) -> None:
        # A plain overwrite, not _atomic_json: the head is a disposable hint,
        # every reader and writer of it holds the write lock, and a torn write
        # merely fails _read_head's parse and triggers the full-scan rebuild.
        # The temp-file/replace/fsync dance would cost several syscalls per
        # append to protect a file whose loss costs nothing.
        try:
            self.head.write_text(
                json.dumps(
                    {"sequence": sequence, "record_hash": record_hash},
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            self.head.unlink(missing_ok=True)

    def _tail_entry(self) -> tuple[int, Path | None]:
        """Count record files and find the newest without glob's pattern machinery.

        Profiling showed glob dominating the append fast path. Record names start
        with a zero-padded 12-digit sequence, so the lexicographic maximum IS the
        newest record -- the same ordering event_paths() relies on -- and one
        name listing gives both the count and the tail. The count matters: a head
        that undercounts the files (crash between record and head writes) must be
        refused, or the next append would fork the chain.
        """
        count = 0
        last_name: str | None = None
        try:
            names = os.listdir(self.events)
        except OSError:
            return 0, None
        for name in names:
            if not name.endswith(".godmode.json"):
                continue
            count += 1
            if last_name is None or name > last_name:
                last_name = name
        return count, (self.events / last_name) if last_name else None

    def _chain_tail(self) -> tuple[int, str | None]:
        """Locate the chain tail without re-reading history. Caller holds the lock.

        Re-verifying the whole chain on every append made writes O(history), so a
        long-lived archive punished the very habit -- frequent recording -- the
        product exists to encourage. The head cache is validated against the last
        record file only (count, sequence, stored hash, and that record's own
        hash); any mismatch falls back to the full verified scan and rebuilds the
        cache. Tamper detection is not weakened: verify()/doctor still walk the
        entire chain.
        """
        count, last_path = self._tail_entry()
        head = self._read_head()
        if head is not None and head["sequence"] == count:
            if last_path is None:
                return 0, None
            try:
                last = self._read_json(last_path)
            except ArchiveError:
                last = None
            if (
                last is not None
                and last.get("sequence") == head["sequence"]
                and last.get("record_hash") == head["record_hash"]
                and _record_hash(last) == head["record_hash"]
            ):
                # B4-1: the hint validates count + last record, both of
                # which a tail-deleter who refreshes the hint controls -
                # the anchor does not pass through their hands. Checked
                # here too, or every append would ride the fast path
                # straight past it. (`anchored < count` prefix divergence
                # is left to the slow path's full verify - this guard's
                # job is the fast path's own blind spot: a shortened tail
                # behind a plausible hint.)
                anchor_state = self._read_chain_anchor()
                if anchor_state is not None:
                    if anchor_state["length"] > count:
                        self._raise_truncated(anchor_state["length"], count)
                    if (anchor_state["length"] == count and count
                            and last.get("record_hash") != anchor_state["head_hash"]):
                        self._raise_truncated(anchor_state["length"], count)
                return head["sequence"], head["record_hash"]
        records = self.read_events(verify=True)
        tail_hash = records[-1]["record_hash"] if records else None
        self._write_head(len(records), tail_hash)
        return len(records), tail_hash

    def _write_record(
        self,
        kind: str,
        subject: str,
        data: dict[str, Any],
        evidence: list[str],
        *,
        sequence: int,
        previous_hash: str | None,
    ) -> dict[str, Any]:
        """Seal and persist one record. Caller holds the lock and has scanned the payload.

        The record file lands before the head cache on purpose: a crash between
        the two leaves a head that undercounts, which _chain_tail detects and
        repairs from the files -- the files are the truth, the head is a hint.
        """
        identifier = uuid.uuid4().hex
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "project_key": self.anchor.project_key,
            "sequence": sequence,
            "record_id": identifier,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "anchor_fingerprint": anchor_fingerprint(self.anchor),
            # Every record attributes its author, so drift between models is
            # traceable on any kind, not only attestations.
            "agent": writer_fingerprint(),
            "kind": kind,
            "subject": subject,
            "data": data,
            "evidence": evidence,
            "previous_hash": previous_hash,
        }
        record["record_hash"] = _record_hash(record)
        destination = self.events / f"{sequence:012d}-{identifier}.godmode.json"
        _atomic_json(destination, record)
        # B4-1 ordering: record first, anchor second, hint last. A crash
        # after the record leaves the anchor lagging by one (legal, repaired
        # by the next append); an anchor ahead of the files can only mean
        # truncation.
        self._write_chain_anchor(sequence, record["record_hash"])
        self._write_head(sequence, record["record_hash"])
        return record

    def append(
        self,
        kind: str,
        subject: str,
        data: dict[str, Any],
        *,
        evidence: list[str] | None = None,
        dedupe: bool = False,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ArchiveError(f"Unsupported Godmode record kind: {kind}")
        subject = subject.strip()
        if not subject or len(subject) > 200:
            raise ArchiveError(
                "Record subject must contain 1-200 characters - the subject "
                "is a label; put the detail in the record's value or data")
        validator = KIND_INVARIANTS.get(kind)
        if validator is not None:
            validator(data)
        evidence = evidence or []
        payload_for_scan = {"subject": subject, "data": data, "evidence": evidence}
        enforce_private_payload(payload_for_scan)
        self.initialize()
        with self.write_lock():
            if dedupe:
                # Re-recording an unchanged fact adds no information but grows the
                # chain forever; opt-in dedupe returns the existing record instead.
                # Only the most recent record of the same kind AND subject counts:
                # deduping across subjects would silently merge distinct facts,
                # and matching anything older would hide a real state change.
                for existing in reversed(self.read_events(verify=False)):
                    if existing.get("kind") != kind or existing.get("subject") != subject:
                        continue
                    if _canonical_json(existing.get("data")) == _canonical_json(data):
                        duplicate = dict(existing)
                        # Presentation-only marker: never persisted, so the
                        # stored record's hash is untouched.
                        duplicate["deduplicated"] = True
                        return duplicate
                    break
            count, tail_hash = self._chain_tail()
            return self._write_record(
                kind, subject, data, evidence,
                sequence=count + 1, previous_hash=tail_hash,
            )

    def reanchor(self) -> dict[str, Any]:
        """B4-1's explicit recovery: accept the chain that remains as the
        chain, and say so on the record.

        The surviving records must still verify structurally (`check_anchor=
        False` - the anchor is exactly what is stale here); then the anchor
        is rewritten to match them, and the act itself is chronicled as an
        `action` record (counts only) - an operator decision that history
        got shorter, never a silent repair.
        """
        with self.write_lock():
            self._events_cache_key = None
            records = [self._read_json(path) for path in self.event_paths()]
            self.verify(records, check_anchor=False)
            previous = self._read_chain_anchor()
            self._write_chain_anchor(
                len(records), records[-1]["record_hash"] if records else None)
        record = self.append(
            "action", "chain-reanchored",
            {
                "anchored_length": len(records),
                "previous_anchor_length": previous["length"] if previous else 0,
                "previous_anchor_present": previous is not None,
            },
            evidence=[],
        )
        return {
            "reanchored": True,
            "anchored_length": len(records),
            "record": f"seq:{record['sequence']}",
        }

    def expunge(self, sequence: int, reason: str) -> dict[str, Any]:
        """Erase a record's payload after a secret slipped past the scanner.

        The sentinel matches secret *shapes*, so a real credential in an
        unfamiliar format can reach disk. Deleting the file would break the hash
        chain and hide that history changed; leaving it keeps leaking. This is
        the middle path: the record's data and evidence are replaced with an
        expunge marker, that record and every subsequent one are re-sealed so
        verify() still passes, and an `incident` tombstone records the sequence,
        reason, and the old record_hash -- the rewrite is visible and auditable,
        never silent. The one deliberate integrity trade: payload bytes are
        unrecoverable, which is the point.
        """
        reason = reason.strip()
        if not reason:
            raise ArchiveError("Expunge requires a non-empty reason")
        self.initialize()
        with self.write_lock():
            # Shallow copies of the CACHED records, not the cached objects
            # themselves: this method mutates every record from the target
            # onward in place (data/evidence/hash rewrite) before writing
            # them back, and read_events() now returns the same list object
            # on every cache hit. Mutating that shared list here would let a
            # later read_events() call see partially-expunged content that
            # was never verified or written to disk.
            records = [dict(record) for record in self.read_events(verify=True)]
            if not 1 <= sequence <= len(records):
                raise ArchiveError(f"No record with sequence {sequence} to expunge")
            target = records[sequence - 1]
            old_hash = target["record_hash"]
            tombstone_data = {
                "expunged_sequence": sequence,
                "reason": reason,
                "expunged_record_hash": old_hash,
            }
            # Scan the tombstone before touching any file: failing after the
            # re-seal would leave a rewritten chain with no tombstone -- exactly
            # the silent rewrite this method exists to avoid.
            enforce_private_payload(
                {"subject": "expunge", "data": tombstone_data, "evidence": []}
            )
            marker = {"expunged": True, "reason": reason}
            target["data"] = dict(marker)
            target["evidence"] = dict(marker)
            paths = self.event_paths()
            previous = records[sequence - 2]["record_hash"] if sequence > 1 else None
            for index in range(sequence - 1, len(records)):
                record = records[index]
                record["previous_hash"] = previous
                record["record_hash"] = _record_hash(record)
                _atomic_json(paths[index], record)
                previous = record["record_hash"]
            self._write_head(len(records), previous)
            tombstone = self._write_record(
                "incident", "expunge", tombstone_data,
                [f"expunged-sequence:{sequence}"],
                sequence=len(records) + 1, previous_hash=previous,
            )
        return {"expunged": sequence, "old_record_hash": old_hash, "tombstone": tombstone}

    def latest(self, kind: str | None = None) -> dict[str, Any] | None:
        records = self.read_events()
        for record in reversed(records):
            if kind is None or record["kind"] == kind:
                return record
        return None

    def select(
        self, *, kind: str | None = None, subject: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        records = self.read_events()
        selected = [
            record
            for record in records
            if (kind is None or record["kind"] == kind)
            and (subject is None or record["subject"] == subject)
        ]
        return selected[-max(1, min(limit, 500)) :]
