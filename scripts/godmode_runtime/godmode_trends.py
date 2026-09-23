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

from datetime import datetime, timedelta, timezone
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import RUNTIME_VERSION
from .godmode_metrics import agentic_ratios

_SUBJECT = "session measurement"

# The counted fields a measured row carries, in render order. A gap row
# carries NONE of them - absence is the statement.
_COUNT_FIELDS = ("turns", "commands", "test_runs", "tokens_in", "tokens_out")

_BASIS_CAP = 200

_PREFLIGHT_SUBJECT = "preflight"


def _findings_by_class(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """N-12: one row per class per preflight attestation, oldest first.
    `recurring` is true when the immediately preceding preflight
    attestation also carried this class - the same failure walking into
    two consecutive rounds, not merely showing up twice ever."""
    rows: list[dict[str, Any]] = []
    previous_classes: set[str] = set()
    for record in records:
        data = record.get("data") or {}
        classes = data.get("classes")
        label = data.get("session") or f"seq:{record['sequence']}"
        current_classes: set[str] = set()
        if isinstance(classes, dict):
            for cls, count in classes.items():
                current_classes.add(cls)
                rows.append({
                    "class": cls,
                    "sprint_or_session": label,
                    "count": int(count) if isinstance(count, (int, float)) else 0,
                    "recurring": cls in previous_classes,
                })
        previous_classes = current_classes
    return rows


def record_flaky_retry(archive: Any, test_id: str, outcome: str) -> None:
    """NS-8o: record one isolated rerun of a registered flake. Called by
    the retry runner (`scripts/dev/run_with_flaky_retry.py`) after every
    isolated rerun; a no-op with no archive - the runner works outside a
    project too, and its own bookkeeping must never fail a test run."""
    if archive is None:
        return
    # Final review N9: `evidence=[]` passed explicitly, matching the two
    # sibling bookkeeping writers (`godmode_post_edit._scan_untrusted_result`,
    # `godmode_session_hook._record_usage_observed`) - harmless either way
    # today (an omitted `evidence` already defaults to empty), but
    # gratuitously different from both of them otherwise.
    archive.append("action", "flaky-retry", {
        "test_id": test_id,
        "outcome": outcome,
        "operation": f"flake:{test_id}",
    }, evidence=[])


def flakes(archive: Chronicle) -> list[dict[str, Any]]:
    """NS-8o: one row per flaky test id, ranked by retry count descending.

    `has_lesson` is true when any lesson record's subject or value names
    the id - the id is free text a person chose for the registry entry, so
    a substring match is the honest test of "does a lesson mention this
    flake," the same standard the preflight finding below applies.
    """
    retries: dict[str, dict[str, int]] = {}
    order: list[str] = []
    # S-3: every retry on record. `select` keeps the newest 500, which
    # capped a busy flake's count at 500 and dropped an older flake whole.
    for record in archive.read_events():
        if record["kind"] != "action" or record["subject"] != "flaky-retry":
            continue
        data = record.get("data") or {}
        test_id = str(data.get("test_id", "")).strip()
        if not test_id:
            continue
        if test_id not in retries:
            retries[test_id] = {"retries": 0, "isolated_failures": 0}
            order.append(test_id)
        retries[test_id]["retries"] += 1
        if data.get("outcome") == "failed-isolated":
            retries[test_id]["isolated_failures"] += 1

    # Final review S4: UNBOUNDED (`archive.read_events()`, not
    # `archive.select(...)`) - `Chronicle.select` clamps to the newest 500
    # matching records regardless of what is asked for, so a lesson naming
    # this flake more than 500 lessons ago used to read as absent here.
    # `flake_findings` (`godmode_preflight.py`) turns a flake with
    # `retries >= 3 and not has_lesson` into a gate finding that turns the
    # verdict to `findings` - a false positive an operator cannot fix by
    # adding a lesson that is already there, 501 lessons back. Same
    # reasoning as `godmode_fingerprint.existing_sequences` and the
    # untrusted-digest scan above it in this file's sibling module.
    lessons = [record for record in archive.read_events() if record["kind"] == "lesson"]

    def _has_lesson(test_id: str) -> bool:
        for lesson in lessons:
            if test_id in str(lesson.get("subject", "")):
                return True
            if test_id in str((lesson.get("data") or {}).get("value", "")):
                return True
        return False

    rows = [
        {
            "test_id": test_id,
            "retries": counts["retries"],
            "isolated_failures": counts["isolated_failures"],
            "has_lesson": _has_lesson(test_id),
        }
        for test_id, counts in ((tid, retries[tid]) for tid in order)
    ]
    rows.sort(key=lambda row: row["retries"], reverse=True)
    return rows


def record_flake_parked(archive: Any, test_id: str, reason: str) -> None:
    """NS-10c: the retry runner records this once - the run where it first
    observes the id's own breaker has tripped, never on every subsequent
    parked run. A park is bookkeeping about the flake, not a step this
    trajectory took, so it joins `BOOKKEEPING_SUBJECTS` beside
    `FLAKY_RETRY_SUBJECT` rather than a fifth, independently-typed
    subject."""
    if archive is None:
        return
    archive.append("action", "flake-parked", {
        "test_id": test_id,
        "reason": reason,
        "operation": f"flake:{test_id}",
    }, evidence=[])


def record_flake_readmitted(archive: Any, test_id: str) -> None:
    """NS-10c: the retry runner records this once - the run where cooldown
    has elapsed and the id is treated as closed again. Bookkeeping about
    the flake, same reasoning as `record_flake_parked` above."""
    if archive is None:
        return
    archive.append("action", "flake-readmitted", {
        "test_id": test_id,
        "operation": f"flake:{test_id}",
    }, evidence=[])


def _as_utc(moment: Any) -> datetime:
    """Accept a `datetime` or an ISO string; always return one with a
    timezone, defaulting a naive value to UTC the same way
    `godmode_status._age_days` does for the same reason - a record's own
    `recorded_at` is always UTC ISO, and a caller's naive `now` should
    compare against it rather than raise."""
    if isinstance(moment, datetime):
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(moment))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _record_time(record: dict[str, Any]) -> datetime | None:
    recorded_at = record.get("recorded_at")
    if not isinstance(recorded_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(recorded_at)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _test_rows(archive: Chronicle, subject: str, test_id: str) -> list[dict[str, Any]]:
    return [
        record for record in archive.select(kind="action", subject=subject, limit=500)
        if str((record.get("data") or {}).get("test_id", "")) == test_id
    ]


def _failed_isolated_in_window(
    retries: list[dict[str, Any]], floor_sequence: int, now: datetime, window: timedelta,
) -> list[dict[str, Any]]:
    out = []
    for record in retries:
        if int(record.get("sequence", 0) or 0) <= floor_sequence:
            continue
        if (record.get("data") or {}).get("outcome") != "failed-isolated":
            continue
        when = _record_time(record)
        if when is None or now - when > window:
            continue
        out.append(record)
    return out


def breaker_state(
    archive: Chronicle,
    test_id: str,
    now: Any,
    n: int = 3,
    window_hours: int = 24,
    cooldown_hours: int = 6,
) -> dict[str, Any]:
    """NS-10c: pure trip/cooldown state for one flaky test id, computed
    only from `flaky-retry` (`outcome == "failed-isolated"`),
    `flake-parked`, and `flake-readmitted` action records - never from the
    wall clock, which is always the caller's explicit `now`, the same
    discipline `godmode_falsifiers.due_falsifiers` uses and for the same
    reason: a test cannot pin a clock a pure function reads on its own.

    Trips (`state: "open"`) the moment `n` or more such failures for this
    id land inside the trailing `window_hours` before `now`. Once an
    active `flake-parked` record exists for the id, state stays "open" -
    regardless of any new failures - until `now` reaches `cooldown_hours`
    past THAT record's own `recorded_at`; from then on the id reads as
    freshly reopened and only failures recorded strictly after the park
    (by sequence) count toward a new trip. `newly_tripped` is true exactly
    when this call is the first to observe the trip (no covering park
    record exists yet) - the caller's cue to write `record_flake_parked`
    now, once, rather than on every later parked run. `readmitted` is true
    exactly when this call is the first to observe cooldown has elapsed -
    the caller's cue to write `record_flake_readmitted`.
    """
    current = _as_utc(now)
    window = timedelta(hours=window_hours)
    cooldown = timedelta(hours=cooldown_hours)

    parks = _test_rows(archive, "flake-parked", test_id)
    readmits = _test_rows(archive, "flake-readmitted", test_id)
    retries = _test_rows(archive, "flaky-retry", test_id)

    last_park = max(parks, key=lambda r: int(r.get("sequence", 0) or 0), default=None)
    last_readmit = max(readmits, key=lambda r: int(r.get("sequence", 0) or 0), default=None)
    currently_parked = last_park is not None and (
        last_readmit is None
        or int(last_readmit.get("sequence", 0) or 0) < int(last_park.get("sequence", 0) or 0)
    )

    floor_sequence = 0
    readmitted_now = False
    if currently_parked:
        parked_at = _record_time(last_park)
        if parked_at is not None:
            reopens_at = parked_at + cooldown
            if current < reopens_at:
                failures = _failed_isolated_in_window(retries, 0, current, window)
                return {
                    "state": "open",
                    "failures_in_window": len(failures),
                    "parked_at": parked_at.isoformat(),
                    "reopens_at": reopens_at.isoformat(),
                    "reason": str((last_park.get("data") or {}).get("reason", "")),
                    "newly_tripped": False,
                    "readmitted": False,
                }
            floor_sequence = int(last_park.get("sequence", 0) or 0)
            readmitted_now = True
    elif last_readmit is not None:
        floor_sequence = int(last_readmit.get("sequence", 0) or 0)

    failures = _failed_isolated_in_window(retries, floor_sequence, current, window)
    count = len(failures)
    if count >= n:
        return {
            "state": "open",
            "failures_in_window": count,
            "parked_at": current.isoformat(),
            "reopens_at": (current + cooldown).isoformat(),
            "reason": f"{count} isolated failure(s) within {window_hours}h (threshold {n})",
            "newly_tripped": True,
            "readmitted": readmitted_now,
        }
    return {
        "state": "closed",
        "failures_in_window": count,
        "parked_at": None,
        "reopens_at": None,
        "reason": None,
        "newly_tripped": False,
        "readmitted": readmitted_now,
    }


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

    # The per-session series above groups by the `session measurement`
    # record's own `data.session` field - there is no equivalent per-record
    # field to group agentic ratios by version: `runtime_version` is stamped
    # once on the archive's own config (`Chronicle.initialize`), not on each
    # record, so there is exactly one version to report the whole archive
    # against - the one computing this report, named rather than fabricated
    # as a history nothing recorded.
    all_records = archive.read_events()
    agentic = [
        {"metric": name, "version": RUNTIME_VERSION,
         "value": None if value is None else round(value, 4)}
        for name, (value, _basis) in agentic_ratios(all_records).items()
    ]

    preflight_records = [
        record for record in all_records
        if record["kind"] == "attestation" and record["subject"] == _PREFLIGHT_SUBJECT
    ]
    if sessions is not None and sessions > 0:
        preflight_records = preflight_records[-sessions:]
    findings_by_class = _findings_by_class(preflight_records)

    # NS-13c: the PDCA row - records per phase of the latest cycle, and a
    # stalled Check named when changes landed with no retest since.
    from .godmode_stages import pdca_cycle
    return {"series": series, "gaps": gaps, "basis": basis, "agentic": agentic,
            "findings_by_class": findings_by_class, "flakes": flakes(archive),
            "pdca": pdca_cycle(all_records)}


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
    for row in report.get("agentic", []):
        value = "insufficient data" if row["value"] is None else row["value"]
        lines.append(f"  agentic[{row['version']}] {row['metric']}: {value}")
    if report.get("pdca") is not None:
        from .godmode_stages import render_pdca
        lines.append("  " + render_pdca(report["pdca"]))
    return "\n".join(lines) + "\n"
