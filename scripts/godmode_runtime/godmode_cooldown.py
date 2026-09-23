"""NS-10h: surface an idle anchor once, then hold silence for a cooldown.

An anchor (an open obligation's subject, an operator ask's subject - any
string a caller wants tracked) that has gone untouched for several turns is
worth naming again exactly once, not on every remaining Stop of the
session and not never again. `due_for_resurface` is the pure decision -
given the anchor's last-touched turn and the current one, is this the turn
to say something - and `record_resurfaced` is the one write that starts
the cooldown clock.

One primitive, two callers: NS-10h (the Stop hook's idle-obligation/ask
surface, this task) uses it first; NS-14e's bounded verify nudges call the
same two functions later against their own anchor names (a verify finding
repeated four times running becomes a `cooldown` record on the fourth,
per that spec item) rather than inventing a second cooldown design. Both
share one `COOLDOWN_SUBJECT` record shape; a reader in either module has
one place to look, not two that could drift.

`now_turn` and `last_touched_turn` are always a state count the caller
already tracks (Stop passes for a session, or whatever a future caller
counts as its own "turn"), never `time.time()` - a test holds the turn
count still and asserts the exact boundary a resurface becomes due,
which a wall-clock sleep could never do honestly.

**Record shape divergence, stated plainly.** The design text describes the
record's subject as `cooldown:<anchor>` - one literal per anchor. Written
that way, the subject is an unbounded, per-anchor literal that could never
be enumerated in `godmode_constants.ACTION_SUBJECTS` (the census
`tests/test_action_subjects.py` runs would fail on the first anchor nobody
had pre-registered). Every record here instead carries the one fixed
`subject=COOLDOWN_SUBJECT` ("cooldown"), with `anchor` as a `data` field -
registerable once, and every reader still resolves to exactly one anchor's
records via `_latest_cooldown_record`'s `data["anchor"]` filter.
"""

from __future__ import annotations

from typing import Any

from .godmode_constants import COOLDOWN_SUBJECT

DEFAULT_IDLE_TURNS = 3
DEFAULT_COOLDOWN_TURNS = 5


def _latest_cooldown_record(archive: Any, anchor: str) -> dict[str, Any] | None:
    """The most recent `cooldown` record for `anchor`, or None when it has
    never been resurfaced. An unreadable archive reads as "never
    resurfaced" - the fail-open direction is a resurface, not a silence
    that outlives the archive that would have proven it should end."""
    latest: dict[str, Any] | None = None
    try:
        records = archive.select(kind="action", subject=COOLDOWN_SUBJECT, limit=500)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable archive treats this anchor as never surfaced
        return None
    for record in records:
        data = record.get("data") or {}
        if str(data.get("anchor", "")) != anchor:
            continue
        if latest is None or int(record.get("sequence", 0)) >= int(latest.get("sequence", 0)):
            latest = record
    return latest


def due_for_resurface(
    archive: Any,
    anchor: str,
    now_turn: int,
    last_touched_turn: int,
    idle_turns: int = DEFAULT_IDLE_TURNS,
    cooldown_turns: int = DEFAULT_COOLDOWN_TURNS,
) -> bool:
    """True when `anchor` has been idle at least `idle_turns` turns AND is
    not presently inside an earlier resurface's cooldown window.

    `cooldown_turns` here is a real input, not merely echoed back from the
    record `record_resurfaced` already wrote: the window honoured is
    `min(the record's own until_turn, its surfaced_at_turn + this call's
    cooldown_turns)`, so a caller asking with a NARROWER cooldown than the
    one actually recorded can decide "due" sooner than the record alone
    would say. `min()` can only narrow that window, never widen it - a
    caller cannot use `cooldown_turns` to hold an anchor quiet past the
    `until_turn` the record already committed to, without writing a new
    record to do it. Passing the same `cooldown_turns` used at write time
    (the ordinary case) makes the two terms equal, which is exactly
    `now_turn >= until_turn`.
    """
    if now_turn - last_touched_turn < idle_turns:
        return False
    record = _latest_cooldown_record(archive, anchor)
    if record is None:
        return True
    data = record.get("data") or {}
    until_turn = data.get("until_turn")
    surfaced_at_turn = data.get("surfaced_at_turn")
    if not isinstance(until_turn, int):
        # A malformed record must not wedge an anchor silent forever -
        # treat it the same as "never surfaced".
        return True
    effective_until = until_turn
    if isinstance(surfaced_at_turn, int):
        effective_until = min(until_turn, surfaced_at_turn + cooldown_turns)
    return now_turn >= effective_until


def record_resurfaced(
    archive: Any,
    anchor: str,
    now_turn: int,
    cooldown_turns: int = DEFAULT_COOLDOWN_TURNS,
    operation: str = "silence-reinjection",
) -> dict[str, Any]:
    """Commit one resurface: `anchor` stays quiet until `now_turn +
    cooldown_turns`. Raises like any other archive write; Stop-path callers
    wrap this and degrade through `_report_ancillary_failure` on failure
    rather than let it escape (C-3/NS-10i)."""
    return archive.append("action", COOLDOWN_SUBJECT, {
        "anchor": anchor,
        "surfaced_at_turn": now_turn,
        "until_turn": now_turn + cooldown_turns,
        "operation": operation,
    })
