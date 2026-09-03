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


def _ordered_keywords(text: str) -> list[str]:
    """Keywords in first-appearance order - the display form."""
    seen: list[str] = []
    for match in _WORD.findall(text):
        token = match.lower().rstrip("._-")
        if len(token) >= 4 and token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def _keywords(text: str) -> frozenset[str]:
    # Field report 2026-08-29 (obligation 4521): the token regex admits
    # trailing punctuation, so "continue." and "here." rode into candidate
    # clusters as distinct keywords - noise no promotion could turn into a
    # rule. Trailing ._- is stripped and anything shorter than four chars
    # after the strip is dropped.
    words = set()
    for match in _WORD.findall(text):
        token = match.lower().rstrip("._-")
        if len(token) >= 4 and token not in _STOPWORDS:
            words.add(token)
    return frozenset(words)


def _reviewable(record: dict[str, Any]) -> str:
    """The line a reviewer recognises an ask by, now that the subject is a
    digest: `ask:<digest> - <keywords>`. Keywords are the words the
    operator used minus stopwords, never the sentence."""
    data = record.get("data") or {}
    keywords = [str(k) for k in (data.get("keywords") or [])]
    subject = str(record.get("subject", ""))
    return f"{subject} - {' '.join(keywords)}" if keywords else subject


# `UserPromptSubmit` is the only input a host cannot reconstruct later, so
# every prompt is recorded - but the host delivers more than typed asks
# through that door. A tool-permission prompt, a task-completion
# notification and a subagent's queued command all arrive prompt-shaped,
# and on this archive they were most of a 44-entry open list that nobody
# had reviewed across 34 handovers. A ledger whose count is mostly noise
# is a ledger nobody reads.
#
# Narrow and shape-based on purpose: dropping a real ask costs far more
# than carrying a stray line, so each pattern is a host envelope no person
# types. Anything not matched is kept.
_HOST_ENVELOPES = (
    re.compile(r"^\s*<task-notification>"),
    re.compile(r"^\s*<system-reminder>"),
    # "Hook PreToolUse:Bash requires confirmation for this command: ..."
    re.compile(r"^\s*Hook [A-Za-z]+:[A-Za-z]+ requires confirmation\b"),
    # Claude Code renders a queued tool call for approval as "Bash command
    # <the command>", optionally attributed to a subagent. A person asking
    # about bash writes a sentence, which is why the command text must
    # follow immediately rather than merely appear somewhere in the line.
    # The attribution separator is matched as "any non-word run" rather than
    # as a literal middle dot: this archive stores it mojibaked, as U+00C2
    # U+00B7 - the UTF-8 bytes of `·` read back as two characters - so a
    # literal never matched the records it was written for.
    re.compile(r"^\s*Bash command\s+\W*from the \S+ agent\b"),
    re.compile(r"^\s*Bash command\s+\S"),
    # A queued command body arrives with no prefix at all. Command-shaped,
    # not sentence-shaped: a shell verb first AND a shell operator present.
    # Both are required, so "can you run the bash command that rebuilds the
    # gate table?" - a person asking - is untouched.
    re.compile(r"^\s*(cd|grep|echo|python3?|git|ls|cat|awk|sed|for|while)\s"
               r"[^\n]*(&&|\|\||<<|\|\s|>\s|>>)"),
    # A pasted terminal transcript: the PowerShell prompt is an envelope no
    # person types as an ask (2026-09-03 hygiene pass: dozens of these sat
    # open in the ledger).
    re.compile(r"^\s*PS [A-Z]:\\"),
)


