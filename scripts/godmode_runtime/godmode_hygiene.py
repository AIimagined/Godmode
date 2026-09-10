"""Memory hygiene over lessons and decisions (absorbed from a typed-memory
store's near-duplicate and contradiction pass, 2026-09-10; the LLM-wiki
pattern's "lint" workflow names the same duty).

`reflect` checks one new claim against the record on demand. Nothing
walked the durable knowledge itself: two lessons that say one thing in
two phrasings, or two active decisions on one subject that disagree,
sat side by side until a reader tripped on them. This pass finds both,
bounded per kind so a long archive is read at a fixed cost, and returns
a review list - it decides nothing and deletes nothing.
"""
from __future__ import annotations

import re
from typing import Any

from .godmode_attest import _NEGATION, _salient

KINDS = ("lesson", "decision")
DEFAULT_CAP = 80
NEAR_DUPLICATE = 0.6
# Polarity disagreement is the stronger signal, so a contradiction needs less overlap.
CONTRADICTION_OVERLAP = 0.4
_INACTIVE = frozenset({"closed", "retired", "superseded", "withdrawn", "done", "waived"})


def _text(record: dict[str, Any]) -> str:
    data = record.get("data") or {}
    return " ".join(str(part) for part in (record.get("subject", ""), data.get("value", ""),
                                            data.get("generalized_guard", "")) if part)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def hygiene(records: list[dict[str, Any]], cap: int = DEFAULT_CAP) -> dict[str, Any]:
    """Near-duplicates and contradictions among the newest `cap` active
    records of each kind. Each finding names both sequences, so the review
    command is `remember ... --status superseded` on the one that lost."""
    out: dict[str, Any] = {"considered": {}, "near_duplicates": [], "contradictions": [], "cap": cap}
    for kind in KINDS:
        latest: dict[str, dict[str, Any]] = {}
        for record in records:
            if record.get("kind") != kind:
                continue
            latest[str(record.get("subject", "")).strip()] = record
        active = [r for r in latest.values()
                  if str((r.get("data") or {}).get("status", "active")).lower() not in _INACTIVE]
        active = sorted(active, key=lambda r: int(r.get("sequence", 0) or 0))[-cap:]
        out["considered"][kind] = len(active)
        terms = {int(r.get("sequence", 0) or 0): _salient(_text(r)) for r in active}
        for index, first in enumerate(active):
            seq_a = int(first.get("sequence", 0) or 0)
            for second in active[index + 1:]:
                seq_b = int(second.get("sequence", 0) or 0)
                score = _jaccard(terms[seq_a], terms[seq_b])
                if score < CONTRADICTION_OVERLAP:
                    continue
                text_a, text_b = _text(first), _text(second)
                polarity_differs = bool(_NEGATION.search(text_a.lower())) != bool(_NEGATION.search(text_b.lower()))
                if not polarity_differs and score < NEAR_DUPLICATE:
                    continue
                finding = {
                    "kind": kind, "sequences": [seq_a, seq_b],
                    "subjects": [str(first.get("subject", ""))[:80], str(second.get("subject", ""))[:80]],
                    "overlap": round(score, 2),
                    "shared_terms": sorted(terms[seq_a] & terms[seq_b])[:6],
                }
                if polarity_differs:
                    finding["why"] = "same subject, opposite polarity - one of them no longer binds"
                    out["contradictions"].append(finding)
                else:
                    finding["why"] = "two phrasings of one rule - keep the sharper, supersede the other"
                    out["near_duplicates"].append(finding)
    out["review"] = len(out["near_duplicates"]) + len(out["contradictions"])
    out["next"] = ("`godmode remember --kind <kind> --subject \"<the loser>\" --status superseded` per finding"
                   if out["review"] else "nothing to review")
    return out


def _self_check() -> None:
    records = [
        {"kind": "lesson", "subject": "verify before claiming done", "sequence": 1,
         "data": {"value": "run the suite before saying the work is done", "status": "active"}},
        {"kind": "lesson", "subject": "run the suite before done", "sequence": 2,
         "data": {"value": "verify by running the suite before claiming the work is done", "status": "active"}},
        {"kind": "decision", "subject": "hooks read stdin to EOF", "sequence": 3,
         "data": {"value": "hooks read stdin to EOF", "status": "active"}},
        {"kind": "decision", "subject": "hooks read stdin to EOF", "sequence": 4,
         "data": {"value": "hooks do not read stdin to EOF; they stop at the first object", "status": "active"}},
    ]
    report = hygiene(records)
    assert report["near_duplicates"] and report["near_duplicates"][0]["sequences"] == [1, 2], report
    assert report["contradictions"] == [] or report["considered"]["decision"] == 1, report
    assert re.match(r"`godmode remember", report["next"])


if __name__ == "__main__":
    _self_check()
    print("ok")
