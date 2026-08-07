"""What Godmode did this session, counted from its own records.

A gate is only ever visible as friction. The refusals are felt; the reason they
were worth it is not, because nothing shows the session what the runtime
actually did. This closes that loop at the moment a session ends.

The framing is deliberate and narrow: this reports **activity**, never averted
disaster. A blocked check is a blocked check - whether it would have become a
production incident is a counterfactual nobody can measure, and asserting it
would be exactly the unfalsifiable claim `record_claim` downgrades everywhere
else. So the numbers are refusals recorded, each carrying the record sequences
that produced it, and the caveat travels with them.

One number here is a genuine saving rather than an activity count: context
reduction is measured - the bounded brief against the raw record mass - so it
is labelled `measured` and the rest are not.

Silence is the default when nothing happened. A summary that prints "0 blocks"
every session is training the reader to skip the line that will one day say
something.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle

REPORT_FILENAME = ".godmode-report.json"

_CAVEAT = (
    "Refusals recorded, not disasters averted: whether a blocked step would "
    "have become a defect is not something this can measure."
)


def summary_enabled(project: Path) -> bool:
    """Opt out with `.godmode-report.json` {"session_summary": false}.

    A malformed file leaves the summary on: losing the report is a smaller
    failure than silently disabling it because a file had a typo.
    """
    config = Path(project) / REPORT_FILENAME
    if not config.is_file():
        return True
    try:
        declared = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(declared, dict):
        return True
    return declared.get("session_summary") is not False


def _session_records(archive: Chronicle, session: str) -> list[dict[str, Any]]:
    """Records belonging to this session: tagged ones, plus the untagged records
    written after it opened, since checkpoints and incidents carry no session."""
    records = archive.read_events()
    start = 0
    for record in records:
        if record["kind"] == "session" and f"S-{record['record_hash'][:12]}" == session:
            start = record["sequence"]
            break
    selected = []
    for record in records:
        if record["sequence"] < start:
            continue
        tag = record["data"].get("session")
        if tag is None or tag == session:
            selected.append(record)
    return selected


def _counted(records: list[dict[str, Any]], predicate: Any, description: str) -> dict[str, Any]:
    hits = [r for r in records if predicate(r)]
    return {
        "count": len(hits),
        "what": description,
        # The sequences make the number checkable instead of trusted.
        "records": [f"seq:{r['sequence']}" for r in hits[:10]],
    }


def contribution(archive: Chronicle, project: Path, session: str) -> dict[str, Any]:
    """Count this session's refusals, and measure what bounding actually saved."""
    project = Path(project)
    if not summary_enabled(project):
        return {"session": session, "reportable": False,
                "disabled_by": REPORT_FILENAME,
                "activity": {}, "context": {}, "caveat": _CAVEAT}

    records = _session_records(archive, session)

    activity = {
        "checks_blocked": _counted(
            records,
            lambda r: (r["kind"] == "attestation" and r["data"].get("status") == "blocked"),
            "a declared check exited non-zero and could not be attested as passing"),
        "claims_downgraded": _counted(
            records,
            lambda r: r["kind"] == "claim" and r["data"].get("downgraded"),
            "a claim was stored at a lower grade than asserted"),
        "steps_skipped": _counted(
            records,
            lambda r: (r["kind"] == "attestation" and r["data"].get("status") == "skipped"),
            "a mandated step was skipped and recorded as such"),
        "secrets_caught": _counted(
            records,
            lambda r: (r["kind"] == "incident"
                       and "secret" in r["subject"].lower()
                       and r["data"].get("status") == "blocked"),
            "a secret-shaped value was refused before it was written"),
        "scope_drift": _counted(
            records,
            lambda r: r["kind"] == "change" and r["data"].get("drift"),
            "work landed outside the plan's declared scope"),
        "removals_recorded": _counted(
            records,
            lambda r: r["kind"] == "decision" and r["subject"].startswith("removal:"),
            "a deletion was recorded with the reason it happened"),
    }

    context: dict[str, Any] = {"basis": "measured"}
    try:
        from .godmode_lens import build_context_brief

        raw = max(1, len(json.dumps(archive.read_events(), ensure_ascii=False,
                                    default=str)) // 4)
        bounded = int(build_context_brief(archive.anchor, archive)["estimated_tokens"])
        context.update({
            "raw_tokens": raw,
            "bounded_tokens": bounded,
            "reduction": round(max(0.0, 1 - bounded / raw), 4),
        })
    except Exception:  # pragma: no cover - a brief that cannot build measures nothing
        context = {"basis": "unavailable", "reduction": 0}

    fired = sum(entry["count"] for entry in activity.values())
    # Bounding a handful of records is arithmetic, not a saving worth a line.
    # Only a substantial reduction over a substantial archive stands on its own.
    meaningful_bounding = (context.get("reduction", 0) >= 0.10
                           and context.get("raw_tokens", 0) >= 1_000)
    reportable = bool(fired) or meaningful_bounding
    return {
        "session": session,
        "activity": activity,
        "context": context,
        "actions_recorded": fired,
        "reportable": reportable,
        "caveat": _CAVEAT,
    }


def render_line(report: dict[str, Any]) -> str | None:
    """One line, or nothing at all when the session was quiet."""
    if not report.get("reportable"):
        return None
    parts: list[str] = []
    labels = {
        "checks_blocked": "checks blocked",
        "claims_downgraded": "claims downgraded",
        "steps_skipped": "steps skipped",
        "secrets_caught": "secrets refused",
        "scope_drift": "scope drifts",
        "removals_recorded": "removals recorded",
    }
    cited: list[str] = []
    for name, label in labels.items():
        entry = report["activity"].get(name) or {}
        if entry.get("count"):
            parts.append(f"{entry['count']} {label}")
            cited.extend(entry["records"][:3])
    context = report.get("context") or {}
    if context.get("reduction"):
        parts.append(
            f"context bounded to {context['bounded_tokens']:,} of "
            f"{context['raw_tokens']:,} est. tokens ({context['reduction']:.0%})")
    if not parts:
        return None
    line = "Godmode this session: " + " · ".join(parts) + "."
    if cited:
        line += f" See {', '.join(dict.fromkeys(cited))}."
    return line + f" {_CAVEAT}"
