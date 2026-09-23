"""Falsifier aging: a hypothesis or incident that names its own falsifier
and never runs it stays a story forever unless the age is on record
somewhere.

A claim (grade `hypothesis`) or an incident may carry `refuted_by` - the
one command whose result would refute it. `due_falsifiers` names every
such record old enough (`max_age_days`, default 2) that no `attestation`
recorded AFTER it cites that command: the falsifier was never run, or was
only ever run before the claim/incident existed, which proves an earlier
state, not this one. A claim closed by a later resolution record
(`claim --resolve <seq> --outcome held|failed|superseded`) is also not
due, whatever the outcome: the resolution answered the question the
falsifier was standing in for. `falsifier_stale_findings` folds the due
list into one preflight judgment finding, class `invented-information` -
a theory this old with nothing run or resolved behind it is asserted,
not shown.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle

#: The acceptance case's own number: a falsifier this old and still unrun
#: is not "not yet gotten to", it is a claim standing on nothing.
DEFAULT_MAX_AGE_DAYS = 2


def falsifier_citation(refuted_by: str) -> str:
    """The citation an attestation of `refuted_by` would carry - built the
    same way `run_check` builds one (argv, space-joined, capped at 160), so
    a real run's evidence matches this even when the stored text's own
    whitespace does not."""
    from .godmode_attest import split_command

    try:
        command = split_command(refuted_by)
    except ValueError:
        command = [str(refuted_by)]
    return f"cmd:{' '.join(command)[:160]}"


def due_falsifiers(
    archive: Chronicle,
    now: Any = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[dict[str, Any]]:
    """Claims (grade `hypothesis`) and incidents whose `refuted_by` is old
    and unrun - age from `godmode_status._age_days(recorded_at, now)`.

    "Unrun" means no `attestation` record citing the falsifier's command
    exists with a HIGHER sequence than this record: an attestation from
    before the claim or incident was written proves an earlier state, not
    that this one has been checked.

    A claim or incident that a later resolution record (`claim --resolve
    <seq> --outcome held|failed|superseded`) has already closed is not
    due either, whatever that outcome was: a resolved claim answered the
    question its falsifier was for, so the falsifier is no longer
    standing on nothing.
    """
    from .godmode_status import _age_days

    # `archive.select(kind=..., limit=N)` keeps only its most recent N
    # records (`godmode_chronicle.Chronicle.select`), so an old-enough-to-
    # be-due claim or incident is exactly what a bounded window would age
    # out first - the same loss Task 2's `read_request_window` catches for
    # open asks. This reader is a diagnostic, not a status surface with a
    # human-scale display cap, so it reads unbounded straight off
    # `read_events()`.
    events = archive.read_events()
    claims = [r for r in events if r.get("kind") == "claim"]
    candidates = list(claims)
    candidates += [r for r in events if r.get("kind") == "incident"]
    attestations = [r for r in events if r.get("kind") == "attestation"]

    resolved_at: dict[int, int] = {}
    for record in claims:
        data = record.get("data") or {}
        target = data.get("resolves")
        if target is None:
            continue
        target = int(target)
        seq = int(record.get("sequence", 0) or 0)
        if seq > resolved_at.get(target, -1):
            resolved_at[target] = seq

    due: list[dict[str, Any]] = []
    for record in candidates:
        data = record.get("data") or {}
        refuted_by = data.get("refuted_by")
        if not refuted_by:
            continue
        kind = record.get("kind")
        if kind == "claim" and data.get("grade") != "hypothesis":
            continue
        age = _age_days(record.get("recorded_at"), now)
        if age is None or age < max_age_days:
            continue
        sequence = int(record.get("sequence", 0) or 0)
        resolution_seq = resolved_at.get(sequence)
        if resolution_seq is not None and resolution_seq > sequence:
            continue
        citation = falsifier_citation(str(refuted_by))
        ran = any(
            int(attestation.get("sequence", 0) or 0) > sequence
            and citation in [str(e) for e in (attestation.get("evidence") or [])]
            for attestation in attestations
        )
        if ran:
            continue
        due.append({
            "kind": kind,
            "sequence": sequence,
            "subject": str(record.get("subject", "")),
            "refuted_by": str(refuted_by),
            "age_days": age,
            "citation": citation,
        })
    return due


def falsifier_stale_findings(
    archive: Chronicle,
    now: Any = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[dict[str, str]]:
    """I-3 as a preflight judgment finding: one finding naming every claim
    or incident whose falsifier aged past `max_age_days` with nothing run
    behind it. Class `invented-information` - an unrefuted hypothesis
    standing this long is asserted, not shown."""
    due = due_falsifiers(archive, now=now, max_age_days=max_age_days)
    if not due:
        return []
    named = "; ".join(
        f"{row['kind']} seq {row['sequence']} {row['subject'][:60]!r} "
        f"({row['age_days']}d unrun: {row['refuted_by'][:60]!r})"
        for row in due[:5]
    )
    more = f" (+{len(due) - 5} more)" if len(due) > 5 else ""
    return [{
        "check": "falsifier-stale",
        "class": "invented-information",
        "detail": (f"{len(due)} falsifier(s) aged past {max_age_days}d with no run "
                   f"behind them: {named}{more}. `godmode verify --falsifiers` runs "
                   "the due ones."),
    }]
