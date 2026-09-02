"""Trace topology: the archive's record-kind transitions as a map.

A session's work leaves a sequence of record kinds behind, and those
sequences settle into a small set of recurring transitions. Walking
each session's kind sequence as bigram transitions and marking each
with its share of FAILURE-shaped sessions (one containing an incident
or a failed claim resolution) turns the archive into a map: transitions
whose failure share clears the bar, with enough support, are warnings -
"runs that do THIS tend to end in incidents here." Counts only, no
model, honest below the session floor.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle

_SESSION_FLOOR = 4
_MIN_SUPPORT = 3
_FAILURE_SHARE_BAR = 0.7


def trace_topology(archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events(verify=False)
    sessions: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] | None = None
    for record in records:
        if record.get("kind") == "session":
            current = []
            sessions.append(current)
        elif current is not None:
            current.append(record)

    if len(sessions) < _SESSION_FLOOR:
        return {"verdict": "insufficient-sessions",
                "sessions": len(sessions),
                "note": f"topology needs at least {_SESSION_FLOOR} sessions "
                        "to say anything - counts, not vibes"}

    transitions: dict[str, list[int]] = {}  # name -> [total, failing]
    failing_sessions = 0
    for session_records in sessions:
        kinds = [str(r.get("kind")) for r in session_records]
        failing = any(
            r.get("kind") == "incident"
            or (r.get("kind") == "claim"
                and (r.get("data") or {}).get("outcome") == "failed")
            for r in session_records)
        failing_sessions += 1 if failing else 0
        for a, b in zip(kinds, kinds[1:]):
            entry = transitions.setdefault(f"{a}->{b}", [0, 0])
            entry[0] += 1
            entry[1] += 1 if failing else 0

    warnings = []
    for name, (total, in_failing) in sorted(transitions.items()):
        share = in_failing / total
        if total >= _MIN_SUPPORT and share >= _FAILURE_SHARE_BAR:
            warnings.append({
                "transition": name,
                "occurrences": total,
                "failure_share": round(share, 3),
            })

    return {
        "verdict": "topology-mapped",
        "sessions": len(sessions),
        "failing_sessions": failing_sessions,
        "transitions": len(transitions),
        "warnings": warnings,
        "basis": "record-kind bigrams per session; a warning is a "
                 "transition seen mostly in sessions that contained an "
                 "incident or failed resolution - association, not cause",
    }
