"""Sprint 9's mechanical half: the host's own approval, recorded as evidence.

Every adapter already lifts a host's sandbox/approval metadata onto
`HostEvent.approval_context`, and that field's own comment says it exists
"so a chronicle record or a future audit can see what the host claimed
about its own approval state alongside what godmode independently
decided". Nothing wrote it. The evidence was collected and dropped.

**The two boundaries stay separate, and that is the point.** A host's
approval is the host's; godmode's decision is godmode's; neither satisfies
the other, and nothing here reads a host approval to decide anything. What
recording both buys is a pair a person can audit - and the row worth
finding is the one where they disagree, in either direction. A host that
approved what godmode refused says godmode is covering ground the host
does not; a host that refused what godmode allowed says the reverse, and
that godmode's cover is the narrower of the two somewhere.

That asymmetry is the Sprint 9 thesis in miniature: the gate stands on
contested ground and the record does not. Every host ships controls of its
own, so the durable claim is not that godmode decides better - it is that
godmode keeps the only account of what both decided.

Stored by digest, never by operation text: an operation is exactly where a
pasted credential turns up, and these records travel. Like the fleet and
governance layers, this owns no record kind - it folds `decision` records
under a `host-approval:` subject, so the closed enumeration stays closed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

_APPROVAL_PREFIX = "host-approval:"

# What a host's metadata calls its own verdict. Read only to compare
# against godmode's, never to decide anything.
_APPROVED_KEYS = ("approved", "granted", "allowed", "permitted")

# godmode verdicts that mean "this did not proceed unchallenged".
_REFUSING = frozenset({"deny", "denied", "ask", "refused", "blocked"})


def _digest(operation: str) -> str:
    return hashlib.sha256(operation.encode("utf-8", "replace")).hexdigest()


def host_said_approved(approval_context: dict[str, Any] | None) -> bool | None:
    """The host's own verdict, or None when its metadata does not state one.

    Deliberately three-valued. A host that carries approval metadata
    without an explicit verdict has not said "no" - collapsing absence into
    refusal would manufacture disagreements that never happened.
    """
    if not isinstance(approval_context, dict):
        return None
    for key in _APPROVED_KEYS:
        value = approval_context.get(key)
        if isinstance(value, bool):
            return value
    return None


def record_host_approval(archive: Chronicle, *, host: str, tool: str,
                         operation: str,
                         approval_context: dict[str, Any] | None,
                         godmode_decision: str) -> dict[str, Any] | None:
    """Record a host's approval state beside godmode's own decision.

    Returns None when the host said nothing about its own boundary, which
    is most events: a row per event would bury the ones that actually
    carry a host verdict.
    """
    if not isinstance(approval_context, dict) or not approval_context:
        return None
    operation = (operation or "").strip()
    if not operation:
        return None
    digest = _digest(operation)
    return archive.append(
        "decision", f"{_APPROVAL_PREFIX}{digest[:16]}",
        {
            "host": host,
            "tool": tool,
            "operation_digest": digest,
            # Verbatim, because a later reader is auditing what the host
            # claimed - paraphrasing it here would be this module deciding
            # what the host meant.
            "host_approval": approval_context,
            "host_approved": host_said_approved(approval_context),
            "godmode_decision": godmode_decision,
        },
    )


def host_approvals(archive: Chronicle) -> list[dict[str, Any]]:
    """Every recorded pair, oldest first. A pure fold - never writes."""
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return []
    rows: list[dict[str, Any]] = []
    for record in events:
        subject = str(record.get("subject", ""))
        if record.get("kind") != "decision" or not subject.startswith(_APPROVAL_PREFIX):
            continue
        data = dict(record.get("data") or {})
        data["sequence"] = record.get("sequence")
        data["recorded_at"] = record.get("recorded_at")
        rows.append(data)
    return rows


def approval_divergence(archive: Chronicle) -> dict[str, Any]:
    """Where the host and godmode disagreed, in both directions."""
    approved_refused: list[dict[str, Any]] = []
    refused_allowed: list[dict[str, Any]] = []
    agreed = 0
    unstated = 0
    for row in host_approvals(archive):
        host_verdict = row.get("host_approved")
        godmode_refused = str(row.get("godmode_decision", "")).lower() in _REFUSING
        if host_verdict is None:
            # The host carried metadata but stated no verdict. Counted, not
            # guessed at.
            unstated += 1
            continue
        if host_verdict and godmode_refused:
            approved_refused.append(row)
        elif not host_verdict and not godmode_refused:
            refused_allowed.append(row)
        else:
            agreed += 1
    return {
        "host_approved_godmode_refused": approved_refused,
        "host_refused_godmode_allowed": refused_allowed,
        "agreed": agreed,
        "host_verdict_unstated": unstated,
        # Stated in the payload rather than left to be inferred: a reader
        # must never take a recorded host approval as godmode's own.
        "host_approval_substitutes": False,
        "note": ("two separate boundaries, recorded side by side - a host "
                 "approval never satisfies godmode's decision, and neither "
                 "is read here to decide anything"),
    }
