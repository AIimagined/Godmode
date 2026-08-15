"""Recurring-ask mining (U-E10): what gets asked for, across sessions, more
than once.

`godmode_requests` records every prompt as it arrives, because it is the one
input this runtime cannot reconstruct after the fact. What it does not do is
notice a pattern across that ledger: the same underlying ask, typed a
different way each time, in three separate sessions, never once becoming a
charter rule because no single session held all three occurrences at once.

This module folds the request ledger and reports exactly that: a normalized
term set that recurred in at least `threshold` distinct sessions, offered as
a SOFT charter-rule candidate. Nothing here writes a rule. The shape is the
one `godmode_detect` already uses for `init --detect` - detection proposes,
a person promotes - because a wrong guess mined from three casual asks must
never become a blocking gate uninspected.

**Clustering.** A request's normalized term set is computed with the exact
`_terms` helper `godmode_precheck` uses for its own matching, imported rather
than reimplemented - the same words are "the same ask" in both places, or the
precheck that warns "this was asked before" and this report that says "this
keeps getting asked" would quietly disagree about what counts as one. Two
requests cluster together when their term sets are identical (`frozenset`
equality, an O(n) dict-keyed bucket). Jaccard-overlap-above-a-threshold was
the other option the spec allowed; exact-set bucketing is the simpler
mechanism that still catches the case this module exists for - the same
short ask, retyped a few words differently, in three different sessions -
without a similarity threshold to tune or justify.

**Content-free by construction.** A cluster's basis is its normalized term
set (already a lossy, word-bag reduction - punctuation, order, and everything
not matched by `_terms`'s own word pattern is gone) plus `seq:` references a
reader can look up. The original request subject is read only long enough to
compute its terms; it is never copied into a candidate, a session ref, or the
rendered report. A request body can contain anything - that is exactly why
this module never repeats it back.

**Insufficient data, stated rather than guessed at.** A cluster can only ever
reach `threshold` distinct sessions if the ledger holds at least that many
sessions with a request in them. Below that, no amount of overlap could
produce a real candidate, so the report says `insufficient-data` and names
the session count instead of returning an empty candidate list a reader might
mistake for "checked, found nothing".
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_precheck import _terms

# Distinct sessions a normalized-term cluster must appear in before it is
# reported as a charter-rule candidate. Flag-tunable (`godmode recurring
# --threshold N`); this is only the default.
DEFAULT_THRESHOLD = 3

# A rendered candidate list this long is no longer a short list to review; the
# ledger keeps growing but the report stays a fixed cost to read.
_CANDIDATE_CAP = 50
# Refs per candidate, same reasoning as `godmode_roi`'s basis cap: bounded so
# one very recurrent ask cannot make the report itself unbounded.
_REFS_CAP = 20


def mine_recurring_asks(archive: Chronicle, *, threshold: int = DEFAULT_THRESHOLD) -> dict[str, Any]:
    """Fold the request ledger into charter-rule candidates.

    One linear pass over `archive.read_events()`. Every `request` record's
    subject is reduced to its `_terms` set immediately; nothing else about the
    record is read.
    """
    if threshold < 1:
        threshold = 1

    records = [r for r in archive.read_events() if r.get("kind") == "request"]

    sessions_seen: set[str] = set()
    # frozenset-of-terms -> {session_id: [seq, ...]}
    clusters: dict[frozenset[str], dict[str, list[int]]] = {}

    for record in records:
        data = record.get("data") or {}
        session = str(data.get("session") or "").strip() or None
        subject = str(record.get("subject", ""))
        sequence = record.get("sequence")

        if session is not None:
            # Counted here, before the terms check below: a session made a
            # real request either way, and the "insufficient data" verdict
            # must reflect every session the ledger actually saw, not only
            # the ones whose wording happened to survive normalization.
            sessions_seen.add(session)

        terms = frozenset(_terms(subject))
        if not terms or session is None:
            # Nothing left after normalization, or no session to attribute
            # this to - either way it cannot support a cross-session cluster.
            continue

        bucket = clusters.setdefault(terms, {})
        bucket.setdefault(session, []).append(int(sequence) if sequence is not None else 0)

    total_sessions = len(sessions_seen)
    requests_seen = len(records)

    if total_sessions < threshold:
        return {
            "verdict": "insufficient-data",
            "requests_seen": requests_seen,
            "sessions_seen": total_sessions,
            "threshold": threshold,
            "candidates": [],
            "note": f"only {total_sessions} distinct session(s) recorded a request; "
                    f"a candidate needs at least {threshold}",
        }

    candidates: list[dict[str, Any]] = []
    for terms, sessions in clusters.items():
        session_count = len(sessions)
        if session_count < threshold:
            continue
        refs = sorted(
            f"seq:{seq}" for seqs in sessions.values() for seq in seqs
        )[:_REFS_CAP]
        candidates.append({
            "terms": sorted(terms),
            "sessions": session_count,
            "refs": refs,
            "note": f"asked in {session_count} sessions - SOFT rule candidate",
        })

    # Most-recurrent first; the term list breaks ties deterministically.
    candidates.sort(key=lambda c: (-c["sessions"], c["terms"]))
    candidates = candidates[:_CANDIDATE_CAP]

    return {
        "verdict": "candidates-found" if candidates else "no-candidates",
        "requests_seen": requests_seen,
        "sessions_seen": total_sessions,
        "threshold": threshold,
        "candidates": candidates,
    }


def render(report: dict[str, Any]) -> str:
    """A reader's report: counts, normalized term sets, and `seq:` refs only -
    never a request's original wording."""
    lines = [
        "GODMODE RECURRING-ASK REPORT - counts and normalized terms only, "
        "proposals for a human to promote, nothing auto-written",
        f"Requests examined: {report['requests_seen']}",
        f"Distinct sessions with a request: {report['sessions_seen']}",
        f"Threshold: {report['threshold']} sessions",
        "",
    ]

    if report["verdict"] == "insufficient-data":
        lines.append(f"Insufficient data: {report['note']}")
        return "\n".join(lines) + "\n"

    if not report["candidates"]:
        lines.append("No cluster reached the session threshold.")
        return "\n".join(lines) + "\n"

    lines.append(f"{len(report['candidates'])} CHARTER-CANDIDATE(s):")
    for candidate in report["candidates"]:
        lines.append(f"  [{candidate['note']}]")
        lines.append(f"    terms: {', '.join(candidate['terms'])}")
        lines.append(f"    refs: {', '.join(candidate['refs'])}")
    lines.append("")
    lines.append("Proposals only - review and promote deliberately, the same as "
                 "`godmode init --detect`; nothing here writes a charter rule.")
    return "\n".join(lines) + "\n"
