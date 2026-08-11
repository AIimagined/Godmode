"""Was this already built, and was it already refused.

Two questions, asked at the only moment the answers are worth having: before
the work starts. Both were answered wrong in the session that produced this
module. A sentinel allowlist came one command from being rebuilt after two
shipped releases had already fixed it. A reinvention check designed in an
earlier session was rediscovered from scratch, because nothing read the record
saying it had been designed.

Neither answer was missing. `removal` records why something was deleted,
decisions record what was rejected and why, and the atlas records what exists.
The archive was already holding both, and nothing consulted either.

**It reports where it looked.** An absence claim needs the search that would
have disproved it - the rule this project applies to every other claim. A
`nothing found` produced by a check that examined nothing is worse than no
check, because it reads as clearance.

**Findings, never closures.** Prior work is a reason to look, not a refusal.
Sometimes the earlier rejection was right and the request should stop; sometimes
the constraint that drove it has gone. Only a person can tell those apart, and
an agent that could clear its own precheck would clear it the way it currently
skips it.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import SETTLED_STATUSES
from .godmode_requests import closure_reason

# Kinds that can carry a "we decided against this" meaning. There is no
# `removal` kind: `godmode removal record` writes a `decision` whose subject is
# prefixed `removal:`, which is exactly the surface that already existed for
# this purpose and had no reader.
_REJECTION_KINDS = frozenset({"decision", "lesson"})

# Words that mark a record as a refusal rather than an ordinary decision. A
# decision to *do* something is not prior grounds against doing it again.
_REFUSAL_WORDS = re.compile(
    r"(?i)\b(reject|rejected|refus|declin|dropped|removed|out of scope|wontfix|"
    r"will not|not adopt|incompatible|abandoned)\b")

# Kinds that can carry "this is already known and nobody has closed it". The
# third question, and the one that was missing: `already_built` reads the tree
# and `already_rejected` reads what was turned down, so a thing FILED and still
# open - an incident, a standing obligation, an ask nobody answered - matched
# neither and stayed invisible. The case that produced it: an open item
# describing the same symptom class as the report under investigation, listed
# twice in the same session's own queue and never once connected to it.
_OPEN_KINDS = frozenset({"obligation", "incident", "request"})

# Statuses that mean the thing is done with, on top of the settled ones. A
# record with no status at all counts as open, for the same reason a record
# with no status counts as live in the contradiction check: records written
# before status was recorded must keep being reported, or the exemption
# retires the reader rather than the record.
_DISCHARGED = frozenset({"closed", "done", "discharged", "resolved", "complete",
                         "completed", "fixed", "refused"})

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOPWORDS = frozenset("""
add the a an and or of to in on at is it this that for with from by as into
new make build create support implement need want should would could please
""".split())


def _terms(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)} - _STOPWORDS


def _overlap(terms: set[str], text: str) -> int:
    haystack = text.lower()
    return sum(1 for term in terms if term in haystack)


def precheck(project_root: Path | str, archive: Chronicle, task: str) -> dict[str, Any]:
    """What already exists and what was already refused, for this task.

    Matching is by term overlap rather than by wording, because a request is
    almost never phrased the way the thing it duplicates was phrased. It is a
    weak test on purpose: a strong one that reports nothing is the check that
    cannot fail, and the cost of over-reporting is a line the reader dismisses.
    """
    root = Path(project_root)
    terms = _terms(task)
    searched: list[str] = []

    already_built: list[dict[str, Any]] = []
    symbols_examined = 0
    from .godmode_atlas import build as build_atlas

    atlas = build_atlas(root)
    searched.append(f"atlas symbols in {root.name or '.'}")
    for symbol in atlas.symbols:
        symbols_examined += 1
        name = str(getattr(symbol, "name", symbol))
        path = str(getattr(symbol, "path", ""))
        line = getattr(symbol, "line", None)
        # A location a reader can open, not a repr. The first version printed
        # the dataclass and the answer was unusable at exactly the moment it
        # was meant to be read.
        where = f"{path}:{line} {name}" if path else name
        if terms and _overlap(terms, f"{name} {path}".replace("_", " ").replace("/", " ")) >= 2:
            already_built.append({
                "where": where,
                "name": name,
                "question": f"'{name}' already exists in {path or 'this project'} - does it "
                            "do what this asks, or is this genuinely a different thing?",
            })

    records = archive.read_events() if archive.initialized() else []
    searched.append(f"{len(records)} archive records ({', '.join(sorted(_REJECTION_KINDS))})")
    already_rejected: list[dict[str, Any]] = []
    for record in records:
        kind = record.get("kind")
        data = record.get("data") or {}
        if kind == "request":
            # A request closed as `refused` is a rejection with the operator's
            # own words attached, which is the strongest form of prior ground
            # there is. It only counts when the closure said so: a plain
            # `closed` covers both "we built it" and "we turned it down".
            if closure_reason(str(data.get("status", ""))) != "refused":
                continue
        elif kind not in _REJECTION_KINDS:
            continue
        # Every string field, not just `value`: a removal record carries its
        # reason across six named fields and none of them is called `value`,
        # so reading one key found nothing in the records written by the one
        # command built to answer this question.
        text = " ".join([str(record.get("subject", ""))]
                        + [str(v) for v in data.values() if isinstance(v, str)])
        # A refused request already said so in its status; requiring the word
        # again in its prose would discard the one record that states the
        # outcome without arguing it.
        if kind != "request" and not _REFUSAL_WORDS.search(text):
            continue
        if terms and _overlap(terms, text) >= 2:
            already_rejected.append({
                "where": f"seq:{record.get('sequence')}",
                "subject": str(record.get("subject", ""))[:120],
                "question": "this was refused before - has the reason changed, or does "
                            "the refusal still hold?",
            })

    searched.append(f"open records ({', '.join(sorted(_OPEN_KINDS))})")
    already_reported: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") not in _OPEN_KINDS:
            continue
        data = record.get("data") or {}
        status = str(data.get("status", "")).lower()
        if status in _DISCHARGED or status in SETTLED_STATUSES:
            continue
        if record.get("kind") == "request" and closure_reason(status) is not None:
            continue
        text = " ".join([str(record.get("subject", ""))]
                        + [str(v) for v in data.values() if isinstance(v, str)])
        if terms and _overlap(terms, text) >= 2:
            already_reported.append({
                "where": f"seq:{record.get('sequence')}",
                "subject": str(record.get("subject", ""))[:120],
                "question": "this is already filed and still open - is the task in hand the "
                            "same thing, and does what is known there change the approach?",
            })

    findings = bool(already_built or already_rejected or already_reported)
    return {
        "task": task,
        "already_built": already_built,
        "already_rejected": already_rejected,
        "already_reported": already_reported,
        # Stated so an empty answer cannot be read as clearance from a check
        # that examined nothing.
        "searched": searched,
        "symbols_examined": symbols_examined,
        "records_examined": len(records),
        "verdict": "prior-work-found" if findings else "no-prior-work-found",
    }


def render(report: dict[str, Any]) -> str:
    """For a reader deciding whether to keep going, not for a parser."""
    if report["verdict"] == "no-prior-work-found":
        return (f"No prior work found for '{report['task'][:60]}'; searched "
                f"{report['symbols_examined']} symbols and "
                f"{report['records_examined']} records.")
    lines = [f"Prior work touching '{report['task'][:60]}':"]
    # Open first: a thing already filed and unclosed is the one a reader is most
    # likely to be about to duplicate, and the one that carries what is already
    # known about it.
    for hit in report.get("already_reported", []):
        lines.append(f"  [already filed, open] {hit['subject']} ({hit['where']})")
    for hit in report["already_rejected"]:
        lines.append(f"  [refused before] {hit['subject']} ({hit['where']})")
    shown = report["already_built"][:10]
    for hit in shown:
        lines.append(f"  [already exists] {hit['where']}")
    # A truncated list that does not say it was truncated is the defect this
    # product reports elsewhere; it does not get to commit it here.
    if len(report["already_built"]) > len(shown):
        lines.append(f"  ... and {len(report['already_built']) - len(shown)} more existing "
                     "symbols, not shown")
    lines.append("None of these is a refusal. Check whether the reason still holds.")
    return "\n".join(lines)
