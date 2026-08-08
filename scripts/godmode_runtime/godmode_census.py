"""Which of this product's own surfaces have never been used here.

Establishing that `claim`, `attest`, `experiment` and `lessons` had zero records
took a manual investigation. The archive knew the whole time.

Every project accumulates surfaces nobody uses, and the cost is invisible in the
usual signals: the tests pass, the documentation is accurate, the front page
demonstrates the feature. Only the record shows that nothing ever exercised it.

This applies the product's own standard to the product's own description of
itself. It reports and never removes: a surface unused in one project may be
the reason someone adopted it in another, so the census answers "was this used
here" and leaves "should it exist" to a person.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle

# Record kinds a capability writes when it is genuinely used, with the surface
# a reader would recognise. A kind absent from the archive means the surface was
# never exercised in this project.
TRACKED_SURFACES: dict[str, str] = {
    "claim": "claim - assertions downgraded when their citations do not resolve",
    "attestation": "attest / session close - steps witnessed against charter rules",
    "action": "gate / authorize - protected actions previewed before running",
    "experiment": "experiment - bounded one-variable investigations",
    "lesson": "lessons - generalisations recorded after a mechanism is understood",
    # `mistakes` is a detector over existing records, not a recorder, so it
    # has no kind of its own. Listing one here declared a surface the archive
    # can never hold, which would have read as permanently unused rather than
    # as impossible - a census reporting a shortfall nothing could ever close.
    "incident": "incident - a failure recorded so its shape can be compared later",
    "checkpoint": "checkpoint - handoffs that survive a lost session",
    "decision": "decision - choices recorded with their rationale",
    "sprint": "sprint - units of work and their proof",
    "inventory": "inventory - the baseline a resume is measured against",
}


def uncaptured_corrections(archive: Chronicle) -> dict[str, Any]:
    """Times the runtime corrected a claim, against lessons actually recorded.

    A miss acknowledged in conversation dies with the session; a miss written
    down cannot repeat. The ledger this comes from makes that a standing
    directive and still records recurrences, because the acknowledgement is the
    easy half.

    A downgraded claim is the one correction this runtime can see for itself:
    the author asserted something and the record refused it. If that happened
    and no lesson was written, the correction exists only in whatever the agent
    said at the time.
    """
    records = archive.read_events()
    downgraded = [
        record for record in records
        if record.get("kind") == "claim" and (record.get("data") or {}).get("downgraded")
    ]
    lessons = [record for record in records if record.get("kind") == "lesson"]

    if not downgraded:
        verdict = "nothing-to-record"
    elif lessons:
        verdict = "corrections-recorded"
    else:
        verdict = "corrections-unrecorded"

    return {
        "downgraded": len(downgraded),
        "lessons": len(lessons),
        "examples": [record["subject"][:100] for record in downgraded[-3:]],
        "verdict": verdict,
        "question": "a correction only recorded in conversation cannot stop the "
                    "next one; record it with `remember --kind lesson`",
    }


# A surface that records itself under another kind. The experiment loop writes
# an `action` record with an `experiment:` subject, so a census keyed on kind
# alone reported the surface as never used minutes after it ran — a false
# negative in the very tool built to find dead surfaces.
_SUBJECT_PREFIXES: dict[str, str] = {"experiment": "experiment:"}


def census(archive: Chronicle) -> dict[str, Any]:
    """Compare the declared surface against what the archive actually holds."""
    records = archive.read_events()
    seen: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind", ""))
        seen[kind] = seen.get(kind, 0) + 1
        subject = str(record.get("subject", ""))
        for surface, prefix in _SUBJECT_PREFIXES.items():
            if subject.startswith(prefix):
                seen[surface] = seen.get(surface, 0) + 1

    used: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    for kind, description in sorted(TRACKED_SURFACES.items()):
        entry = {"kind": kind, "surface": description, "records": seen.get(kind, 0)}
        (used if entry["records"] else unused).append(entry)

    # Kinds present in the archive that nothing here declares. Reported so the
    # census cannot quietly describe a smaller product than the one running.
    undeclared = sorted(set(seen) - set(TRACKED_SURFACES))

    return {
        "records_examined": len(records),
        "used": used,
        "unused": unused,
        "undeclared_kinds": undeclared,
        "scope": "this project only; a surface unused here may be used elsewhere",
        # Reported, never a failure: the census asks what happened, not what
        # ought to have.
        "verdict": "complete-usage" if not unused else "unused-surfaces-present",
    }


def render(report: dict[str, Any]) -> str:
    """One line per unused surface, for a reader rather than a parser."""
    if not report["unused"]:
        return "every tracked surface has been used in this project."
    total = len(report["used"]) + len(report["unused"])
    lines = [f"{len(report['unused'])} of {total} tracked surfaces have never "
             "been used in this project:"]
    lines.extend(f"  never used - {entry['surface']}" for entry in report["unused"])
    lines.append("Reported, not judged: unused here is not unused everywhere.")
    return "\n".join(lines)


def _self_check() -> None:
    class _Fake:
        def __init__(self, kinds: list[str]) -> None:
            self._records = [{"kind": kind} for kind in kinds]

        def read_events(self) -> list[dict[str, Any]]:
            return self._records

    report = census(_Fake(["checkpoint", "checkpoint", "decision", "wildcard"]))  # type: ignore[arg-type]
    unused = {entry["kind"] for entry in report["unused"]}
    assert "claim" in unused, report
    assert "attestation" in unused, report
    assert "checkpoint" not in unused, report
    assert report["undeclared_kinds"] == ["wildcard"], report
    assert report["verdict"] == "unused-surfaces-present", report
    assert "never used" in render(report)

    full = census(_Fake(list(TRACKED_SURFACES)))  # type: ignore[arg-type]
    assert full["verdict"] == "complete-usage", full
    assert "every tracked surface" in render(full)

    print("godmode_census self-check OK")
