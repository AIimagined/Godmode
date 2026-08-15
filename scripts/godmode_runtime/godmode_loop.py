"""Anti-loop detectors: notice repetition the repeating agent cannot see.

A loop never looks like a loop from inside - each iteration arrives with fresh
optimism and the same normalised content. These detectors read the archive's own
records (actions, changes, attestations, checkpoints), so what was actually done
is compared, not what the current session remembers doing. Blocking findings
stop the next repetition; the finding cites the earlier record so the prior
result is retrieved instead of regenerated.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

REPEAT_THRESHOLD = 3
LOOP_CONFIG_FILENAME = ".godmode-loop.json"

# U-R2: consecutive no-progress rounds before each mandated response.
STALL_REDIRECT_THRESHOLD = 2  # N1: blocking "change direction" finding
STALL_HALT_THRESHOLD = 4  # N2: governance human-escalation halt
# Progress that clears a stall streak - the same records U-V1/U-R3 already
# treat as evidence something happened, not just was attempted.
_PROGRESS_KINDS = frozenset({"change", "attestation", "verdict"})
# A record an operator wrote, not the agent inferring on their behalf
# (godmode_requests.record_request's default `source`). Only this kind of
# record clears a halt: an agent redirecting itself does not count as the
# human escalation the halt asked for.
_OPERATOR_SOURCE_KINDS = frozenset({"request", "decision"})

# Task 10b: what a loop/experiment declaration may claim about how closely
# it is watched. "unattended" is not a third level quietly accepted here -
# nothing in this runtime reads every cycle's output before the next one
# starts, so nothing may declare itself safe to run with nobody watching.
MATURITY_LEVELS = ("report-only", "assisted")

# §15.3: a rollback target must be a state known good, not merely the most
# recent bookmark - the last checkpoint by sequence is often the broken state
# the oscillation is trying to escape.
_STABLE_CHECKPOINT_STATUSES = frozenset({"green", "verified"})


def repeat_threshold(project: Any = None) -> int:
    """Repetitions tolerated before blocking: `.godmode-loop.json`
    {"repeat_threshold": n}, clamped to 2..10, else 3.

    Projects differ in how much repetition is legitimate (a flake-hunting
    harness reruns on purpose), so the threshold is theirs to set - but only
    within bounds, because 1 would flag first attempts and a large value would
    disable the detector while appearing configured.
    """
    if project is not None:
        config = Path(project) / LOOP_CONFIG_FILENAME
        if config.is_file():
            try:
                declared = json.loads(config.read_text(encoding="utf-8")).get("repeat_threshold")
            except (OSError, ValueError, AttributeError):
                declared = None
            if isinstance(declared, int) and not isinstance(declared, bool):
                return max(2, min(10, declared))
    return REPEAT_THRESHOLD


def _signature(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _finding(detector: str, detail: str, blocking: bool, citations: list[int]) -> dict[str, Any]:
    return {"detector": detector, "detail": detail, "blocking": blocking,
            "citations": [f"seq:{s}" for s in citations]}


def _repeated_actions(
    records: list[dict[str, Any]], threshold: int = REPEAT_THRESHOLD
) -> list[dict[str, Any]]:
    counts: dict[str, list[int]] = {}
    for record in records:
        if record["kind"] != "action":
            continue
        data = {k: v for k, v in record["data"].items() if k not in ("at", "recorded_at")}
        key = _signature({"subject": record["subject"], "data": data})
        counts.setdefault(key, []).append(record["sequence"])
    findings = []
    for sequences in counts.values():
        if len(sequences) >= threshold:
            findings.append(_finding(
                "repeated-action",
                f"the same normalised action ran {len(sequences)} times with nothing "
                "changed between runs; what varied was hope, not input",
                True, sequences,
            ))
    return findings


def _repeated_patches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    findings = []
    for record in records:
        if record["kind"] != "change":
            continue
        key = _signature({"subject": record["subject"],
                          "files": record["data"].get("files", [])})
        if key in seen:
            findings.append(_finding(
                "repeated-patch",
                f"'{record['subject']}' was already applied at seq:{seen[key]}; "
                "retrieve that record's outcome instead of reapplying",
                True, [seen[key], record["sequence"]],
            ))
        else:
            seen[key] = record["sequence"]
    return findings


def _oscillation(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_files: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["kind"] != "change":
            continue
        key = _signature(record["data"].get("files", []))
        by_files.setdefault(key, []).append(record)
    findings = []
    # Only checkpoints recorded stable qualify as rollback targets (§15.3): the
    # last checkpoint by sequence may be the very state that keeps failing.
    checkpoints = [
        r["sequence"] for r in records
        if r["kind"] == "checkpoint"
        and str(r["data"].get("status", "")).lower() in _STABLE_CHECKPOINT_STATUSES
    ]
    for changes in by_files.values():
        subjects = [c["subject"] for c in changes]
        for i in range(len(subjects) - 2):
            if subjects[i] == subjects[i + 2] and subjects[i] != subjects[i + 1]:
                before = [s for s in checkpoints if s < changes[i]["sequence"]]
                rollback = (f"roll back to checkpoint seq:{before[-1]}" if before
                            else "no stable checkpoint precedes the oscillation; record one before continuing")
                findings.append(_finding(
                    "oscillation",
                    f"A->B->A over the same files ('{subjects[i]}' <-> '{subjects[i+1]}'); "
                    f"neither state satisfied the check that keeps reverting it. {rollback}",
                    True,
                    [c["sequence"] for c in changes[i:i + 3]],
                ))
                break
    return findings


def _prior_fix_reversal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guarded: dict[str, tuple[int, str]] = {}
    for record in records:
        if record["kind"] in ("lesson", "invariant"):
            for evidence in record.get("evidence", []):
                if evidence.startswith("file:"):
                    guarded[evidence[len("file:"):].split("#")[0]] = (
                        record["sequence"], record["subject"])
    findings = []
    for record in records:
        if record["kind"] != "change":
            continue
        for path in record["data"].get("files", []):
            hit = guarded.get(path)
            if hit and hit[0] < record["sequence"]:
                reverified = any(
                    r["kind"] == "attestation" and r["sequence"] > record["sequence"]
                    and r["data"].get("status") == "ran"
                    and any(e == f"file:{path}" for e in r.get("evidence", []))
                    for r in records
                )
                if not reverified:
                    findings.append(_finding(
                        "prior-fix-reversal",
                        f"{path} carries fix '{hit[1]}' (seq:{hit[0]}) and was changed "
                        "without its guard being re-observed; re-run the guard before this counts",
                        True, [hit[0], record["sequence"]],
                    ))
    return findings


def _silent_success(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for record in records:
        if record["kind"] != "attestation":
            continue
        data = record["data"]
        if (record["subject"].startswith("check:") and data.get("status") == "ran"
                and "(no output)" in str(data.get("result", ""))):
            findings.append(_finding(
                "silent-success",
                f"{record['subject']} exited zero with no output; silence is a no-op "
                "until a re-query shows the effect, not a success",
                False, [record["sequence"]],
            ))
    return findings


def hypothesis_reset_required(
    records: list[dict[str, Any]], threshold: int = REPEAT_THRESHOLD
) -> list[dict[str, Any]]:
    """Three non-green checkpoints under one hypothesis end that hypothesis.

    A wrong hypothesis does not announce itself; it produces plausible next steps
    forever. The only external signal is that the checkpoints stop moving while
    the explanation stays the same - so the record of what stayed constant, not
    the agent's confidence, decides when the explanation is spent. The finding
    blocks further mutation because a fourth attempt under the same hypothesis is
    the same attempt.
    """
    findings: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    run_key: str | None = None

    def flush() -> None:
        if len(run) >= threshold:
            hypothesis = str(run[0]["data"]["hypothesis"])
            statuses = ", ".join(str(r["data"].get("status", "unknown")) for r in run)
            findings.append(_finding(
                "no-progress-cycle",
                f"{len(run)} consecutive checkpoints stayed non-green ({statuses}) "
                f"while the hypothesis stayed constant: '{hypothesis[:120]}'. "
                "The world moved and the explanation did not, so the explanation is "
                "spent: a hypothesis reset is required - discard it, state a new "
                "one, and record it on the next checkpoint before any further mutation",
                True, [r["sequence"] for r in run],
            ))

    for record in records:
        if record["kind"] != "checkpoint":
            continue
        hypothesis = record["data"].get("hypothesis")
        status = str(record["data"].get("status", "")).lower()
        key = None if hypothesis is None else _signature({"hypothesis": hypothesis})
        if key is not None and status != "green" and key == run_key:
            run.append(record)
            continue
        flush()
        if key is not None and status != "green":
            run, run_key = [record], key
        else:
            # A green checkpoint or an absent hypothesis is progress or a fresh
            # start; either way the streak of sameness is broken.
            run, run_key = [], None
    flush()
    return findings


def _current_stall_streak(records: list[dict[str, Any]]) -> tuple[int, int | None]:
    """The stall streak as of the END of `records` - a live status, not a
    log of every threshold ever crossed.

    A round closes at each checkpoint. It is empty when nothing of kind
    change/attestation/verdict was recorded since the previous one (or the
    start of the archive, for the first). An operator-sourced record
    (`request`/`decision` with `data.source == "stated"`) clears the streak
    outright, wherever it appears - it is itself "record what you'll do
    differently," so a checkpoint is not required to make it count.
    """
    streak = 0
    last_seq: int | None = None
    progress_since_last = False
    for record in records:
        kind = record["kind"]
        if kind in _PROGRESS_KINDS:
            progress_since_last = True
        if (kind in _OPERATOR_SOURCE_KINDS
                and record["data"].get("source") == "stated"):
            streak = 0
            progress_since_last = False
            last_seq = record["sequence"]
            continue
        if kind != "checkpoint":
            continue
        streak = 0 if progress_since_last else streak + 1
        progress_since_last = False
        last_seq = record["sequence"]
    return streak, last_seq


def stall_escalation(
    records: list[dict[str, Any]],
    n1: int = STALL_REDIRECT_THRESHOLD,
    n2: int = STALL_HALT_THRESHOLD,
) -> list[dict[str, Any]]:
    """U-R2: graduated response to consecutive empty rounds, not one
    threshold treated as both "notice" and "emergency".

    Below N1: nominal, no finding. From N1 to just under N2: a blocking
    `stall-redirect` finding - change direction, record what differs. At N2
    and beyond: a governance `stall-escalation` halt - human escalation
    required, cleared only by an operator-sourced record (see
    `_current_stall_streak`), never by the agent simply continuing.
    """
    streak, last_seq = _current_stall_streak(records)
    citations = [last_seq] if last_seq is not None else []
    if streak >= n2:
        return [_finding(
            "stall-escalation",
            f"{streak} consecutive rounds produced no change, attestation, or "
            "verdict; human escalation required - this halt clears only on an "
            "operator-sourced record, not on trying again",
            True, citations,
        )]
    if streak >= n1:
        return [_finding(
            "stall-redirect",
            f"{streak} consecutive rounds produced no change, attestation, or "
            "verdict; change direction - record what you'll do differently "
            "before the next round",
            True, citations,
        )]
    return []


def declare_maturity(value: Any) -> str:
    """Validate a loop/experiment declaration's `maturity` field (Task 10b).

    Only `"report-only"` and `"assisted"` are legal. `"unattended"` is
    refused by name, not silently mapped to the nearest legal level: nothing
    here reads a cycle's output before starting the next one, so nothing may
    declare itself safe to run with no human in that loop.
    """
    if value not in MATURITY_LEVELS:
        raise ArchiveError(
            f"maturity '{value}' is not a legal declaration; only "
            f"{' or '.join(MATURITY_LEVELS)} may run. Unattended execution is "
            "refused by policy - no reader checks a cycle's output before the "
            "next one starts, so no declaration may claim nobody needs to"
        )
    return value


def loop_ready(declaration: dict[str, Any]) -> dict[str, Any]:
    """Task 10b's pre-flight audit: structural readiness before cycle one.

    Checks the CONTRACT's shape, not whether its parts are individually
    sound - a declared stop contract's own predicates are `godmode_stop`'s
    tests to own, not this function's. `maturity` is validated by
    `declare_maturity` first and RAISES on an illegal value (a refusal, not
    a finding); everything below is a blocking finding instead, because a
    loop with a legal maturity but a missing budget is not lawless, it is
    merely not ready yet.
    """
    declare_maturity(declaration.get("maturity"))

    findings: list[dict[str, Any]] = []
    if not declaration.get("stop_contract"):
        findings.append({
            "check": "stop-contract", "blocking": True,
            "detail": "no stop contract declared (U-R1); a loop with no "
                      "termination predicate has no way to end on purpose",
        })
    budget = declaration.get("budget_s")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        findings.append({
            "check": "budget", "blocking": True,
            "detail": "no positive budget_s declared; an unbounded loop "
                      "spends without a ceiling to report against",
        })
    verdict_path = declaration.get("verdict_path")
    if not isinstance(verdict_path, str) or not verdict_path.strip():
        findings.append({
            "check": "verdict-path", "blocking": True,
            "detail": "no verdict_path named; a loop that cannot say where "
                      "its verdict lands cannot be checked afterward",
        })
    escalation = declaration.get("escalation") or {}
    n1, n2 = escalation.get("n1"), escalation.get("n2")
    sane = (isinstance(n1, int) and not isinstance(n1, bool)
            and isinstance(n2, int) and not isinstance(n2, bool)
            and 0 < n1 < n2)
    if not sane:
        findings.append({
            "check": "escalation-thresholds", "blocking": True,
            "detail": f"escalation thresholds not sane (n1={n1!r}, n2={n2!r}); "
                      "n1 must be a positive int less than n2",
        })
    blocking = any(finding["blocking"] for finding in findings)
    return {
        "maturity": declaration.get("maturity"),
        "findings": findings,
        "blocking": blocking,
        "verdict": "not-ready" if blocking else "ready",
    }


def experiment_ready(declaration: dict[str, Any]) -> dict[str, Any]:
    """Task 10b's pre-flight audit for the OTHER declaration type the brief
    names alongside loops: `.godmode-experiment.json`. Narrower than
    `loop_ready` on purpose - an experiment has no escalation ladder and no
    separate verdict_path to name, so only what an experiment actually has
    is checked: its stop contract (`max_runs`, already this file's own
    termination bound - `run_experiment` requires it unconditionally before
    this ever runs) and a declared `budget_s`.

    `maturity` is optional here, unlike the loop path, so a declaration
    that never mentions it is not gated at all - the behaviour every
    `.godmode-experiment.json` predating this function relies on
    (`gated: False` below says so explicitly). The instant one DOES declare
    a maturity, `declare_maturity` runs first and RAISES on an illegal
    value ("unattended" included) exactly like the loop path, and the
    findings become a real gate the caller is expected to enforce, not a
    courtesy report - `run_experiment` does exactly that.
    """
    maturity = declaration.get("maturity")
    if maturity is not None:
        declare_maturity(maturity)

    findings: list[dict[str, Any]] = []
    if not declaration.get("max_runs"):
        findings.append({
            "check": "stop-contract", "blocking": True,
            "detail": "no max_runs declared; an experiment with no bound "
                      "has no way to end on purpose",
        })
    budget = declaration.get("budget_s")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        findings.append({
            "check": "budget", "blocking": True,
            "detail": "no positive budget_s declared; an unbounded series "
                      "spends without a ceiling to report against",
        })
    blocking = any(finding["blocking"] for finding in findings)
    return {
        "maturity": maturity,
        "gated": maturity is not None,
        "findings": findings,
        "blocking": blocking,
        "verdict": "not-ready" if blocking else "ready",
    }


def model_blame_allowed(records: list[dict[str, Any]], session: str | None = None) -> dict[str, Any]:
    """Blaming the model requires a non-model control: the same input through a
    path with no model in it. Without one, the blame is a hypothesis.

    A request/response captured at the transport layer (`transport-evidence:`)
    also qualifies: no model sits between the wire and the record, so it is a
    non-model control by construction, not by naming convention.
    """
    controls = [
        r["sequence"] for r in records
        if r["kind"] == "attestation"
        and ("non-model-control" in r["subject"]
             or r["subject"].startswith("transport-evidence:"))
        and (session is None or r["data"].get("session") == session)
    ]
    return {
        "allowed": bool(controls),
        "controls": [f"seq:{s}" for s in controls],
        "reason": ("a non-model control was attested" if controls else
                   "no non-model control attested; attest one as 'non-model-control:<name>' "
                   "or capture the exchange as 'transport-evidence:<name>' first"),
    }


def _render_notice(findings: list[dict[str, Any]]) -> str | None:
    """Four plain sentences for the reader who will not parse the findings JSON.

    A blocking verdict phrased only as data is easy to scroll past - the loop
    continues around it. The notice states, in order: what repeated, what that
    means, the next safe step, and the standing rule. Text is built only from
    the top blocking finding, so it is deterministic for a given archive.
    """
    blocking = [f for f in findings if f["blocking"]]
    if not blocking:
        return None
    top = blocking[0]
    cited = ", ".join(top["citations"]) if top["citations"] else "the archive"
    return "\n".join((
        f"What repeated: {top['detail']}",
        f"What this means: the records at {cited} already hold this attempt and its "
        "outcome, so running it again produces motion, not information.",
        f"Next safe step: read {cited}, take the outcome recorded there, and change "
        "the input or the hypothesis before acting again.",
        "No further mutation until the evidence changes.",
    ))


def analyze(archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events()
    threshold = repeat_threshold(archive.anchor.project_root)
    findings = (
        _repeated_actions(records, threshold)
        + _repeated_patches(records)
        + _oscillation(records)
        + _prior_fix_reversal(records)
        + _silent_success(records)
        + hypothesis_reset_required(records, threshold)
        + stall_escalation(records)
        # Read from history rather than from the records, because every
        # detector above needs a failure somebody chose to write down.
        + repeated_repairs(Path(archive.anchor.project_root))
    )
    blocking = [f for f in findings if f["blocking"]]
    return {
        "records_scanned": len(records),
        "findings": findings,
        "blocking": bool(blocking),
        "notice": _render_notice(findings),
        "verdict": "loop-detected" if blocking else "no-loop",
    }


# A fix that keeps being needed is not a fix.
#
# Every other detector here reads checkpoint records, and recording a failure is
# voluntary - so across this project's whole archive not one checkpoint carries a
# non-green status and `hypothesis_reset_required` can never fire. Inferring the
# failure from the records was tried and abandoned: subjects are outcome
# summaries, not problem statements, and none of them cluster. The signal is not
# in the record.
#
# It is in history. A file repaired by a `fix:` commit across three or more
# releases is a file whose fixes are not holding, and history is written by the
# act of committing rather than by anyone choosing to admit being stuck.
REPAIR_THRESHOLD = 3


def _git(project: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(project), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _is_version_chore(project: Path, sha: str, path: str) -> bool:
    """Whether a commit moved nothing but a version string in this file.

    Without this every file carrying a version scores the maximum, because a
    release touches all of them, and the real signal is buried under chores.
    """
    diff = _git(project, "show", sha, "--unified=0", "--", path)
    # `startswith`, not `line[:1] in "+-"`: an empty string is a member of every
    # string, so blank diff lines passed that test and broke the `all()` below,
    # which read every version bump as a genuine repair.
    body = [
        line for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    return bool(body) and all("version" in line.lower() for line in body)


def repeated_repairs(project: Path, threshold: int = REPAIR_THRESHOLD) -> list[dict[str, Any]]:
    """Source files repaired by `fix:` commits across `threshold` releases."""
    project = Path(project)
    tags = [tag for tag in _git(project, "tag", "--list", "--sort=v:refname").split() if tag]
    if not tags:
        return []

    repaired: dict[str, set[str]] = {}
    previous = ""
    for tag in tags:
        span = f"{previous}..{tag}" if previous else tag
        previous = tag
        for sha in _git(project, "log", span, "--format=%H", "--grep=^fix").split():
            for path in _git(project, "show", sha, "--name-only", "--format=").split():
                if not path.endswith(".py") or path.startswith("tests/") or "/test" in path:
                    continue
                if _is_version_chore(project, sha, path):
                    continue
                repaired.setdefault(path, set()).add(tag)

    findings: list[dict[str, Any]] = []
    for path, releases in sorted(repaired.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(releases) < threshold:
            continue
        ordered = sorted(releases)
        findings.append({
            "detector": "repeated-repair",
            "path": path,
            "releases": len(ordered),
            # Reported, not blocked: a file may be repaired often because it is
            # where the work is. The reader judges; the record only says how
            # many times the same place needed fixing.
            "blocking": False,
            "detail": (
                f"{path} was repaired in {len(ordered)} releases "
                f"({', '.join(ordered)}). Fixes that keep being needed in one "
                "place are evidence the cause is structural, not the next "
                "special case"
            ),
            "citations": [],
        })
    return findings
