"""Typed compression: every compressed record states what was removed.

Uniform truncation is a lie of omission - the reader cannot tell a short record
from a shortened one. Here each record kind has a declared mask: the fields a
compressed view keeps, the fields it drops, and the sequence number that
reconstructs the original from the archive. Nothing is destroyed; compression
is a view, and the archive stays the reversible source.

Confidence decay: a record's weight in a brief fades with the records written
after it, so stale context loses influence gradually instead of flipping a
binary flag the moment an arbitrary threshold passes.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# kind -> fields a compressed view keeps from data. Everything else is masked
# and listed by name, never silently absent.
MASKS: dict[str, tuple[str, ...]] = {
    "attestation": ("status", "session"),
    "claim": ("grade", "session"),
    "checkpoint": ("status", "next"),
    "change": ("files", "plan"),
    "decision": ("status",),
    "invariant": ("status",),
    "lesson": ("status", "generalized_guard"),
    "obligation": ("status",),
    "plan": ("state",),
    "sprint": ("state", "title"),
}
_DEFAULT_KEEP: tuple[str, ...] = ("status", "state")
_TEXT_CAP = 120


def compress_record(record: dict[str, Any]) -> dict[str, Any]:
    keep = MASKS.get(record["kind"], _DEFAULT_KEEP)
    data = record["data"]
    kept = {field: data[field] for field in keep if field in data}
    removed = sorted(set(data) - set(kept))
    return {
        "kind": record["kind"],
        "subject": str(record["subject"])[:_TEXT_CAP],
        "sequence": record["sequence"],
        "data": kept,
        "mask": {
            "kept": sorted(kept),
            "removed": removed,
            "reconstruct": f"seq:{record['sequence']}",
        },
    }


def reconstruct(archive: Chronicle, sequence: int) -> dict[str, Any]:
    """The reversal path: the original record, every field the mask removed."""
    for record in archive.read_events():
        if record["sequence"] == sequence:
            return record
    raise ArchiveError(f"No record at seq:{sequence}; the archive holds the originals")


def confidence(sequence: int, latest_sequence: int, half_life: int = 50) -> float:
    """Confidence decays with the records written since, not with wall time.

    Wall time punishes quiet weekends; record distance measures how much has
    actually happened since this was true. Halves every `half_life` records.
    """
    age = max(0, latest_sequence - sequence)
    return round(0.5 ** (age / half_life), 4)


def compress_brief(archive: Chronicle, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = records[-1]["sequence"] if records else 0
    views = []
    for record in records:
        view = compress_record(record)
        view["confidence"] = confidence(record["sequence"], latest)
        views.append(view)
    return views