def is_operator_ask(text: str) -> bool:
    """Whether a prompt is a person asking for something.

    False for a host envelope and for a prompt carrying no word at all - a
    rule of box-drawing characters is a separator, not a request.
    """
    if not text or not text.strip():
        return False
    if not _WORD.findall(text):
        return False
    return not any(pattern.search(text) for pattern in _HOST_ENVELOPES)


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
    if not is_operator_ask(flattened):
        # A host envelope, not an ask. Dropped rather than stored, because
        # a ledger of asks that fills with tool-permission prompts and task
        # notifications stops being a ledger of asks.
        return None
    # Write-path only (the review path re-judges stored digest subjects,
    # which legitimately carry few words): a SHORT single-word prompt -
    # "yes", "hi", "continue" - is turn lubricant with nothing to act on
    # later. A long single token stays recordable: a pasted opaque secret
    # must reach the redaction machinery, not vanish before it.
    if len(flattened.split()) < 2 and len(flattened) <= 12:
        return None

    # A spoken secret used to be caught downstream: the subject carried the
    # sentence, and the archive's own scan refused the append. The subject
    # is a digest now, so nothing downstream can see it - the scan happens
    # here, on the text, and a secret-shaped prompt is still REFUSED rather
    # than quietly dropped (an operator who pasted a token should be told).
    from .godmode_errors import PrivacyError
    from .godmode_sentinel import find_secret_shapes

    if find_secret_shapes(flattened):
        raise PrivacyError(
            "this prompt carries secret-shaped content; it is not recorded. "
            "Rotate anything that was pasted, then restate the ask without it.")

    identifier = digest(flattened)

    # GODMODE_PRIVACY.md: the store holds no prompts. The ask is reviewable
    # by its digest and keywords - never by the sentence the operator typed
    # (2026-08-28, obligation 4018, operator chose the digest form).
    return archive.append(
        "request",
        f"ask:{identifier[:12]}",
        {
            "digest": identifier,
            "status": "open",
            # Whether the agent was already working when this arrived. The one
            # fact that cannot be recovered later, so it is recorded now.
            "interrupted_work": bool(tools_in_flight),
            "tools_in_flight": int(tools_in_flight),
            "session": session,
            "source": "inferred" if str(source).lower() == "inferred" else "stated",
            # Appearance order, not sorted: rendered back to a reviewer,
            # ordered keywords read like the ask; a sorted bag reads like
            # noise (field report, 2026-09-03). Matching still treats
            # them as a set.
            "keywords": _ordered_keywords(flattened)[:24],
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


def open_stated_requests(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latest open stated request per digest, subject-closures honoured.

    Two consumers (the push preflight and the stop-hook nag) each rebuilt a
    latest-per-`data.digest` scan and were blind to a closure written from
    the command line: `remember --kind request --subject "ask:<hex>" --status
    closed` stores the digest OF THE SUBJECT, a different key from the
    prompt-text digest the original carries - so the exact command both
    surfaces prescribed closed nothing they could see (field-caught at the
    0.3.17 gate, 2026-09-04). `_closed_digests` already holds the fallback;
    this is the one place all readers get it from.
    """
    closed = _closed_digests(records)
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("kind") != "request":
            continue
        identifier = str((record.get("data") or {}).get("digest", ""))
        if identifier:
            latest[identifier] = record
    survivors: list[dict[str, Any]] = []
    for identifier, record in latest.items():
        data = record.get("data") or {}
        if str(data.get("status", "open")) != "open":
            continue
        if str(data.get("source", "stated")) != "stated":
            continue
        if identifier in closed:
            continue
        if digest(str(record.get("subject", "")).strip()) in closed:
            continue
        survivors.append(record)
    return survivors


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
        # A closure written by a person carries the subject they can see,
        # never the full-text digest they cannot. The subject is truncated
        # at SUBJECT_LIMIT while `digest` comes from the whole flattened
        # prompt, so for any prompt longer than the limit the two could
        # never match and the closure landed without closing anything -
        # the same shape the digest-only matching had before the subject
        # fallback was added, one truncation further along.
        subject_key = digest(str(record.get("subject", "")).strip())
        # Applied on read as well as on write. A predicate used only at
        # write time would leave every envelope already in the archive in
        # the open count forever - which is the state that made this
        # ledger unreviewable in the first place.
        if not is_operator_ask(str(record.get("subject", ""))):
            continue
        total += 1
        if identifier in closed or subject_key in closed or identifier in seen:
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
            # The subject is a digest (no prompt text in the store); the
            # keywords are what a reviewer recognises the ask by.
            "request": _reviewable(record),
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
