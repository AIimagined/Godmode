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
    # B4-3: coverage went stale as CX/B3 added writers - a kind without a
    # mask compressed to the default ("status", "state"), which for most of
    # the kinds below kept nothing their payloads hold. The completeness
    # test (tests/test_brief_budget.py) now enumerates every literal-kind
    # writer by AST scan; grow-only - a mask outlives its writer, because
    # old archives still hold the records.
    "action": ("state", "host", "category"),
    "attestation": ("status", "session"),
    "branch": ("branch", "state"),
    "claim": ("grade", "session"),
    "checkpoint": ("status", "next"),
    "change": ("files", "plan"),
    "criterion": ("task", "session"),
    "perimeter": ("status", "digest"),
    "ratchet": ("name", "value", "previous"),
    "checker_bond": ("session", "failed_as_expected"),
    "database": ("rung", "decision", "status"),
    "receipt": ("source", "path", "lines", "digest"),
    "decision": ("status",),
    "differential": ("subject", "method"),
    # `actor` included (fix round 1, N3): the whole proposer/checker
    # separateness rule ratify enforces turns on this field, and it was
    # invisible in a compressed brief before this.
    "improvement_proposal": ("target", "diff_hash", "actor"),
    "improvement_verdict": ("proposal_seq", "verdict", "bond_seq"),
    # NS-12a + NS-12d (Task 9): the whole point of a compressed view here is
    # the verdict and the numbers it turned on, never the full patterns list.
    "skill_impact": ("target", "outcome", "score_before", "score_after"),
    # NS-13f: the cause and where it stands; the kill command stays masked.
    "hypothesis": ("cause", "status", "of"),
    # `graph_edge` is never a written kind (`godmode_graph.py`'s own
    # `archive.append("graph_edge", ...)` in `_self_check` exists only to
    # prove the write is refused) - a mask is declared anyway so the AST
    # writer scan (`tests/test_brief_budget.py`) stays satisfied by an
    # honest entry rather than a special-cased exemption, and so a future
    # real writer (or an old archive that predates the refusal) is never
    # silently compressed by the "status"/"state" default, which keeps
    # neither field an edge actually has.
    "graph_edge": ("type", "src", "dst", "valid_from", "valid_to"),
    "incident": ("expunged_sequence", "expunged_record_hash"),
    "inventory": ("files", "captured_at"),
    "invariant": ("status",),
    "lesson": ("status", "generalized_guard"),
    # NS-2 + NS-10j (0.3.28 Plan 5 Task 2): the separateness fields
    # `law compile`'s chained-approval check turns on - the same reasoning
    # `improvement_proposal`'s own `actor` inclusion above gives.
    "lesson_promotion": ("lesson_seq", "actor", "rerun_hash"),
    "lesson_approval": ("promotion_seq", "actor", "rerun_hash"),
    # Fix round 1 (nit 6): the COUNT, never the list. A shelf note can
    # name up to MAX_CANDIDATES sequences, and `compress_record` applies no
    # per-value cap - the whole list would have entered the brief verbatim,
    # from the one kind whose entire job is bounding something.
    "lesson_candidate": ("archived_count", "reason"),
    # NS-1: the signature and remaining budget are the whole point of a
    # compressed view - a reader deciding whether a loop is stuck needs
    # the hash and the budget, never the full failing-test-id list.
    "loop_step": ("task", "attempt_n", "failure_signature_hash"),
    "loop_halt": ("task", "reason"),
    "metric": ("measured", "turns"),
    "obligation": ("status",),
    # `workaround` is deliberately not kept, same call as `lesson`'s own
    # value text and `incident`'s detail: `index patterns` (and `history
    # --kind pattern`) read the raw record for the remedy text itself.
    "pattern": ("class", "occurrences"),
    "pin": ("action", "path"),
    "plan": ("state",),
    "refusal": ("tool", "tier", "category"),
    "request": ("digest", "status", "session"),
    # NS-11e (0.3.28 Plan 5 Task 7): the two fields that ARE the finding -
    # which kind disagrees and which sequences to open, never `reason`
    # (free text, read from the raw record when a reader wants it).
    "review": ("kind", "sequences"),
    "session": ("state", "agent"),
    "sprint": ("state", "title"),
    "upstream-diff": ("target", "verdict", "resolved"),
    "verdict": ("disposition", "run_state", "acquitted_by"),
}
_DEFAULT_KEEP: tuple[str, ...] = ("status", "state")
_TEXT_CAP = 120


def compress_record(record: dict[str, Any]) -> dict[str, Any]:
    keep = MASKS.get(record["kind"], _DEFAULT_KEEP)
    data = record["data"]
    kept = {field: data[field] for field in keep if field in data}
    removed = sorted(set(data) - set(kept))
    # The subject cap must say when it bit. A 120-character subject and a
    # 300-character subject clipped to 120 were byte-identical in the view,
    # which is the uniform-truncation lie the docstring above condemns - and
    # a head-only clip deletes exactly the tail where a long subject keeps
    # its distinguishing part. The mask states the cut, same as it states
    # every removed field.
    subject = str(record["subject"])
    clipped = len(subject) > _TEXT_CAP
    mask: dict[str, Any] = {
        "kept": sorted(kept),
        "removed": removed,
        "reconstruct": f"seq:{record['sequence']}",
    }
    if clipped:
        mask["subject_truncated_at"] = _TEXT_CAP
    return {
        "kind": record["kind"],
        "subject": subject[:_TEXT_CAP],
        "sequence": record["sequence"],
        "data": kept,
        "mask": mask,
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
