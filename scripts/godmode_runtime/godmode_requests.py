"""What the operator asked for, and whether anything answered it.

Everything else this runtime governs leaves an artefact. A command leaves a
run, a fix leaves a commit, a conclusion leaves a claim that must cite one.
A request leaves nothing. It exists in the agent's recollection and nowhere
else, and recollection is the substrate this product exists to distrust.

That matters most for an input that arrives while the agent is already working.
The host hands it over beside a tool result; the agent answers whichever part
is cheapest to answer and carries the rest in its head. In a long session the
rest is what goes missing, and nobody can point at what was dropped afterwards
because there is no list.

**Recorded live, because it cannot be reconstructed.** Two signals were tried
against a real 9,777-event transcript before this module existed. The notice
the host shows the agent - "the user sent a new message while you were working"
- appears twice in the whole file, once because the agent quoted it: it is
injected at delivery and never stored. And of 113 human inputs, zero carry a
timestamp falling inside a tool call's span, because the stored time is when
the input was delivered rather than when it was typed. After the fact, an
interruption is indistinguishable from an ordinary turn. So the prompt is
recorded as it arrives or not at all.

Findings, never closures - the same contract as `godmode_obligations`. An
agent that could close its own requests would close them the way it currently
forgets them, and the point is to put the question in front of a person.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# A closed request, in the words a person is likely to use for one.
#
# `already-built` and `refused` were added because `closed` covered two
# opposite outcomes. A request closed because the thing already existed and one
# closed because it was turned down left the same record, so a later session -
# and the precheck that reads these records - could not tell "we built this"
# from "we decided not to". The distinction is the part worth keeping; the
# closure itself was never in doubt.
CLOSED_STATUSES = frozenset({"closed", "done", "answered", "addressed",
                             "declined", "withdrawn", "superseded",
                             "already-built", "refused"})

# The two that carry a reason. Everything else closes without stating one,
# which stays valid: a migration that reopened every closure written before
# this shipped would be a worse defect than the ambiguity it corrected.
_REASONED_CLOSURES = {"already-built": "already-built",
                      "refused": "refused",
                      "declined": "refused"}


def closure_reason(status: str) -> str | None:
    """Why a request closed, or `None` if it is still open.

    `unspecified` is a real answer and not a gap to be filled in later. It says
    the closure happened before anybody was asked to say why, which is a
    different fact from nobody knowing.
    """
    normalised = str(status).strip().lower()
    if normalised not in CLOSED_STATUSES:
        return None
    return _REASONED_CLOSURES.get(normalised, "unspecified")

# How much of a prompt is kept. Enough to recognise which request it was,
# short of keeping a transcript this runtime has no business duplicating -
# the host already stores one, and a second copy is a second thing to leak.
SUBJECT_LIMIT = 160

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{3,}")
_STOPWORDS = frozenset("""
the a an and or of to in on at is it this that be for with from by as was were
you i we they can not no do does did have has had will would should could if so
but then than there here what which who when where why how all any some also
just now new old very much many more most other into out up down over under
again once only own same too our your their them us am are been being get got
go make made see say said want need know think take come give please thanks ok
""".split())


def digest(text: str) -> str:
    """A stable name for a request, so the same one is not recorded twice.

    Whitespace and case are normalised because the same ask retyped is the same
    ask, and a ledger that counts it twice reports a backlog the operator does
    not have.
    """
    normalised = " ".join(text.split()).casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def summarise(text: str) -> str:
    """The line a reviewer will recognise the request by."""
    flattened = " ".join(text.split())
    if len(flattened) <= SUBJECT_LIMIT:
        return flattened
    return flattened[: SUBJECT_LIMIT - 1].rstrip() + "…"


def _keywords(text: str) -> frozenset[str]:
    return frozenset({w.lower() for w in _WORD.findall(text)} - _STOPWORDS)


def record_request(archive: Any, text: str, *, session: str | None = None,
                   tools_in_flight: int = 0,
                   source: str = "stated") -> dict[str, Any] | None:
    """Write one operator request to the archive.

    Returns `None` for an input with nothing to track - an empty prompt.

    `source` separates an ask the operator typed from one the agent supplied on
    their behalf. The hook path only ever writes `stated`; `inferred` is for an
    agent recording its own reading of an ambiguous turn. Both are worth
    keeping - an inference that shaped the work should be reviewable - but they
    cannot carry the same standing, because waiting on a stated ask is correct
    and waiting on an inferred one is the agent blocking itself. The detector
    that tells them apart keys on this field, so it defaults to the truthful
    value for the only caller that writes automatically.

    **Deduplication happens at review, not here.** The first version scanned
    every record in the archive on each prompt to reject a repeat, which put a
    full archive read on the critical path of every turn: measured at 1.1s
    against 65 events, growing linearly and forever, inside a hook the host
    kills at its timeout. A repeated prompt now writes a second record with the
    same digest, and `review_requests` collapses them - the same answer, paid
    for once when somebody reads the report instead of on every keystroke.

    The prompt is stored through the archive's ordinary append, which runs the
    secret scan every other record runs. A prompt is exactly where a pasted
    token turns up, and a ledger of asks is not worth a store of credentials.
    """
    flattened = " ".join(str(text).split())
    if not flattened:
        return None

    identifier = digest(flattened)

    return archive.append(
        "request",
        summarise(flattened),
        {
            "digest": identifier,
            "status": "open",
            # Whether the agent was already working when this arrived. The one
            # fact that cannot be recovered later, so it is recorded now.
            "interrupted_work": bool(tools_in_flight),
            "tools_in_flight": int(tools_in_flight),
            "session": session,
            "source": "inferred" if str(source).lower() == "inferred" else "stated",
            "keywords": sorted(_keywords(flattened))[:24],
        },
        evidence=[],
    )


def _closed_digests(records: list[dict[str, Any]]) -> set[str]:
    """Digests an operator has closed.

    A closure written by the runtime carries the digest. A closure written by a
    person does not: `remember --kind request --status closed --subject "..."`
    has no field a digest could travel in, so matching on `data.digest` alone
    made the closure path unreachable from the command line - the mechanism
    existed, the report told the reader to use it, and using it changed
    nothing. The same shape as obligation retirement being starved by a
    filtered record list, one module along.

    So the subject is digested as a fallback. It is the same normalisation the
    request was recorded under, which is what makes retyping the line enough.
    """
    closed: set[str] = set()
    for record in records:
        if record.get("kind") != "request":
            continue
        data = record.get("data") or {}
        if str(data.get("status", "")).lower() not in CLOSED_STATUSES:
            continue
        identifier = data.get("digest")
        if identifier:
            closed.add(str(identifier))
            continue
        subject = str(record.get("subject", "")).strip()
        if subject:
            closed.add(digest(subject))
    return closed


def review_requests(records: list[dict[str, Any]],
                    answered_text: str = "") -> dict[str, Any]:
    """Requests with no closure, interruptions first.

    `answered_text` is whatever the session has since said. Where it is
    available a request whose distinctive words all appear in it is reported as
    likely answered rather than open - a weak test on purpose. A strong one
    that reports nothing is the check that cannot fail, and the cost of
    over-reporting here is a question the operator waves away.
    """
    closed = _closed_digests(records)
    haystack = answered_text.lower()

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for record in records:
        if record.get("kind") != "request":
            continue
        data = record.get("data") or {}
        identifier = str(data.get("digest", ""))
        if str(data.get("status", "")).lower() != "open":
            continue
        total += 1
        if identifier in closed or identifier in seen:
            continue
        seen.add(identifier)

        keywords = [str(k) for k in (data.get("keywords") or [])]
        if haystack and keywords:
            echoed = sum(1 for word in keywords if word in haystack)
            coverage = echoed / len(keywords)
        else:
            coverage = 0.0
        if coverage >= 0.5:
            continue

        interrupted = bool(data.get("interrupted_work"))
        findings.append({
            "code": "request-interrupted-work" if interrupted else "request-open",
            "request": record.get("subject", ""),
            "digest": identifier,
            "sequence": int(record.get("sequence", 0)),
            "coverage": round(coverage, 2),
            "detail": ("arrived while a tool call was already running"
                       if interrupted else "recorded and not visibly answered"),
            "question": "was this answered, or did it get lost beside the "
                        "work that was already running?",
        })

    # Interruptions first: they are the ones nothing else would surface.
    findings.sort(key=lambda f: (f["code"] != "request-interrupted-work",
                                 f["coverage"], f["sequence"]))
    return {
        "requests_seen": total,
        "closed": len(closed),
        "findings": findings,
        # Stated so an empty report cannot be read as "nothing was examined".
        "verdict": "no-open-requests" if not findings else "open-requests",
    }


def render(report: dict[str, Any]) -> str:
    """One line per open request, for a reader rather than a parser."""
    if not report["findings"]:
        return (f"{report['requests_seen']} requests recorded; "
                "none look unanswered.")
    lines = [f"{len(report['findings'])} of {report['requests_seen']} recorded "
             "requests have no visible answer:"]
    for finding in report["findings"]:
        marker = "interrupted work" if finding["code"] == "request-interrupted-work" \
            else "open"
        lines.append(f"  [{marker}] {finding['request']}")
    lines.append("Close one with "
                 "`godmode remember --kind request --status closed`.")
    return "\n".join(lines)


def _self_check() -> None:
    class _Fake:
        def __init__(self) -> None:
            self.records: list[dict[str, Any]] = []

        def read_events(self) -> list[dict[str, Any]]:
            return self.records

        def append(self, kind: str, subject: str, data: dict[str, Any],
                   evidence: list[str]) -> dict[str, Any]:
            record = {"kind": kind, "subject": subject, "data": data,
                      "sequence": len(self.records) + 1}
            self.records.append(record)
            return record

    archive = _Fake()
    assert record_request(archive, "  ") is None
    first = record_request(archive, "check the release page", tools_in_flight=2)
    assert first is not None
    assert first["data"]["interrupted_work"] is True
    # The same ask retyped is the same ask - collapsed when the report is read
    # rather than refused at write, so no prompt pays for an archive scan.
    assert record_request(archive, "Check the   release page") is not None
    assert len(review_requests(archive.read_events())["findings"]) == 1

    record_request(archive, "rewrite the author identity")
    report = review_requests(archive.read_events())
    assert report["verdict"] == "open-requests", report
    assert report["findings"][0]["code"] == "request-interrupted-work", report

    answered = review_requests(archive.read_events(),
                               "I checked the release page and it is published")
    assert all(f["code"] != "request-interrupted-work" for f in answered["findings"]), \
        answered

    archive.append("request", "closed one",
                   {"digest": first["data"]["digest"], "status": "closed"}, [])
    closed = review_requests(archive.read_events())
    assert all(f["digest"] != first["data"]["digest"] for f in closed["findings"]), closed
    assert "Close one with" in render(closed)

    print("godmode_requests self-check OK")
