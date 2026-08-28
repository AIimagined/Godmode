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

**Content-free by construction, and a second gate at the door out.** A
cluster's basis is its normalized term set (already a lossy, word-bag
reduction - punctuation, order, and everything not matched by `_terms`'s own
word pattern is gone) plus `seq:` references a reader can look up. The
original request subject is read only long enough to compute its terms; it
is never copied into a candidate, a session ref, or the rendered report.

That reduction alone is not sufficient. `_terms`'s word pattern has no upper
bound on length, and `godmode_chronicle`'s upstream secret scan
(`godmode_sentinel`) matches known vendor *shapes* - `sk-`, `ghp_`, JWTs,
scheme://user:pass@ - not high entropy in general. A generic unlabeled token
with no recognizable prefix (a bare 40-character random string, say) matches
none of those shapes, persists to the archive untouched, and - if repeated
across enough sessions - would otherwise become a single-term cluster whose
term IS that token, verbatim. Relying solely on the upstream gate would make
this module's own "content-free" claim true only by luck of the input.

So a second, local gate runs at the point a term becomes DISPLAYED output -
in `_display_term`, applied only when building `candidate["terms"]` for the
report (the one field both `render()` and the JSON payload draw from).
Clustering itself still groups by the raw `frozenset` of terms - hashing or
displaying the raw value are different concerns, and only the display side
carries the risk. A term is replaced with a `<token:NNch>` shape marker when
either holds:

- it is longer than `_OPAQUE_LENGTH_CAP` (24) characters - longer than any
  real word this runtime's own vocabulary uses, regardless of content; or
- it is at least `_OPAQUE_MIN_LENGTH` (16) characters, mixes letters and
  digits, and its vowel density is below `_OPAQUE_VOWEL_DENSITY` (0.2) - a
  simple, documented entropy proxy, not a claim of measuring real entropy:
  English words carry a vowel roughly every two or three letters, and a
  random alphanumeric string does not.

Neither rule claims to detect a secret; both only claim a term does not look
like a word, which is the bar this report actually needs to clear.

**Insufficient data, stated rather than guessed at.** A cluster can only ever
reach `threshold` distinct sessions if the ledger holds at least that many
sessions with a request in them. Below that, no amount of overlap could
produce a real candidate, so the report says `insufficient-data` and names
the session count instead of returning an empty candidate list a reader might
mistake for "checked, found nothing".

**Session-less requests, stated rather than silent.** A request record with
no `session` on it cannot support a cross-session claim, so it is excluded
from both `sessions_seen` and every cluster - but the exclusion is counted
and returned as `requests_without_session`, and named in `render()`, so a
reader sees why `requests_seen` and the clustered total can differ instead of
having to infer it from a count mismatch that a request with only stopwords
in it would produce identically.
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

# Defense-in-depth thresholds for `_display_term` - see the module docstring.
# Deliberately simple and documented rather than a real entropy measurement:
# the bar is "does not look like a word", not "is cryptographically random".
_OPAQUE_LENGTH_CAP = 24
_OPAQUE_MIN_LENGTH = 16
_OPAQUE_VOWEL_DENSITY = 0.2
_VOWELS = frozenset("aeiou")


def _looks_opaque(term: str) -> bool:
    """A term that does not look like a word - the local, in-module half of
    keeping a term-shaped secret out of a rendered report.

    Two independent triggers, either sufficient on its own:

    - over `_OPAQUE_LENGTH_CAP` characters, regardless of content;
    - at least `_OPAQUE_MIN_LENGTH` characters, mixing letters and digits,
      with a vowel density below `_OPAQUE_VOWEL_DENSITY`.
    """
    if len(term) > _OPAQUE_LENGTH_CAP:
        return True
    if len(term) < _OPAQUE_MIN_LENGTH:
        return False
    has_digit = any(c.isdigit() for c in term)
    letters = [c for c in term if c.isalpha()]
    if not has_digit or not letters:
        return False
    vowels = sum(1 for c in letters if c in _VOWELS)
    return (vowels / len(letters)) < _OPAQUE_VOWEL_DENSITY


def _display_term(term: str) -> str:
    """The form a term takes in a rendered/JSON report. A word-shaped term is
    shown unchanged; an opaque one becomes a length-only shape marker - long
    enough to say "something recurred here", short of repeating it."""
    if _looks_opaque(term):
        return f"<token:{len(term)}ch>"
    return term


def mine_recurring_asks(archive: Chronicle, *, threshold: int = DEFAULT_THRESHOLD) -> dict[str, Any]:
    """Fold the request ledger into charter-rule candidates.

    One linear pass over `archive.read_events()`. Every `request` record's
    subject is reduced to its `_terms` set immediately; nothing else about the
    record is read. Clustering keys on the raw term set; `_display_term` is
    applied only when a candidate's terms are written into the report.
    """
    if threshold < 1:
        threshold = 1

    records = [r for r in archive.read_events() if r.get("kind") == "request"]

    sessions_seen: set[str] = set()
    requests_without_session = 0
    # frozenset-of-terms -> {session_id: [seq, ...]}
    clusters: dict[frozenset[str], dict[str, list[int]]] = {}

    for record in records:
        data = record.get("data") or {}
        session = str(data.get("session") or "").strip() or None
        subject = str(record.get("subject", ""))
        sequence = record.get("sequence")

        if session is None:
            # No session to attribute this to: cannot support a cross-session
            # claim, so it is excluded from clustering - but counted, so the
            # report can say so rather than leaving it to be inferred.
            requests_without_session += 1
            continue
        sessions_seen.add(session)

        # The subject is `ask:<digest>` since 2026-08-28 - unique per ask,
        # so clustering on it would never find a repeat. The keywords are
        # the ask's own words minus stopwords, which is what the terms were
        # always meant to be; the subject is the fallback for records
        # written before the ledger stopped storing prompt text.
        keywords = [str(k) for k in (data.get("keywords") or [])]
        terms = frozenset(_terms(" ".join(keywords))) if keywords else frozenset(_terms(subject))
        if not terms:
            # Nothing left after normalization - a request that was entirely
            # stopwords cannot support a cluster either, but its session still
            # counts toward `sessions_seen` above.
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
            "requests_without_session": requests_without_session,
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
            "terms": sorted(_display_term(t) for t in terms),
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
        "requests_without_session": requests_without_session,
        "threshold": threshold,
        "candidates": candidates,
    }


def render(report: dict[str, Any]) -> str:
    """A reader's report: counts, normalized term sets, and `seq:` refs only -
    never a request's original wording, and never a term shaped like a secret
    rather than a word (see `_display_term`)."""
    lines = [
        "GODMODE RECURRING-ASK REPORT - counts and normalized terms only, "
        "proposals for a human to promote, nothing auto-written",
        f"Requests examined: {report['requests_seen']}",
        f"Distinct sessions with a request: {report['sessions_seen']}",
        f"Requests with no session on record: {report['requests_without_session']} "
        "(excluded from clustering)",
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
