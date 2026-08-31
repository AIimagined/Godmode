"""Whether the product works, measured — not whether its tests pass.

A green suite proves the code does what it was written to do. It says nothing
about whether the thing being built actually prevents the failures it exists to
prevent: whether a resumed session picks up the stated next action, whether a
root cause survives scrutiny, whether finished work stays finished. Those are
properties of the record the product produced while being used, so they are
computed from the archive rather than asserted.

Two rules keep the numbers honest:

* A metric with no denominator reports `insufficient-data` and a null value. A
  zero-over-zero rendered as 1.0 is the cheapest way to look healthy while
  measuring nothing, and it is exactly the self-report this project exists to
  refuse.
* Every metric states its `basis` - what was counted - so a suspicious number
  can be checked against the records instead of believed.

Nothing here transmits: the metrics are computed locally and printed locally.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle

# metric -> (target value, comparison, prose target for the report)
_TARGETS: dict[str, tuple[float | None, str, str]] = {
    "resume_accuracy": (0.9, ">=", ">= 0.9"),
    # A similarity heuristic generates leads, not verdicts: a hard target here
    # would read red forever on near-names and train the reader to ignore it.
    "duplicate_build_prevention": (None, "", "reported; each pair is a lead to judge"),
    "rca_precision": (0.8, ">=", ">= 0.8"),
    "same_root_recurrence": (0.03, "<", "< 0.03"),
    "regression_escape": (0, "<=", "0 reversals"),
    "false_complete_rate": (0.02, "<", "< 0.02"),
    "action_transparency": (1.0, ">=", "1.0"),
    "documentation_parity": (0.98, ">=", ">= 0.98"),
    "token_reduction": (0.6, ">=", ">= 0.6"),
    "gate_effectiveness": (None, "", "reported, no target"),
    "evidence_density": (1.0, ">=", ">= 1.0"),
    "attestation_coverage": (0.9, ">=", ">= 0.9"),
}

METRIC_ORDER: tuple[str, ...] = tuple(_TARGETS)

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "run",
    "then", "next", "this", "that", "it", "is", "be", "at", "by", "from",
})


def _tokens(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]+", str(text).lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def _entry(value: float | None, name: str, basis: str) -> dict[str, Any]:
    target, comparison, prose = _TARGETS[name]
    if value is None:
        return {"value": None, "target": prose, "meets_target": None,
                "basis": basis, "confidence": "insufficient-data"}
    meets: bool | None
    if target is None:
        meets = None
    elif comparison == ">=":
        meets = value >= target
    elif comparison == "<":
        meets = value < target
    else:
        meets = value <= target
    return {"value": round(value, 4), "target": prose, "meets_target": meets,
            "basis": basis, "confidence": "measured"}


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


def _resume_accuracy(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    """Did the session that followed a checkpoint do what the checkpoint said next?"""
    checkpoints = [r for r in records if r["kind"] == "checkpoint" and r["data"].get("next")]
    considered = followed = 0
    for checkpoint in checkpoints:
        after = [r for r in records if r["sequence"] > checkpoint["sequence"]]
        opening = next((r for r in after if r["kind"] == "session"), None)
        if opening is None:
            continue
        first_work = next(
            (r for r in after
             if r["sequence"] > opening["sequence"]
             and r["kind"] in ("attestation", "change", "action")), None)
        if first_work is None:
            continue
        considered += 1
        stated = checkpoint["data"]["next"]
        wanted = _tokens(" ".join(stated) if isinstance(stated, list) else stated)
        if wanted & _tokens(first_work["subject"]):
            followed += 1
    return _ratio(followed, considered), f"{followed} of {considered} resumed sessions"


def _rca_precision(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    claims = [
        r for r in records
        if r["kind"] == "claim"
        and "root cause" in str(r["data"].get("text", r["subject"])).lower()
    ]
    held = [r for r in claims if not r["data"].get("downgraded")]
    return _ratio(len(held), len(claims)), f"{len(held)} of {len(claims)} root-cause claims held"


def _same_root_recurrence(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    subjects: dict[str, int] = {}
    for record in records:
        if record["kind"] in ("incident", "lesson"):
            subjects[record["subject"]] = subjects.get(record["subject"], 0) + 1
    repeated = sum(1 for count in subjects.values() if count > 1)
    return _ratio(repeated, len(subjects)), f"{repeated} of {len(subjects)} roots recurred"


def _false_complete_rate(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    """Work that reached a terminal state and had to be reopened with proof."""
    terminal: set[str] = set()
    reopened: set[str] = set()
    for record in records:
        if record["kind"] != "sprint" or "state" not in record["data"]:
            continue
        state = record["data"]["state"]
        if state in ("verified", "closed"):
            terminal.add(record["subject"])
        elif record["subject"] in terminal and str(record["data"].get("proof", "")).strip():
            reopened.add(record["subject"])
    return _ratio(len(reopened), len(terminal)), f"{len(reopened)} of {len(terminal)} finished items reopened"


def _action_transparency(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    actions = [r for r in records if r["kind"] == "action"]
    if not actions:
        return None, "0 action records"
    previewed = sum(
        1 for action in actions
        if any(r["kind"] == "attestation" and r["sequence"] < action["sequence"]
               and (r["subject"].startswith(("guard:", "check:", "preview"))
                    or "guard" in r["subject"])
               for r in records)
    )
    return _ratio(previewed, len(actions)), f"{previewed} of {len(actions)} actions preceded by a check"


def _token_reduction(archive: Chronicle, records: list[dict[str, Any]]) -> tuple[float | None, str]:
    """How much of the raw record mass the bounded brief spares the model.

    Prefers a real basis over a guess. C-79/U-T1's session-log measurement
    writes `metric` records with `measured: True` and a real `tokens_in`
    read from the host's own transcript usage blocks - when this window
    holds at least one, their summed `tokens_in` IS what the session
    actually spent, and that replaces the byte-length guess entirely rather
    than blending with it. A `measured: False` record is a stated gap, not a
    zero, and must not be summed as though the session spent nothing. Falls
    back to the `len(json.dumps(records))//4` heuristic only when no
    measured record is present in this window. Either way the basis string
    names which one was used, so a suspicious number can be checked against
    which kind of basis produced it.
    """
    if not records:
        return None, "no records to bound"
    measured_tokens = sum(
        int(r["data"].get("tokens_in") or 0)
        for r in records
        if r["kind"] == "metric" and r["data"].get("measured") is True
    )
    if measured_tokens > 0:
        raw = measured_tokens
        basis_kind = "measured"
    else:
        raw = max(1, len(json.dumps(records, ensure_ascii=False, default=str)) // 4)
        basis_kind = "estimated"
    try:
        from .godmode_lens import build_context_brief

        brief = build_context_brief(archive.anchor, archive)
        bounded = int(brief.get("estimated_tokens") or raw)
    except Exception:  # pragma: no cover - a brief that cannot build measures nothing
        return None, "context brief unavailable"
    return (max(0.0, 1 - bounded / raw),
            f"{bounded} of {raw} {basis_kind} tokens after bounding")


def _gate_effectiveness(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    blocked = sum(1 for r in records
                  if r["kind"] == "attestation" and r["data"].get("status") == "blocked")
    total = sum(1 for r in records if r["kind"] == "attestation")
    return _ratio(blocked, total), f"{blocked} of {total} attested steps were blocked"


def _evidence_density(records: list[dict[str, Any]]) -> tuple[float | None, str]:
    claims = [r for r in records if r["kind"] == "claim"]
    cited = sum(len(r.get("evidence") or []) for r in claims)
    return _ratio(cited, len(claims)), f"{cited} citations across {len(claims)} claims"


def _attestation_coverage(project: Path, records: list[dict[str, Any]]) -> tuple[float | None, str]:
    try:
        from .godmode_charter import compile_charter

        hard = [r for r in compile_charter(project)["compiled"] if r["enforcement"] == "HARD"]
    except Exception:  # pragma: no cover - no charter is no denominator
        return None, "charter unavailable"
    if not hard:
        return None, "no HARD rules compiled"
    attested: set[str] = set()
    for record in records:
        if record["kind"] == "attestation":
            attested.update(record["data"].get("rule_ids") or [])
    covered = sum(1 for rule in hard if rule["id"] in attested)
    return _ratio(covered, len(hard)), f"{covered} of {len(hard)} HARD rules attested"


def _duplicates_and_regressions(
    archive: Chronicle, project: Path, records: list[dict[str, Any]]
) -> tuple[tuple[float | None, str], tuple[float | None, str]]:
    duplicates: tuple[float | None, str] = (None, "atlas unavailable")
    try:
        from .godmode_atlas import build as build_atlas

        atlas = build_atlas(project)
        if not atlas.symbols:
            # Zero duplicates in a project with no symbols is arithmetic, not
            # evidence that duplication was prevented.
            duplicates = (None, "no symbols extracted; nothing to duplicate")
        else:
            pairs = atlas.duplicates()
            duplicates = (float(len(pairs)),
                          f"{len(pairs)} near-duplicate pairs across {len(atlas.symbols)} symbols")
    except Exception:  # pragma: no cover - an unbuildable atlas measures nothing
        pass

    regressions: tuple[float | None, str] = (None, "no protected fixes recorded")
    # A reversal can only be counted where a fix was recorded to reverse.
    guarded = [r for r in records if r["kind"] in ("lesson", "invariant")]
    if guarded:
        try:
            from .godmode_loop import analyze

            found = [f for f in analyze(archive)["findings"]
                     if f["detector"] == "prior-fix-reversal"]
            regressions = (float(len(found)),
                           f"{len(found)} reversals across {len(guarded)} protected fixes")
        except Exception:  # pragma: no cover
            regressions = (None, "loop analysis unavailable")
    return duplicates, regressions


def _documentation_parity(archive: Chronicle) -> tuple[float | None, str]:
    try:
        from .godmode_reconcile import record_triggers

        report = record_triggers(archive)
    except Exception:  # pragma: no cover
        return None, "trigger table unavailable"
    satisfied = len(report.get("satisfied") or [])
    missing = len(report.get("missing") or [])
    return _ratio(satisfied, satisfied + missing), f"{satisfied} of {satisfied + missing} triggers satisfied"


def branch_complexity(project: Path, top: int = 10) -> dict[str, Any]:
    """Per-function decision-point count over the project's own Python.

    Decision points + 1, counted natively from the ast: if/elif, loops,
    except handlers, boolean operator branches, conditional expressions,
    comprehension filters, match cases. Advisory only - the report names
    the worst offenders so a refactor distributes complexity into named
    functions; no gate reads the number, and collapsing a function into
    an unreadable one-liner to lower it is gaming the count, not fixing
    the code.
    """
    import ast

    from .godmode_constants import IGNORED_DIRECTORY_NAMES

    def _score(node: ast.AST) -> int:
        count = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.AsyncFor,
                                  ast.ExceptHandler, ast.IfExp)):
                count += 1
            elif isinstance(child, ast.BoolOp):
                count += max(0, len(child.values) - 1)
            elif isinstance(child, ast.comprehension):
                count += len(child.ifs)
            elif isinstance(child, ast.match_case):
                count += 1
        return count

    functions: list[dict[str, Any]] = []
    files_scanned = 0
    for path in sorted(Path(project).rglob("*.py")):
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        files_scanned += 1
        relative = str(path.relative_to(project)).replace("\\", "/")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "function": node.name,
                    "where": f"{relative}:{node.lineno}",
                    "complexity": _score(node),
                })
    functions.sort(key=lambda f: (-f["complexity"], f["where"]))
    return {
        "files_scanned": files_scanned,
        "functions_counted": len(functions),
        "worst": functions[:max(0, top)],
        "basis": "decision points + 1, counted from the ast; advisory only",
    }


def economics(archive: Chronicle, project: Path) -> dict[str, Any]:
    """Verified-result economics, read entirely from existing records.

    The count that matters is not how much ran but how much finished
    verified. Four readings, all advisory: evidence debt (the calibration
    ledger's scored-but-unresolved claims, a liability with an age);
    verified completion rate (verified-tier items over all terminal items -
    shown over shown-plus-said); rule growth (whether the lesson/invariant
    ratchet is still accelerating - a maturing ratchet's rate declines);
    and trip wires - any failure subject recorded three times is named and
    pointed at the investigation workflow, because the third strike is a
    pattern, not a coincidence.
    """
    from .godmode_attest import calibration_summary
    from .godmode_status import evidence_tier, items as status_items

    calibration = calibration_summary(archive)
    debt = {
        "count": calibration["unresolved_scored"],
        "oldest_seq": calibration["oldest_unresolved_seq"],
    }

    current = status_items(archive)
    terminal = [e for e in current.values() if e["state"] in ("verified", "closed")]
    shown = [e for e in terminal if evidence_tier(e) == "verified"]
    rate = round(len(shown) / len(terminal), 6) if terminal else None

    rule_records = [
        r for r in archive.read_events(verify=False)
        if r.get("kind") in ("lesson", "invariant")
    ]
    recent, prior = rule_records[-25:], rule_records[-50:-25]
    growth = (
        "no rules recorded" if not rule_records
        else "accelerating" if len(recent) > len(prior)
        else "steady" if len(recent) == len(prior)
        else "declining"
    )

    # The whole archive, not a recent window: a strike counter over a
    # bounded window is a decaying monitor, and a patient failure mode
    # simply waits the window out. Incident counts never decay.
    strikes: dict[str, list[dict[str, Any]]] = {}
    for record in archive.read_events(verify=False):
        if record.get("kind") == "incident":
            strikes.setdefault(record["subject"], []).append(record)
    trip_wires = []
    for subject, records in sorted(strikes.items()):
        if len(records) < 3:
            continue
        # The class turns "same error three times" into a named failure
        # shape, which names the fix layer. Latest record's word wins.
        classed = [r["data"].get("failure_class") for r in records
                   if r["data"].get("failure_class")]
        label = f" ({classed[-1]})" if classed else ""
        trip_wires.append({
            "code": "third-strike",
            "detail": (
                f"'{subject}'{label} has {len(records)} incident records; a "
                "third strike is a pattern - open a godmode investigation "
                "instead of another fix in place"
            ),
        })

    # The fix-loop wire's doctor face: subjects whose scored claims failed
    # their outcomes twice are named here as well as at claim time, so the
    # loop is visible even to a reader who never tries a third claim.
    claims = archive.select(kind="claim", limit=500)
    by_seq = {r["sequence"]: r for r in claims}
    failed_subjects: dict[str, int] = {}
    for record in claims:
        data = record.get("data") or {}
        if data.get("resolves") is None or data.get("outcome") != "failed":
            continue
        original = by_seq.get(data["resolves"])
        if original is None:
            continue
        subject = str(original.get("subject", ""))[:80]
        failed_subjects[subject] = failed_subjects.get(subject, 0) + 1
    for subject, count in sorted(failed_subjects.items()):
        if count >= 2:
            trip_wires.append({
                "code": "fix-loop",
                "detail": (
                    f"'{subject}' carries {count} reversals (scored claims "
                    "that failed their outcomes); the analysis is the defect "
                    "- open a godmode investigation before a third try"
                ),
            })

    return {
        "evidence_debt": debt,
        "verified_completion_rate": rate,
        "rule_growth": growth,
        "trip_wires": trip_wires,
    }


def utilization(archive: Chronicle, project: Path | None = None) -> dict[str, Any]:
    """Demand-vs-use census: dormancy with demand is the alarm.

    Absolute usage tracking is wrong - a project with no databases should
    never touch `db`. The honest question pairs what the record DEMANDED
    with what FIRED, per capability family: `investigation` (demand:
    fix-loop subjects with two failed resolutions, third-strike subjects;
    fired: incidents opened, differentials recorded), `learning` (demand:
    incidents; fired: lessons at or after them), `verification` (demand:
    downgraded claims; fired: verdict records and attestations). A family
    with demand and nothing fired reads dormant-with-demand; with neither
    it reads idle - which is health, not neglect. Advisory always.
    """
    records = archive.read_events(verify=False)
    claims = [r for r in records if r.get("kind") == "claim"]
    by_seq = {r["sequence"]: r for r in claims}

    reversal_subjects: dict[str, int] = {}
    downgraded = 0
    for record in claims:
        data = record.get("data") or {}
        if data.get("downgraded"):
            downgraded += 1
        if data.get("resolves") is not None and data.get("outcome") == "failed":
            original = by_seq.get(data["resolves"])
            if original is not None:
                subject = str(original.get("subject", ""))[:80]
                reversal_subjects[subject] = reversal_subjects.get(subject, 0) + 1

    incident_subjects: dict[str, int] = {}
    incident_seqs: list[int] = []
    for record in records:
        if record.get("kind") == "incident":
            incident_seqs.append(record["sequence"])
            incident_subjects[record["subject"]] = (
                incident_subjects.get(record["subject"], 0) + 1)

    counts = {kind: sum(1 for r in records if r.get("kind") == kind)
              for kind in ("differential", "lesson", "verdict", "attestation")}
    last_lesson = max((r["sequence"] for r in records
                       if r.get("kind") == "lesson"), default=0)

    def family(demand: int, fired: int) -> dict[str, Any]:
        verdict = ("idle" if not demand and not fired
                   else "dormant-with-demand" if demand and not fired
                   else "satisfied")
        return {"demand": demand, "fired": fired, "verdict": verdict}

    investigation_demand = (
        sum(1 for c in reversal_subjects.values() if c >= 2)
        + sum(1 for c in incident_subjects.values() if c >= 3))
    families = {
        "investigation": family(
            investigation_demand,
            len(incident_seqs) + counts["differential"]),
        "learning": family(
            sum(1 for seq in incident_seqs if seq > last_lesson),
            counts["lesson"]),
        "verification": family(
            downgraded, counts["verdict"] + counts["attestation"]),
    }
    # The db family joins only when a project is given, because its demand
    # is detected from the tree, not the archive: database files present
    # with no database-kind records is machinery sleeping through its own
    # use case (the operator's own audit question, 2026-09-01).
    if project is not None:
        try:
            from .godmode_dbmgr import _candidate_files

            found = len(_candidate_files(Path(project)))
        except Exception:  # noqa: BLE001 - detection failing is not demand
            found = 0
        db_records = sum(1 for r in records if r.get("kind") == "database")
        families["db"] = family(found, db_records)
    return {
        "families": families,
        "basis": "record kinds only; dormancy with demand is the alarm, "
                 "idle is health",
    }


def metrics(archive: Chronicle, project: Path, window: int = 500) -> dict[str, Any]:
    """The twelve product metrics, computed locally from the archive."""
    records = archive.read_events()[-max(1, window):] if archive.initialized() else []

    duplicates, regressions = _duplicates_and_regressions(archive, project, records)
    computed: dict[str, tuple[float | None, str]] = {
        "resume_accuracy": _resume_accuracy(records),
        "duplicate_build_prevention": duplicates,
        "rca_precision": _rca_precision(records),
        "same_root_recurrence": _same_root_recurrence(records),
        "regression_escape": regressions,
        "false_complete_rate": _false_complete_rate(records),
        "action_transparency": _action_transparency(records),
        "documentation_parity": _documentation_parity(archive) if records else (None, "no records"),
        "token_reduction": _token_reduction(archive, records),
        "gate_effectiveness": _gate_effectiveness(records),
        "evidence_density": _evidence_density(records),
        "attestation_coverage": _attestation_coverage(project, records),
    }

    report: dict[str, Any] = {}
    for name in METRIC_ORDER:
        value, basis = computed[name]
        report[name] = _entry(value, name, basis)

    measured = [e for e in report.values() if e["confidence"] == "measured"]
    meeting = [e for e in measured if e["meets_target"] is True]
    failing = [e for e in measured if e["meets_target"] is False]
    return {
        "records_considered": len(records),
        "window": window,
        "metrics": report,
        "economics": economics(archive, project),
        "summary": {
            "measured": len(measured),
            "meeting_target": len(meeting),
            "below_target": len(failing),
            "insufficient_data": len(METRIC_ORDER) - len(measured),
        },
        "transmitted": "nothing; metrics are computed and printed locally",
        "verdict": ("insufficient-data" if not measured
                    else "below-target" if failing else "healthy"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PRODUCT METRICS",
        "",
        f"Computed from {report['records_considered']} local records. "
        f"Verdict: **{report['verdict']}**.",
        "",
        "| metric | value | target | meets | basis |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in METRIC_ORDER:
        entry = report["metrics"][name]
        value = "insufficient data" if entry["value"] is None else entry["value"]
        meets = {True: "yes", False: "no", None: "-"}[entry["meets_target"]]
        lines.append(f"| {name} | {value} | {entry['target']} | {meets} | {entry['basis']} |")
    return "\n".join(lines) + "\n"
