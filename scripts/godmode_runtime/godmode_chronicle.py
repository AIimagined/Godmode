"""Atomic, hash-chained local continuity records for Godmode."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterator
import uuid

import shutil

from .godmode_anchor import ProjectAnchor, anchor_fingerprint, nongit_archive_root


def writer_fingerprint() -> dict[str, str]:
    """Who is writing: host, model, effort, and the adapter's enforcement level."""
    return {
        "host": os.environ.get("GODMODE_HOST") or os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "unknown",
        "model": os.environ.get("GODMODE_MODEL", "unknown"),
        "effort": os.environ.get("GODMODE_EFFORT", "unknown"),
        "enforcement": os.environ.get("GODMODE_ENFORCEMENT", "SOFT"),
    }
from .godmode_constants import EVENT_KINDS, RUNTIME_VERSION, SCHEMA_VERSION
from .godmode_errors import ArchiveError
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


class Chronicle:
    """A project-bound archive whose primary records are immutable files."""

    def __init__(self, anchor: ProjectAnchor) -> None:
        self.anchor = anchor
        self.root = Path(anchor.archive_root)
        self.events = self.root / "godmode-events"
        self.config = self.root / "godmode-archive.json"
        self.lock_path = self.root / "godmode-write.lock"

    def initialized(self) -> bool:
        return self.config.is_file() and self.events.is_dir()

    def accepted_keys(self) -> set[str]:
        """Identities whose records this archive owns.

        Adopting a stranded archive must not rewrite its records: the ledger is
        immutable and hash-chained, so editing history to fit a new identity would
        destroy the very property that makes it trustworthy. Instead the archive
        remembers which identity it grew out of and accepts those records as its own.
        """
        keys = {self.anchor.project_key}
        if self.config.is_file():
            try:
                keys.update(self._read_json(self.config).get("adopted_keys", []))
            except ArchiveError:
                pass
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
            existing["last_anchor"] = asdict(self.anchor)
            existing["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
            existing["runtime_version"] = RUNTIME_VERSION
            existing.pop("author", None)
            _atomic_json(self.config, existing)
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
                os.write(descriptor, f"{os.getpid()}\n{time.time()}\n".encode())
                os.fsync(descriptor)
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

    def read_events(self, *, verify: bool = True) -> list[dict[str, Any]]:
        records = [self._read_json(path) for path in self.event_paths()]
        if verify:
            self.verify(records)
        return records

    def verify(self, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
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
        return {
            "valid": True,
            "records": len(records),
            "head_hash": previous,
        }

    def append(
        self,
        kind: str,
        subject: str,
        data: dict[str, Any],
        *,
        evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ArchiveError(f"Unsupported Godmode record kind: {kind}")
        subject = subject.strip()
        if not subject or len(subject) > 200:
            raise ArchiveError("Record subject must contain 1-200 characters")
        evidence = evidence or []
        payload_for_scan = {"subject": subject, "data": data, "evidence": evidence}
        enforce_private_payload(payload_for_scan)
        self.initialize()
        with self.write_lock():
            records = self.read_events(verify=True)
            sequence = len(records) + 1
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
                "previous_hash": records[-1]["record_hash"] if records else None,
            }
            record["record_hash"] = _record_hash(record)
            destination = self.events / f"{sequence:012d}-{identifier}.godmode.json"
            _atomic_json(destination, record)
            return record

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
