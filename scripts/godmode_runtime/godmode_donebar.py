"""C-9: reviewer vs builder roles for the done-bar's own checks.

The done-bar (the Stop hook's completion gate) runs several checks before
it lets a reply through as finished. Two of them stand for a fact - a
claim with nothing backing it, a HARD charter rule never attested this
session, a done-shaped reply re-fired with no new record - and no reason
offered at the Stop boundary changes what is or is not on record.
Rewording never discharges a fact; that class of check is REVIEWER and
this module gives it no escape hatch at all.

The other class is a judgment call about how much is left before the
declared scope is actually closed - an open ask, a plan step, a style
nit. A builder who has looked and disagrees can say so. That class is
BUILDER: `godmode governance escalate <check> --reason "<why>"` records
the reason as a `decision` on the archive and the Stop hook accepts it
for a few turns, printing the reason instead of nagging or blocking.

Expiry is bounded two ways, both state rather than the clock:

- **The session anchor** (fix round 1, S1). `active_escalation` only
  accepts an `escalate:<check>` record whose own sequence is AFTER
  `godmode_hookproof._session_anchor_sequence` - the same anchor
  Plan 6 Task 12 built for exactly this shape of question (`godmode_
  guardrails.py`'s usage-ledger windowing), and for the reason that
  review gave: `latest_session` (a `session open`-only marker) is
  usually `None` on an ordinary hook-driven project, so matching on it
  would have silently never fired. An escalation written in a PRIOR
  session - before the current anchor - has aged out; only the anchor
  of 0 (no session-start hook installed, `session open` never run
  either) falls back to matching any escalation on record, exactly as
  Task 12's own D3 documents for its ledger.
- **The turn count**, inside that same window. Each real Stop turn this
  module is consulted for, while some escalation is actually live,
  leaves one `donebar-turn` record behind (`note_turn`); an escalation
  stays unexpired only while fewer of those have landed since it was
  written than its own `expires_turns` says.

`session` is still written into the escalation record - which session
was open when it was written, provenance a reader can check by eye -
but the anchor above, not that field, is what gates the match.
"""

from __future__ import annotations

from typing import Any, Iterable

from .godmode_attest import latest_session
from .godmode_chronicle import Chronicle
from .godmode_constants import DONEBAR_TURN_SUBJECT
from .godmode_errors import ArchiveError
from .godmode_hookproof import _session_anchor_sequence

REVIEWER = "reviewer"
BUILDER = "builder"

# Every check the done-bar can raise, and who may override it. Order
# matches the brief: reviewer checks first (non-negotiable), builder
# checks after (escalatable). `godmode governance --checks` prints this
# table as-is.
DONE_BAR_CHECKS: dict[str, str] = {
    "uncited-claim": REVIEWER,
    "unattested-hard-rule": REVIEWER,
    "reworded-done": REVIEWER,
    "scope-still-open": BUILDER,
    "open-operator-asks": BUILDER,
    "style": BUILDER,
}

# N-style (fix round 1 review): two checks the brief names have no live
# Stop-hook detector in this repository at all - `style` raises no
# block or notice for anything to skip, and `unattested-hard-rule` is
# read only at SessionStart, into a count, never at Stop. Escalating
# either exits 0 as though something changed at Stop when nothing does;
# `gated` in the table says so instead of leaving a reader to find out
# by escalating and getting no effect.
DONE_BAR_GATED: frozenset[str] = frozenset(
    {"uncited-claim", "reworded-done", "scope-still-open", "open-operator-asks"})

_ESCALATE_PREFIX = "escalate:"
DEFAULT_EXPIRES_TURNS = 3


def checks_table() -> list[dict[str, Any]]:
    """The check -> role table `godmode governance --checks` prints.
    `gated` is false for a builder check with no live Stop-hook detector
    to skip (see `DONE_BAR_GATED`) - escalating it is accepted and
    recorded, but changes nothing at Stop."""
    return [{"check": check, "role": role, "gated": check in DONE_BAR_GATED}
            for check, role in DONE_BAR_CHECKS.items()]


def role_of(check: str) -> str | None:
    """A check's role, or None when the name is not one of ours."""
    return DONE_BAR_CHECKS.get(check)


