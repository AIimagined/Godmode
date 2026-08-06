"""Removal memory: deleting something keeps the knowledge of why it existed.

A removal is the change most likely to be relearned the hard way - the code is
gone, so the next session cannot read it, and the first question ("why is this
missing?") has no artefact to answer it. So a removal records six fields at the
moment of deletion, and `removal why` answers from the record instead of from
archaeology. A removal missing any field is refused: five answers and a shrug
is exactly the gap the sixth question falls into.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

REQUIRED_FIELDS = (
    "reason",        # why it was removed
    "location",      # where it lived
    "replacement",   # what covers the need now, or "nothing"
    "references",    # what still mentions it and was updated
    "restoration",   # how to bring it back if the removal was wrong
    "authorizer",    # who approved the removal
)


def record_removal(
    archive: Chronicle, subject: str, fields: dict[str, str],
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    missing = [f for f in REQUIRED_FIELDS if not str(fields.get(f, "")).strip()]
    if missing:
        raise ArchiveError(
            "A removal record needs all six fields; missing: " + ", ".join(missing)
        )
    data = {field: str(fields[field]).strip() for field in REQUIRED_FIELDS}
    data["status"] = "removed"
    return archive.append("decision", f"removal:{subject}", data, evidence=evidence)


def removal_answer(archive: Chronicle, subject: str) -> dict[str, Any] | None:
    matches = archive.select(kind="decision", subject=f"removal:{subject}", limit=1)
    if not matches:
        return None
    record = matches[-1]
    answer = {field: record["data"].get(field) for field in REQUIRED_FIELDS}
    answer["recorded_at"] = record["recorded_at"]
    answer["sequence"] = record["sequence"]
    return answer
