"""The mandatory task-completion report: derived from records, never composed.

A completion summary is written at the exact moment a session is least reliable
about itself - the work feels finished, so the summary describes the intention
rather than the record, and the next reader inherits the intention as fact. So
every field here is assembled from archive records and read-only git
observation, and the status verdict is a derivation the records must support:
"verified" is only reachable when no claim this session was downgraded and
session close would actually pass, and a blocked gate makes the report say
"blocked" no matter how the session felt about its progress.

Each field also carries an uncertainty label from the fixed vocabulary, because
a report whose every line reads with equal confidence teaches the reader to
trust the least certain line as much as the most. A git state was observed; a
next action is a hypothesis until someone takes it; a scan that never ran
supports nothing - and the label says so on the line itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_anchor import ProjectAnchor, run_git
from .godmode_attest import close_session, latest_session
from .godmode_charter import compile_charter
from .godmode_chronicle import Chronicle
from .godmode_egress import scan_staged
from .godmode_errors import ArchiveError
from .godmode_lens import observe_git
from .godmode_plan import active_plan
from .godmode_reconcile import reconcile_docs, reconcile_versions
from .godmode_status import items as status_items
from .godmode_status import remaining

# The full uncertainty vocabulary. Every field label must come from here, so a
# report cannot invent a softer or grander word for how sure it is.
UNCERTAINTY_LABELS = (
    "observed",
    "hypothesis",
    "rooted",
    "fixed locally",
    "verified",
    "blocked",
    "human-only",
)

STATUS_VALUES = ("verified", "partially verified", "blocked", "no change required")

# The twelve mandatory fields, in the order they render. The order is part of
# the contract: a reader scans for a field by position, not by re-reading.
FIELD_ORDER = (
    "task",
    "status",
    "what_changed",
    "actions_taken",
    "evidence",
    "security_privacy",
    "git_state",
    "version_state",
    "sprint_state",
    "documentation",
    "remaining",
    "next_safe_action",
)


def _field(value: str, label: str, detail: Any = None) -> dict[str, Any]:
    assert label in UNCERTAINTY_LABELS, label
    return {"value": value, "label": label, "detail": detail}


def _session_records(records: list[dict[str, Any]], session: str | None) -> list[dict[str, Any]]:
    """Records belonging to one session: tagged with its id, or written inside
    its span (between its opening record and the next session's).

    Both tests are needed because not every record kind carries a session tag -
    checkpoints and actions do not - while tagged records (an approved plan
    executed later, say) can land outside the span.
    """
    if not session:
        return []
    start: int | None = None
    end: int | None = None
    for record in records:
        if record["kind"] != "session":
            continue
        if f"S-{record['record_hash'][:12]}" == session:
            start = record["sequence"]
        elif start is not None and end is None and record["sequence"] > start:
            end = record["sequence"]
    members = []
    for record in records:
        data = record.get("data")
        tagged = isinstance(data, dict) and data.get("session") == session
        spanned = (
            start is not None
            and record["sequence"] > start
            and (end is None or record["sequence"] < end)
        )
        if tagged or spanned:
            members.append(record)
    return members


def _latest_checkpoint(
    session_records: list[dict[str, Any]], records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for pool in (session_records, records):
        for record in reversed(pool):
            if record["kind"] == "checkpoint":
                return record
    return None


def _blocked_gates(session_records: list[dict[str, Any]]) -> list[str]:
    """Subjects whose latest attestation this session is `blocked`.

    Latest per subject, because a check that failed and later passed was a
    detour, not a standing block.
    """
    latest: dict[str, str] = {}
    for record in session_records:
        if record["kind"] == "attestation":
            latest[record["subject"]] = str(record["data"].get("status", ""))
    return sorted(subject for subject, status in latest.items() if status == "blocked")


def _derive_status(
    archive: Chronicle,
    project: Path,
    session: str | None,
    session_records: list[dict[str, Any]],
    charter: dict[str, Any],
) -> dict[str, Any]:
    changes = [r for r in session_records if r["kind"] == "change"]
    blocked = _blocked_gates(session_records)
    downgraded = [
        r["subject"]
        for r in session_records
        if r["kind"] == "claim" and r["data"].get("downgraded")
    ]
    close_would_pass = False
    if session:
        close_would_pass = bool(close_session(archive, session, charter)["closed"])

    if blocked:
        value = "blocked"
    elif not changes:
        value = "no change required"
    elif not downgraded and close_would_pass:
        value = "verified"
    else:
        value = "partially verified"

    label = value if value in ("verified", "blocked") else "observed"
    return _field(
        value,
        label,
        {
            "derived": True,
            "changes": len(changes),
            "blocked_gates": blocked,
            "downgraded_claims": downgraded,
            "close_would_pass": close_would_pass,
        },
    )


def _git_operations(project: Path) -> list[str]:
    git_dir = run_git(project, "rev-parse", "--git-dir")
    if not git_dir:
        return []
    base = Path(git_dir)
    if not base.is_absolute():
        base = project / base
    markers = {
        "MERGE_HEAD": "merge",
        "CHERRY_PICK_HEAD": "cherry-pick",
        "REVERT_HEAD": "revert",
        "BISECT_LOG": "bisect",
        "rebase-merge": "rebase",
        "rebase-apply": "rebase",
    }
    return sorted({name for marker, name in markers.items() if (base / marker).exists()})


def _git_state(anchor: ProjectAnchor, project: Path) -> dict[str, Any]:
    if not anchor.is_git:
        return _field("not a Git repository", "observed", {"is_git": False})
    observed = observe_git(anchor)
    dirty = len(observed.get("changes", []))
    operations = _git_operations(project)
    head = (observed.get("head") or "")[:12] or "(no head)"
    value = f"branch {observed.get('branch') or '(detached)'} at {head}, {dirty} dirty file(s)"
    if operations:
        value += f", in progress: {', '.join(operations)}"
    return _field(value, "observed", {
        "branch": observed.get("branch"),
        "head": observed.get("head"),
        "dirty": dirty,
        "in_progress": operations,
    })


def _security_privacy(project: Path) -> dict[str, Any]:
    scan = scan_staged(project)
    scanned = not any(str(s).startswith("unavailable") for s in scan["sources"])
    if scan["findings"]:
        kinds = sorted({f["kind"] for f in scan["findings"]})
        return _field(
            f"{len(scan['findings'])} secret-shaped finding(s) in staged content ({', '.join(kinds)})",
            "observed",
            scan["findings"],
        )
    if scanned:
        # The exact sentence is only earned by an actual scan; without one the
        # words would vouch for content nothing looked at.
        return _field("no secret-shaped values in staged content", "observed", scan["sources"])
    return _field(
        "not checked: no scannable staging boundary (not a Git repository)",
        "hypothesis",
        scan["sources"],
    )


def _version_state(project: Path) -> dict[str, Any]:
    try:
        verdict = reconcile_versions(project)
    except ArchiveError:
        return _field("no version surfaces found to reconcile", "observed", None)
    versions = ", ".join(verdict["distinct_versions"])
    return _field(f"{verdict['verdict']} ({versions})", "observed", verdict["surfaces"])


def _documentation(project: Path) -> dict[str, Any]:
    try:
        verdict = reconcile_docs(project)
    except ArchiveError:
        return _field(
            "not checked: the documentation reconciler needs a Git repository",
            "hypothesis",
            None,
        )
    if verdict["missing"]:
        triggers = ", ".join(entry["trigger"] for entry in verdict["missing"])
        return _field(
            f"documentation-missing: changes under {triggers} lack their counterpart",
            "observed",
            verdict["missing"],
        )
    return _field("reconciled", "observed", None)


def _next_safe_action(
    checkpoint: dict[str, Any] | None,
    blocked: list[str],
    left: dict[str, Any],
) -> dict[str, Any]:
    if checkpoint and str(checkpoint["data"].get("next", "")).strip():
        return _field(str(checkpoint["data"]["next"]).strip(), "hypothesis",
                      {"source": f"checkpoint seq:{checkpoint['sequence']}"})
    if blocked:
        return _field(f"unblock the blocked gate '{blocked[0]}' before anything else",
                      "hypothesis", {"source": "blocking gap", "gates": blocked})
    if left["remaining"]:
        first = left["remaining"][0]
        return _field(f"address remaining {first['source']} item: {first['detail']}",
                      "hypothesis", {"source": "remaining", "item": first})
    return _field("nothing outstanding; record a checkpoint before ending the session",
                  "hypothesis", None)


def completion_report(
    archive: Chronicle,
    anchor: ProjectAnchor,
    project: Path,
    session: str | None = None,
) -> dict[str, Any]:
    """Assemble the twelve mandatory fields from records and read-only git state."""
    project = Path(project)
    session = session or latest_session(archive)
    records = archive.read_events() if archive.initialized() else []
    session_records = _session_records(records, session)
    charter = compile_charter(project)
    checkpoint = _latest_checkpoint(session_records, records)

    plan = active_plan(archive)
    if plan:
        task = _field(plan["title"], "observed", {"plan": plan["id"], "state": plan["state"]})
    elif checkpoint:
        task = _field(checkpoint["subject"], "observed",
                      {"checkpoint": f"seq:{checkpoint['sequence']}"})
    else:
        task = _field("(no plan or checkpoint recorded)", "observed", None)

    changes = [
        {"summary": r["subject"], "files": sorted(r["data"].get("files", []))}
        for r in session_records
        if r["kind"] == "change"
    ]
    if changes:
        summarised = "; ".join(
            f"{c['summary']} ({', '.join(c['files']) or 'no files listed'})" for c in changes[:6]
        )
        what_changed = _field(f"{len(changes)} change(s): {summarised}", "observed", changes)
    else:
        what_changed = _field("no change records this session", "observed", [])

    actions = [r["subject"] for r in session_records if r["kind"] == "action"]
    actions_taken = _field(
        f"{len(actions)} action(s): {'; '.join(actions[:8])}" if actions
        else "no action records this session",
        "observed",
        actions,
    )

    cited: set[str] = set()
    for record in session_records:
        if record["kind"] in ("claim", "attestation"):
            cited.update(record.get("evidence", []))
    refs = sorted(cited)
    evidence = _field(
        f"{len(refs)} evidence ref(s): {'; '.join(refs[:8])}" if refs
        else "no evidence cited this session",
        "observed",
        refs,
    )

    status = _derive_status(archive, project, session, session_records, charter)
    blocked = status["detail"]["blocked_gates"]

    counts: dict[str, int] = {}
    for entry in status_items(archive).values():
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1
    sprint_state = _field(
        ", ".join(f"{n} {state}" for state, n in sorted(counts.items())) if counts
        else "no sprint items recorded",
        "observed",
        counts,
    )

    left = remaining(archive, project, session=session, charter=charter)
    top = [f"{entry['source']}: {entry['detail']}" for entry in left["remaining"][:5]]
    remaining_field = _field(
        f"{left['count']} item(s) remaining over {left['complete_over']}"
        + (f": {'; '.join(top)}" if top else ""),
        "observed",
        {"count": left["count"], "top": top, "complete_over": left["complete_over"]},
    )

    fields = {
        "task": task,
        "status": status,
        "what_changed": what_changed,
        "actions_taken": actions_taken,
        "evidence": evidence,
        "security_privacy": _security_privacy(project),
        "git_state": _git_state(anchor, project),
        "version_state": _version_state(project),
        "sprint_state": sprint_state,
        "documentation": _documentation(project),
        "remaining": remaining_field,
        "next_safe_action": _next_safe_action(checkpoint, blocked, left),
    }
    return {
        "report": "task-completion",
        "session": session,
        "field_order": list(FIELD_ORDER),
        "fields": fields,
        "label_vocabulary": list(UNCERTAINTY_LABELS),
    }


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "; ")


def render_markdown(report: dict[str, Any]) -> str:
    """The report as one markdown table, fields in their fixed order."""
    lines = [
        "# TASK COMPLETION REPORT",
        "",
        f"session: {report.get('session') or '(none)'}",
        "",
        "| field | value | label |",
        "| --- | --- | --- |",
    ]
    fields = report["fields"]
    for name in FIELD_ORDER:
        entry = fields[name]
        lines.append(f"| {name} | {_cell(entry['value'])} | {_cell(entry['label'])} |")
    return "\n".join(lines) + "\n"