def escalate(archive: Chronicle, check: str, *, reason: str) -> dict[str, Any]:
    """Record a builder's reason for skipping one done-bar check for a
    few turns.

    Refuses a reviewer check - non-overridable by design, so a person
    trying anyway needs the rule named back at them, not a record that
    quietly did nothing - and refuses a name that is not a done-bar check
    at all. Both refusals raise `ArchiveError`; the CLI turns that into
    exit 2.
    """
    check = (check or "").strip()
    reason = (reason or "").strip()
    role = DONE_BAR_CHECKS.get(check)
    if role is None:
        raise ArchiveError(f"'{check}' is not a done-bar check")
    if role != BUILDER:
        raise ArchiveError(f"{check} is a reviewer check and cannot be escalated")
    if not reason:
        raise ArchiveError("Escalation needs a reason: why this check does not apply")
    session = ""
    try:
        session = latest_session(archive) or ""
    except ArchiveError:
        session = ""
    return archive.append(
        "decision", f"{_ESCALATE_PREFIX}{check}",
        {"reason": reason, "session": session,
         "expires_turns": DEFAULT_EXPIRES_TURNS},
    )


def _expires_turns_of(data: dict[str, Any]) -> int:
    """N3: a hand-edited or malformed `expires_turns` must not raise past
    this module, and an explicit 0 means "expires now", not "unset" - the
    original `int(x or DEFAULT)` treated 0 as falsy and silently promoted
    it to the default instead."""
    raw = data.get("expires_turns", DEFAULT_EXPIRES_TURNS)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EXPIRES_TURNS


def note_turn(archive: Chronicle, session: str | None = None) -> None:
    """Mark one real Stop turn - the state an escalation's expiry counts
    against. Callers tick this only while `live_escalations` found
    something live (N2): there is nothing to count otherwise, and ticking
    unconditionally would leave one record behind on every ordinary Stop,
    forever. `session` is recorded when one is open, for provenance only;
    the session ANCHOR, not this field, is what bounds the match."""
    archive.append("action", DONEBAR_TURN_SUBJECT,
                   {"session": session or "", "operation": f"donebar-turn:{session or 'none'}"})


def live_escalations(archive: Chronicle, checks: Iterable[str]) -> dict[str, str]:
    """Active escalation reasons for the requested builder checks, read in
    one pass (N2) - the Stop hook calls this once for every builder check
    it consults that turn rather than having each check re-scan the
    archive on its own. A reviewer or unknown name in `checks` is silently
    absent from the result, never a `KeyError` for a caller iterating a
    fixed list.
    """
    wanted = {c for c in checks if DONE_BAR_CHECKS.get(c) == BUILDER}
    if not wanted:
        return {}
    anchor = _session_anchor_sequence(archive)
    latest: dict[str, dict[str, Any]] = {}
    turn_sequences: list[int] = []
    for record in archive.read_events(verify=False):
        kind = record.get("kind")
        if kind == "action" and record.get("subject") == DONEBAR_TURN_SUBJECT:
            turn_sequences.append(int(record.get("sequence", 0)))
            continue
        if kind != "decision":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith(_ESCALATE_PREFIX):
            continue
        check = subject[len(_ESCALATE_PREFIX):]
        if check not in wanted:
            continue
        # S1: an escalation from BEFORE the current session anchor is
        # stale - it belongs to a session that is no longer the live one.
        # An anchor of 0 (no session-start hook, `session open` never
        # run) falls back to matching regardless, same as Task 12's D3.
        if anchor and record.get("sequence", 0) <= anchor:
            continue
        latest[check] = record
    result: dict[str, str] = {}
    for check, record in latest.items():
        expires_turns = _expires_turns_of(record.get("data") or {})
        sequence = int(record.get("sequence", 0))
        turns_since = sum(1 for seq in turn_sequences if seq > sequence)
        if turns_since >= expires_turns:
            continue
        reason = str((record.get("data") or {}).get("reason") or "")
        if reason:
            result[check] = reason
    return result


def active_escalation(archive: Chronicle, check: str) -> str | None:
    """The recorded reason when `check` has an unexpired escalation on
    record within the current session anchor's window; None otherwise.

    A reviewer check always returns None here - it never reads this at
    all, by construction, not by a value that happens to be absent. A
    thin wrapper over `live_escalations` for a single check; the Stop
    hook itself calls `live_escalations` directly so consulting several
    checks in the same turn costs one archive read, not one per check.
    """
    return live_escalations(archive, (check,)).get(check)
