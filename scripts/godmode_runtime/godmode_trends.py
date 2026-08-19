"""B4-5: per-session counts as a time series, gaps stated, no causal words.

The session-log writes one `metric` record per session - counts only, or a
stated gap when the transcript could not be read (`measured: False` plus the
reason). This module folds those records into a series and renders it. Two
disciplines are load-bearing and tested, both inherited from the ROI
reports that pinned them first:

- CAUSAL_DENYLIST: the render names what was counted, never what the counts
  supposedly earned or averted. Trends and counts, not causation - the
  design doc's own words.
- C-79, gaps stay gaps: an unmeasured session appears in the series as a
  stated gap with its reason, and never carries a number. Interpolating a
  plausible value for a session nobody measured is how a report starts
  lying politely.

Counts and `seq:` references only - a record's free-text fields never reach
the report or the render, same as every other fold beside it.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle

_SUBJECT = "session measurement"

# The counted fields a measured row carries, in render order. A gap row
# carries NONE of them - absence is the statement.
_COUNT_FIELDS = ("turns", "commands", "test_runs", "tokens_in", "tokens_out")

_BASIS_CAP = 200


def trends_report(archive: Chronicle, sessions: int | None = None) -> dict[str, Any]:
    """The ordered series of session measurements, oldest first.

    `sessions` bounds the series to the most recent N measurement records
    (measured and gap alike - a window that silently skipped gaps would
    overstate coverage).
    """
    records = [
        record for record in archive.read_events()
        if record["kind"] == "metric" and record["subject"] == _SUBJECT
    ]
    if sessions is not None and sessions > 0:
        records = records[-sessions:]

    series: list[dict[str, Any]] = []
    gaps = 0
    basis: list[str] = []
    for record in records:
        data = record.get("data") or {}
        row: dict[str, Any] = {
            "sequence": record["sequence"],
            "session": data.get("session"),
            "measured": bool(data.get("measured")),
        }
        if row["measured"]:
            for field in _COUNT_FIELDS:
                value = data.get(field)
                row[field] = int(value) if isinstance(value, (int, float)) else 0
            tool_calls = data.get("tool_calls")
            row["tool_calls_total"] = (
                sum(int(v) for v in tool_calls.values())
                if isinstance(tool_calls, dict) else 0
            )
        else:
            gaps += 1
            row["reason"] = str(data.get("reason", "unmeasured"))[:120]
        if len(basis) < _BASIS_CAP:
            basis.append(f"seq:{record['sequence']}")
        series.append(row)

    return {"series": series, "gaps": gaps, "basis": basis}


def render_trends(report: dict[str, Any]) -> str:
    """One line per session, counts or a stated gap - nothing else."""
    lines = [
        "GODMODE TRENDS - per-session counts from local measurement records; "
        "trends and counts, not causation",
    ]
    if not report["series"]:
        lines.append("no session measurements on record")
    for row in report["series"]:
        name = row.get("session") or f"seq:{row['sequence']}"
        if row["measured"]:
            lines.append(
                f"  {name}: turns={row['turns']} commands={row['commands']} "
                f"test_runs={row['test_runs']} tool_calls={row['tool_calls_total']} "
                f"tokens_in={row['tokens_in']} tokens_out={row['tokens_out']}"
            )
        else:
            lines.append(f"  {name}: unmeasured ({row['reason']})")
    if report["gaps"]:
        lines.append(f"gaps: {report['gaps']} session(s) unmeasured - stated, "
                     "never interpolated")
    lines.append("Basis: " + (", ".join(report["basis"]) if report["basis"] else "(none)"))
    return "\n".join(lines) + "\n"
