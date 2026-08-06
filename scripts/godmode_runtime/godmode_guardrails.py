"""Runtime guardrails: controls that act during a run, at every boundary crossed.

Godmode starts no watcher and no daemon, so "live" here means: cheap enough to
run at every hook boundary. The watchdog is an anomaly scan a host calls per
turn; ceilings are declared limits the host reports spend against; rewind is a
preview-and-authorize mechanism (Godmode never executes the rollback itself);
the arbiter scores competing open plans instead of taking the first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

CEILINGS_FILENAME = ".godmode-ceilings.json"
DEFAULT_CEILINGS = {"tokens": 0, "tool_calls": 0, "seconds": 0}  # 0 = no ceiling


def declared_ceilings(project: Path) -> dict[str, int]:
    ceilings = dict(DEFAULT_CEILINGS)
    path = project / CEILINGS_FILENAME
    if path.is_file():
        try:
            declared = json.loads(path.read_text(encoding="utf-8"))
            ceilings.update({k: int(v) for k, v in declared.items() if k in ceilings})
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return ceilings


def check_ceilings(project: Path, spent: dict[str, int]) -> dict[str, Any]:
    """The host reports spend; the verdict is computed here, outside the run."""
    ceilings = declared_ceilings(project)
    exceeded = []
    for name, limit in ceilings.items():
        if limit and int(spent.get(name, 0)) > limit:
            exceeded.append({
                "ceiling": name, "limit": limit, "spent": int(spent.get(name, 0)),
            })
    remaining = {
        name: (limit - int(spent.get(name, 0)) if limit else None)
        for name, limit in ceilings.items()
    }
    return {
        "ceilings": ceilings,
        "spent": {k: int(v) for k, v in spent.items()},
        "remaining": remaining,
        "exceeded": exceeded,
        "verdict": "over-ceiling" if exceeded else "within-ceilings",
        "detail": ("stop the run and report what remained" if exceeded
                   else "spend is within every declared ceiling"),
    }


def watchdog(archive: Chronicle, session: str, skip_threshold: int = 3) -> dict[str, Any]:
    """Anomaly scan for the current session, cheap enough for every boundary.

    Three mandatory steps skipped in one run is a pattern, not three incidents;
    the scan turns it into an interrupt at the next boundary instead of a
    post-hoc note.
    """
    skipped: list[dict[str, str]] = []
    blocked: list[str] = []
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") != session:
            continue
        if data.get("status") == "skipped":
            skipped.append({"step": record["subject"],
                            "reason": str(data.get("reason", ""))[:120]})
        if data.get("status") == "blocked":
            blocked.append(record["subject"])
    anomaly = len(skipped) >= skip_threshold
    return {
        "session": session,
        "skipped": skipped,
        "blocked_steps": blocked,
        "anomaly": anomaly,
        "verdict": "interrupt" if anomaly else "nominal",
        "detail": (f"{len(skipped)} mandated steps skipped this session; stop and "
                   "resolve the pattern before the next step" if anomaly
                   else "no skip pattern this session"),
    }


def rewind_preview(archive: Chronicle, to_sequence: int) -> dict[str, Any]:
    """Preview a rollback to a prior verified checkpoint.

    Godmode never executes the operation itself: this names the checkpoint, the
    commit it recorded, and the exact command - execution goes through the
    guard/authorize path like any other protected operation.
    """
    target = None
    for record in archive.select(kind="checkpoint", limit=500):
        if record["sequence"] == to_sequence:
            target = record
            break
    if target is None:
        raise ArchiveError(f"No checkpoint at sequence {to_sequence}; run `history` to list them")
    status = str(target["data"].get("status", "")).lower()
    if status not in ("green", "verified"):
        raise ArchiveError(
            f"Checkpoint seq:{to_sequence} is '{status or 'unstated'}', not a verified state; "
            "rewinding to an unverified point re-creates the problem somewhere older"
        )
    head = target["data"].get("head") or target.get("anchor_fingerprint")
    commit = target["data"].get("head")
    return {
        "checkpoint": {
            "sequence": target["sequence"],
            "summary": target["subject"],
            "status": status,
            "recorded_at": target["recorded_at"],
            "head": head,
        },
        "operation": (f"git stash --include-untracked && git checkout {commit}" if commit
                      else "checkpoint predates head recording; identify the commit from "
                           "`git reflog` around the recorded_at time"),
        "protected": True,
        "next": "authorize and run the operation through `guard`; Godmode previews, the operator executes",
    }


EXPERIMENT_FILENAME = ".godmode-experiment.json"


def run_experiment(archive: Chronicle, project: Path, timeout: int = 300) -> dict[str, Any]:
    """S27-04/S8-03: the bounded experiment loop as one declarative file.

    `.godmode-experiment.json` declares hypothesis, command, success_exit and
    max_runs. The loop runs until success or the bound - never past it - and
    every run is recorded, so "I tried a few times" becomes a numbered series
    with outcomes.
    """
    import shlex
    import subprocess

    path = project / EXPERIMENT_FILENAME
    if not path.is_file():
        raise ArchiveError(f"No {EXPERIMENT_FILENAME}; declare hypothesis, command, max_runs")
    spec = json.loads(path.read_text(encoding="utf-8"))
    for field in ("hypothesis", "command", "max_runs"):
        if field not in spec:
            raise ArchiveError(f"{EXPERIMENT_FILENAME}: $.{field} is required")
    success_exit = int(spec.get("success_exit", 0))
    max_runs = max(1, min(int(spec["max_runs"]), 20))  # [private]: hard cap 20; raise if a real program needs more
    command = shlex.split(str(spec["command"]))

    runs: list[dict[str, Any]] = []
    succeeded = False
    for attempt in range(1, max_runs + 1):
        try:
            done = subprocess.run(command, cwd=str(project), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
            code = done.returncode
        except FileNotFoundError:
            code = 127
        except subprocess.TimeoutExpired:
            code = 124
        runs.append({"attempt": attempt, "exit": code})
        if code == success_exit:
            succeeded = True
            break
    archive.append(
        "action", f"experiment:{str(spec['hypothesis'])[:80]}",
        {"runs": runs, "succeeded": succeeded, "bound": max_runs},
    )
    return {
        "hypothesis": spec["hypothesis"],
        "runs": runs,
        "succeeded": succeeded,
        "bound": max_runs,
        "verdict": ("hypothesis-supported" if succeeded else
                    f"bound-reached: {len(runs)} runs without exit {success_exit}; "
                    "revise the hypothesis rather than raising the bound"),
    }


def arbitrate(archive: Chronicle) -> dict[str, Any]:
    """Score every open plan instead of executing the first one stated.

    Deterministic scoring from the contracts alone: completeness first (a gap
    is unpriced risk), then declared points ascending (the smaller complete
    plan wins), title as the stable tiebreak.
    """
    from .godmode_plan import CONTRACT_FIELDS, _plans, gaps

    open_plans: dict[str, dict[str, Any]] = {}
    for record in _plans(archive):
        data = record["data"]
        if data["state"] == "open":
            open_plans[record["subject"]] = {
                "title": record["subject"],
                "sequence": record["sequence"],
                "contract": data["contract"],
            }
    if len(open_plans) < 2:
        return {"candidates": len(open_plans),
                "verdict": "nothing-to-arbitrate",
                "detail": "arbitration needs at least two open plans"}
    scored = []
    for plan in open_plans.values():
        missing = gaps(plan["contract"])
        try:
            points = int(str(plan["contract"].get("points", "")).strip() or 999)
        except ValueError:
            points = 999
        scored.append({
            "title": plan["title"],
            "sequence": plan["sequence"],
            "complete_fields": len(CONTRACT_FIELDS) - len(missing),
            "missing_fields": missing,
            "points": points,
        })
    scored.sort(key=lambda p: (len(p["missing_fields"]), p["points"], p["title"]))
    return {
        "candidates": len(scored),
        "comparison": scored,
        "winner": scored[0]["title"],
        "reason": "fewest unpriced gaps, then smallest declared points",
        "verdict": "arbitrated",
    }
