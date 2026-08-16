"""Runtime guardrails: controls that act during a run, at every boundary crossed.

Godmode starts no watcher and no daemon, so "live" here means: invoked by the
host at a boundary it already crosses. Where a host offers a pre-tool boundary,
that invocation is the interrupt - the watchdog scan and the ceiling check run
there and answer before the tool does. Where it does not, the same functions
still answer on demand, and `capabilities` says which of the two is true rather
than implying the stronger one.

Spend is measured here, not reported to us: tool calls and elapsed time are
counted at the boundary Godmode is called on. Tokens are the host's number and
stay declared, so the ceiling report names which figures it measured.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_stop import OperatorStop

CEILINGS_FILENAME = ".godmode-ceilings.json"
DEFAULT_CEILINGS = {"tokens": 0, "tool_calls": 0, "seconds": 0}  # 0 = no ceiling
METER_FILENAME = "godmode-meter.json"
# The operator's own escape hatch (U-R1): presence, not content, stops a
# watchdog-boundary run regardless of what the skip-pattern scan finds.
OPERATOR_STOP_FLAG = ".godmode-stop"
# U-R2's freshness watchdog: a loop that claims activity but has not
# touched the archive in this many seconds is not running, it is hung.
DEFAULT_MAX_STATE_AGE_S = 900


def declared_ceilings(project: Path) -> dict[str, int]:
    ceilings = dict(DEFAULT_CEILINGS)
    path = project / CEILINGS_FILENAME
    if path.is_file():
        try:
            declared = json.loads(path.read_text(encoding="utf-8"))
            # `null`, a list, or a number all parse cleanly and are all not a
            # config: a malformed file degrades to the defaults rather than
            # taking the caller down with an AttributeError.
            if isinstance(declared, dict):
                ceilings.update({k: int(v) for k, v in declared.items() if k in ceilings})
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass
    return ceilings


def _meter_path(archive: Chronicle) -> Path:
    return archive.root / METER_FILENAME


def _load_meter(archive: Chronicle) -> dict[str, Any]:
    """Disposable operational state, deliberately outside the hash chain.

    A counter that ticks on every tool call would bury the evidence record in
    bookkeeping, and losing a count costs nothing: the meter restarts, the
    archive stays the record of what happened.
    """
    path = _meter_path(archive)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def read_meter(archive: Chronicle, session: str) -> dict[str, Any]:
    """Measured spend for one session: calls counted, seconds elapsed since first."""
    entry = _load_meter(archive).get(session)
    if not isinstance(entry, dict):
        return {"tool_calls": 0, "seconds": 0, "by_tool": {}, "source": "measured"}
    started = float(entry.get("started_at") or time.time())
    return {
        "tool_calls": int(entry.get("tool_calls", 0)),
        "seconds": int(max(0.0, time.time() - started)),
        "by_tool": dict(entry.get("by_tool") or {}),
        "started_at": started,
        "source": "measured",
    }


def meter_tool_call(archive: Chronicle, session: str, tool: str) -> dict[str, Any]:
    """Count one crossing of the pre-tool boundary. Cheap enough to run always."""
    meter = _load_meter(archive)
    entry = meter.get(session)
    if not isinstance(entry, dict):
        entry = {"tool_calls": 0, "by_tool": {}, "started_at": time.time()}
    entry["tool_calls"] = int(entry.get("tool_calls", 0)) + 1
    by_tool = dict(entry.get("by_tool") or {})
    by_tool[tool] = int(by_tool.get(tool, 0)) + 1
    entry["by_tool"] = by_tool
    entry.setdefault("started_at", time.time())
    meter[session] = entry
    # Bounded: only the most recent sessions are kept, so the meter cannot grow
    # without limit on a long-lived project.
    if len(meter) > 20:
        for stale in sorted(meter, key=lambda key: meter[key].get("started_at", 0))[:-20]:
            meter.pop(stale, None)
    try:
        _meter_path(archive).write_text(
            json.dumps(meter, sort_keys=True), encoding="utf-8")
    except OSError:
        # A meter that cannot be written must not stop the tool call it precedes.
        pass
    return read_meter(archive, session)


# Tool payload -> an operation string the action classifier already
# understands, for the finite, adapter-documented tool names below.
#
# CX-2 deleted the old generic-invocation degradation path: a tool this did
# not recognise used to fall back to `f"{tool} tool invocation"`, a string
# that carried no command or target forward and happened to classify through
# `classify_action`'s own catch-all - correct by accident, and losing the
# only evidence of what the call actually was. Returns `None` for any name
# outside this map; `godmode_hostevent.py`'s adapters (the only remaining
# callers) route a `None` here to their own fail-closed `unrecognized-tool`
# path instead - visible, chronicled, never guessed at.
def tool_operation(tool: str, tool_input: dict[str, Any] | None) -> str | None:
    payload = tool_input or {}
    if tool in ("Bash", "PowerShell"):
        return str(payload.get("command", "")).strip() or f"{tool} with no command"
    if tool in ("Write", "Edit", "NotebookEdit"):
        verb = "write" if tool == "Write" else "edit"
        return f"{verb} file {payload.get('file_path', '(unnamed)')}"
    if tool in ("Read", "Glob", "Grep"):
        return f"read {tool.lower()} {payload.get('file_path') or payload.get('pattern') or ''}".strip()
    return None


def check_ceilings(project: Path, spent: dict[str, int]) -> dict[str, Any]:
    """Compare spend against the declared limits, naming which figures were measured."""
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
    measured = spent.get("source") == "measured"
    return {
        "ceilings": ceilings,
        "spent": {k: int(v) for k, v in spent.items() if isinstance(v, (int, float))},
        "remaining": remaining,
        "exceeded": exceeded,
        # Which numbers Godmode counted itself, and which it was handed. Tokens
        # are the host's figure; treating them as measured would overstate what
        # this ceiling can actually hold.
        "measurement": {
            "tool_calls": "measured" if measured else "declared",
            "seconds": "measured" if measured else "declared",
            "tokens": "declared (host-reported)",
        },
        "verdict": "over-ceiling" if exceeded else "within-ceilings",
        "detail": ("stop the run and report what remained" if exceeded
                   else "spend is within every declared ceiling"),
    }


def _session_start_sequence(archive: Chronicle, session: str) -> int:
    """The sequence of the `session` record this session id was derived from.

    `open_session` builds the id as `f"S-{record_hash[:12]}"` from a
    kind="session" record; reversing that mapping locates the record whose
    hash produced it, so the watchdog can window to records written after
    it instead of scanning every attestation this archive has ever held -
    only this session's records can carry this session's skips, and the
    archive before it opened is history, not behaviour to police now.
    Falls back to 0 (the whole archive) for an id that cannot be matched -
    a foreign or synthetic session id must not silently exclude everything.
    """
    if not session.startswith("S-"):
        return 0
    prefix = session[len("S-"):]
    for record in archive.read_events():
        if record["kind"] == "session" and record["record_hash"].startswith(prefix):
            return int(record["sequence"])
    return 0


def state_freshness(
    archive: Chronicle, active: bool, max_age_s: int = DEFAULT_MAX_STATE_AGE_S
) -> dict[str, Any]:
    """U-R2's freshness watchdog: a loop-active claim needs a fresh archive.

    A loop that claims to be running produces records; one that has not in
    `max_age_s` seconds is not running, it is hung - and hung reads as
    active from the outside, which is exactly the gap this closes by
    routing to the same `human-escalation` verdict a stall streak reaches
    (`godmode_loop.stall_escalation`), so a caller does not need two
    different words for the same "a human needs to look" state.
    """
    if not active:
        return {
            "active": False, "stale": False, "verdict": "not-active",
            "detail": "no loop claims activity; freshness is not evaluated",
        }
    head = archive.head
    if not head.is_file():
        return {
            "active": True, "stale": False, "verdict": "nominal",
            "detail": "no archive activity recorded yet",
        }
    age = time.time() - head.stat().st_mtime
    stale = age > max_age_s
    return {
        "active": True,
        "age_seconds": round(age, 1),
        "max_age_seconds": max_age_s,
        "stale": stale,
        "verdict": "human-escalation" if stale else "nominal",
        "detail": (
            f"loop claims activity but the archive has not been touched in "
            f"{round(age)}s (over {max_age_s}s); treat as hung, not running - "
            "escalate the same as a stall streak"
            if stale else "archive activity is current with the loop's claim"
        ),
    }


def watchdog(
    archive: Chronicle, session: str, skip_threshold: int = 3,
    *, loop_active: bool = False, max_state_age_s: int = DEFAULT_MAX_STATE_AGE_S,
) -> dict[str, Any]:
    """Anomaly scan for the current session, cheap enough for every boundary.

    Three mandatory steps skipped in one run is a pattern, not three incidents;
    the scan turns it into an interrupt at the next boundary instead of a
    post-hoc note. Two more sources of interrupt, both opt-in so a caller
    that never sets them sees the original behaviour unchanged: an
    `OperatorStop` flag (U-R1) - presence alone ends the run regardless of
    what the skip scan found - and, when `loop_active` says a loop believes
    itself running, the U-R2 freshness check above.
    """
    skipped: list[dict[str, str]] = []
    blocked: list[str] = []
    start = _session_start_sequence(archive, session)
    # read_events() over select(): the read is cache-backed within this
    # process (godmode_chronicle's _events_identity cache), so this costs
    # nothing extra when another call already warmed it this invocation,
    # and the session-sequence window bounds the WORK done regardless of
    # how many attestations prior sessions left behind.
    for record in archive.read_events():
        if record["sequence"] <= start or record["kind"] != "attestation":
            continue
        data = record["data"]
        if data.get("session") != session:
            continue
        if data.get("status") == "skipped":
            skipped.append({"step": record["subject"],
                            "reason": str(data.get("reason", ""))[:120]})
        if data.get("status") == "blocked":
            blocked.append(record["subject"])
    operator_reason = OperatorStop(
        Path(archive.anchor.project_root) / OPERATOR_STOP_FLAG
    )([])
    freshness = state_freshness(archive, loop_active, max_state_age_s)
    skip_anomaly = len(skipped) >= skip_threshold
    anomaly = skip_anomaly or operator_reason is not None or freshness["stale"]
    if operator_reason is not None:
        detail = operator_reason
    elif freshness["stale"]:
        detail = freshness["detail"]
    elif skip_anomaly:
        detail = (f"{len(skipped)} mandated steps skipped this session; stop and "
                  "resolve the pattern before the next step")
    else:
        detail = "no skip pattern this session"
    return {
        "session": session,
        "skipped": skipped,
        "blocked_steps": blocked,
        "operator_stop": operator_reason,
        "freshness": freshness,
        "anomaly": anomaly,
        "verdict": "interrupt" if anomaly else "nominal",
        "detail": detail,
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

# Every cycle's `action` record is filed under this subject prefix (locked by
# tests.test_tooling_failures's census check, predating U-R3) - the ledger
# functions below key off it rather than a separate counter, so a cycle
# recorded through `run_experiment` is indistinguishable from the ledger's
# point of view whether U-R3 exists or not.
EXPERIMENT_CYCLE_PREFIX = "experiment:"


def _experiment_cycles(archive: Chronicle) -> list[dict[str, Any]]:
    """Every recorded experiment cycle, oldest first - one per past
    `run_experiment` call, identified the same way the pre-existing
    census test already relies on (kind=action, `experiment:` subject)."""
    return [
        record for record in archive.read_events()
        if record["kind"] == "action" and record["subject"].startswith(EXPERIMENT_CYCLE_PREFIX)
    ]


def _latest_experiment_cycle(archive: Chronicle) -> dict[str, Any] | None:
    cycles = _experiment_cycles(archive)
    return cycles[-1] if cycles else None


def _experiment_verdict_for_cycle(archive: Chronicle, cycle_seq: int) -> dict[str, Any] | None:
    for record in archive.select(kind="verdict", limit=2000):
        if record["data"].get("cycle_seq") == cycle_seq:
            return record
    return None


def _experiment_completion_claimed(archive: Chronicle, verdict_seq: int) -> bool:
    """Whether an explicit completion claim citing this cycle's verdict was
    ever recorded (U-R3's positive completion sentinel, E78) - existence
    only. Termination is a claim, not an inference this function draws: it
    does not judge whether the claim actually RESOLVES as confirmed - that
    is `godmode_attest._citation_resolves`'s job, unmodified and untouched
    here, run whenever anything downstream reads the claim.
    """
    citation = f"verdict:{verdict_seq}"
    return any(
        record["kind"] == "claim" and citation in record.get("evidence", [])
        for record in archive.read_events()
    )


def _resolve_experiment_cycle(archive: Chronicle, cycle_seq: int | None) -> dict[str, Any]:
    if cycle_seq is None:
        cycle = _latest_experiment_cycle(archive)
        if cycle is None:
            raise ArchiveError(
                "no experiment cycle recorded yet; run `experiment run` before "
                "recording a verdict"
            )
        return cycle
    for record in _experiment_cycles(archive):
        if record["sequence"] == cycle_seq:
            return record
    raise ArchiveError(f"seq:{cycle_seq} is not a recorded experiment cycle")


def record_experiment_verdict(
    archive: Chronicle,
    project: Path,
    *,
    metric: str,
    before: float,
    after: float,
    epsilon: float,
    cycle_seq: int | None = None,
    simpler: bool = False,
    acquitted_by: str = "self",
) -> dict[str, Any]:
    """U-R3: epsilon adjudication for one experiment cycle - computed, not
    asserted, from `{metric, before, after, epsilon}`.

    `improvement = after - before`: the caller orients `before`/`after` so
    higher is better for the metric named (a latency or error-rate metric
    is handed in already sign-flipped) - this function does no per-metric
    interpretation of its own. `improvement >= epsilon` keeps the
    change; short of that it discards, UNLESS `before == after` exactly (a
    genuinely flat result, not merely small) AND the caller declares
    `simpler=True` - a change that measures no worse and is plainly simpler
    is worth keeping even without a measured gain, but only that flat case;
    a change that measures WORSE never gets rescued by "simpler" alone.

    One verdict per cycle (repeat calls for an already-verdicted cycle are
    refused), and this is the write half of verdict-before-next-cycle:
    `run_experiment` will not start another cycle until the record this
    function writes exists for the one before it.

    `acquitted_by` defaults to `"self"`: before/after are numbers the SAME
    caller supplied, so grading their own arithmetic is honest
    self-attestation of the *comparison*, exactly `godmode_verdict.
    attest_run_state`'s existing convention for execution facts - `disposition`
    therefore stays unset here, so a claim later citing this record as
    `verdict:<seq>` will NOT resolve "confirmed" through
    `godmode_attest._citation_resolves` (U-R3's own audit hook: termination is
    a claim needing independent confirmation, not an inference this
    self-graded arithmetic gets to make on its own). A caller with genuine
    independent standing may pass `acquitted_by="independent"`, which lets
    `disposition` become confirmed/refuted - and then the SAME archive-seam
    invariants every other verdict kind is held to
    (`godmode_invariants._verdict_invariants`) apply here too, unmodified: a
    cycle that never reached an explicit success (loop exhaustion - see
    `run_state` below) can still never be recorded "confirmed" through this
    path either.

    The commit digest (`run_git rev-parse HEAD`) is captured at adjudication
    time and stored on the record - a cycle is commit-linked by carrying the
    digest of the tree it judged, not by inference from timing.
    """
    cycle = _resolve_experiment_cycle(archive, cycle_seq)
    cycle_seq = cycle["sequence"]
    if _experiment_verdict_for_cycle(archive, cycle_seq) is not None:
        raise ArchiveError(f"seq:{cycle_seq} already has a verdict; one verdict per experiment cycle")
    if acquitted_by not in ("independent", "self"):
        raise ArchiveError(f"Unknown acquitted_by '{acquitted_by}'; expected 'independent' or 'self'")
    eps = float(epsilon)
    if not eps > 0:
        raise ArchiveError("epsilon must be a positive number; a non-positive epsilon adjudicates nothing")

    before_v, after_v = float(before), float(after)
    improvement = after_v - before_v
    if improvement >= eps:
        adjudication = "keep"
    elif before_v == after_v and simpler:
        adjudication = "keep-simpler"
    else:
        adjudication = "discard"

    # Loop exhaustion without an explicit completion claim (U-R3/E78): a
    # cycle that was itself budget-cut, or that ran every attempt without
    # ever hitting its declared `success_exit`, never produced an explicit
    # positive signal - its verdict is truncated, never a completion,
    # regardless of what the epsilon math alone says about the metric.
    cycle_data = cycle["data"]
    exhausted = cycle_data.get("run_state") == "truncated" or not cycle_data.get("succeeded", False)
    run_state = "truncated" if exhausted else "terminated"

    disposition = None
    if acquitted_by == "independent":
        disposition = "confirmed" if adjudication in ("keep", "keep-simpler") else "refuted"

    commit = run_git(project, "rev-parse", "HEAD")

    data = {
        "cycle_seq": cycle_seq,
        "metric": metric,
        "before": before_v,
        "after": after_v,
        "epsilon": eps,
        "improvement": improvement,
        "adjudication": adjudication,
        "simpler": bool(simpler),
        "commit": commit,
        "run_state": run_state,
        "acquitted_by": acquitted_by,
        "disposition": disposition,
    }
    subject = f"experiment-verdict:cycle-{cycle_seq}:{metric}"[:200]
    evidence = [f"seq:{cycle_seq}"]
    if commit:
        evidence.append(f"commit:{commit}")
    # The forbidden disposition/run_state/acquitted_by combinations are
    # enforced INSIDE archive.append() itself
    # (godmode_invariants._verdict_invariants, seeded at godmode_chronicle's
    # own import) - not duplicated here, and binding regardless of whether
    # this function is the caller.
    return archive.append("verdict", subject, data, evidence=evidence)


def run_experiment(
    archive: Chronicle, project: Path, timeout: int = 300, *, budget_s: float | None = None
) -> dict[str, Any]:
    """S27-04/S8-03: the bounded experiment loop as one declarative file.

    `.godmode-experiment.json` declares hypothesis, command, success_exit and
    max_runs. The loop runs until success or the bound - never past it - and
    every run is recorded, so "I tried a few times" becomes a numbered series
    with outcomes.

    `budget_s` (U-R1) is a second, independent bound over the whole series:
    `max_runs` caps *how many* attempts happen, `budget_s` caps *how long*
    they may take together. Optional, and off by default, so a caller that
    never passes it sees exactly the prior behaviour - only wall time cuts
    the series short early, and when it does the recorded action carries
    `run_state: "truncated"` rather than pretending the bound was reached on
    its own terms. Each individual attempt is bounded by whichever ceiling
    is TIGHTER - the per-run `timeout` or what remains of `budget_s` - so a
    single long-running attempt cannot itself blow past a declared budget
    unkilled; only the loop noticing *afterward* that the series ran long
    is not enough (review fix, U-R1).

    Task 10b (review fix): a `maturity` field in the spec is validated by
    `godmode_loop.declare_maturity`, which RAISES on an illegal value
    ("unattended" included) before cycle one - the same refusal the loop
    path gives, named the same way. A spec with no `maturity` at all is not
    gated (every pre-existing `.godmode-experiment.json` keeps working
    unchanged); the instant one declares a maturity, `experiment_ready`'s
    findings (stop contract present via the `max_runs` already required
    above, budget declared) become a real gate - blocking findings refuse
    the run before cycle one, not just report on it afterward.

    Task 11/U-R3: each call is one CYCLE of a commit-linked experiment
    ledger. Before running anything, the previous cycle (if any) must
    already carry a verdict (`record_experiment_verdict`) - verdict-before-
    next-cycle, refused here at the API rather than only detected later
    (`godmode_loop.unadjudicated_experiment_cycles` is the read-time half,
    for a raw append that bypasses this function entirely). An optional
    declared `max_cycles` in the spec bounds the SERIES of cycles (distinct
    from `max_runs`, which bounds attempts WITHIN one cycle): once reached
    with no explicit completion claim on record for the last cycle's
    verdict, the series is exhaustED, not complete - a closing `verdict`
    record is written with `run_state: "truncated"` and the call is refused,
    the positive-completion-sentinel half of E78 (a completion claim, once
    made, is audited by U-V1's own unmodified citation-grading, not this
    function).
    """
    import shlex

    from .godmode_loop import experiment_ready
    from .godmode_stop import AttemptHandle, MaxRecords

    path = project / EXPERIMENT_FILENAME
    if not path.is_file():
        raise ArchiveError(f"No {EXPERIMENT_FILENAME}; declare hypothesis, command, max_runs")
    spec = json.loads(path.read_text(encoding="utf-8"))
    for field in ("hypothesis", "command", "max_runs"):
        if field not in spec:
            raise ArchiveError(f"{EXPERIMENT_FILENAME}: $.{field} is required")
    preflight = experiment_ready(spec)  # raises on an illegal declared maturity
    if preflight["gated"] and preflight["blocking"]:
        reasons = "; ".join(f["detail"] for f in preflight["findings"])
        raise ArchiveError(
            f"{EXPERIMENT_FILENAME} declares a maturity but is not pre-flight "
            f"ready: {reasons}"
        )

    prior_cycle = _latest_experiment_cycle(archive)
    if prior_cycle is not None and _experiment_verdict_for_cycle(archive, prior_cycle["sequence"]) is None:
        raise ArchiveError(
            f"cycle refused: seq:{prior_cycle['sequence']} (the previous experiment "
            "cycle) has no verdict yet - adjudicate it (`experiment verdict`) before "
            "running another cycle; verdict-before-next-cycle"
        )

    max_cycles = spec.get("max_cycles")
    if isinstance(max_cycles, int) and not isinstance(max_cycles, bool) and max_cycles > 0:
        # U-R1's own Stop algebra bounds the SERIES, not a synthetic count:
        # a fresh MaxRecords(max_cycles) fed the REAL delta of every cycle
        # recorded so far (one call, not ticked incrementally - there is no
        # long-lived process across separate `run_experiment` invocations to
        # tick it in) fires exactly at the declared boundary, the same
        # `>= n` semantics `MaxRecords` is already pinned to elsewhere.
        prior_cycles = _experiment_cycles(archive)
        prior_count = len(prior_cycles)
        if MaxRecords(max_cycles)(prior_cycles) is not None:
            prior_verdict = (
                _experiment_verdict_for_cycle(archive, prior_cycle["sequence"])
                if prior_cycle is not None else None
            )
            if prior_verdict is not None and _experiment_completion_claimed(archive, prior_verdict["sequence"]):
                raise ArchiveError(
                    f"experiment series already complete: an explicit completion "
                    f"claim cites verdict seq:{prior_verdict['sequence']}; no further "
                    "cycles run"
                )
            closing = archive.append(
                "verdict",
                f"experiment-series-exhausted:{str(spec['hypothesis'])[:80]}"[:200],
                {
                    # `last_cycle_seq`, not `cycle_seq`: this record closes the
                    # SERIES, not one more adjudication of that cycle - naming
                    # it `cycle_seq` would make `_experiment_verdict_for_cycle`
                    # treat it as a second verdict for a cycle that already has
                    # its own (the real one is why this code path was even
                    # reachable at all; verdict-before-next-cycle above ran first).
                    "last_cycle_seq": prior_cycle["sequence"] if prior_cycle is not None else None,
                    "cycles": prior_count,
                    "max_cycles": max_cycles,
                    "run_state": "truncated",
                    "disposition": None,
                    "acquitted_by": "self",
                    "adjudication": None,
                    "reason": "cycle bound reached with no completion claim on record",
                },
            )
            raise ArchiveError(
                f"experiment series exhausted at {prior_count} cycles (max_cycles="
                f"{max_cycles}) with no completion claim recorded; seq:{closing['sequence']} "
                "records run_state=truncated - loop exhaustion is not completion. "
                "Record a completion claim citing a confirmed verdict, or raise max_cycles"
            )

    success_exit = int(spec.get("success_exit", 0))
    max_runs = max(1, min(int(spec["max_runs"]), 20))  # deliberate ceiling: hard cap 20; raise if a real program needs more
    command = shlex.split(str(spec["command"]))

    runs: list[dict[str, Any]] = []
    succeeded = False
    truncated = False
    series_deadline = time.monotonic() + float(budget_s) if budget_s else None
    for attempt_number in range(1, max_runs + 1):
        remaining = (series_deadline - time.monotonic()) if series_deadline is not None else None
        if remaining is not None and remaining <= 0:
            truncated = True
            break
        attempt_budget = min(timeout, remaining) if remaining is not None else timeout
        handle = AttemptHandle(deadline=time.monotonic() + attempt_budget)
        try:
            result = handle.run(command, cwd=str(project))
            code = result["returncode"]
        except FileNotFoundError:
            code = 127
            result = {"run_state": "terminated"}
        runs.append({"attempt": attempt_number, "exit": code})
        if result["run_state"] == "truncated":
            # Cut off by the series budget, not merely the unrelated per-run
            # `timeout` ceiling: only when the budget was the tighter bound
            # does the SERIES itself count as truncated, not just this attempt.
            if remaining is not None and attempt_budget < timeout:
                truncated = True
            break
        if code == success_exit:
            succeeded = True
            break
    run_state = "truncated" if truncated else "terminated"
    cycle_record = archive.append(
        "action", f"experiment:{str(spec['hypothesis'])[:80]}",
        {"runs": runs, "succeeded": succeeded, "bound": max_runs, "run_state": run_state},
    )
    if truncated:
        verdict = f"budget-exhausted: {len(runs)} of {max_runs} runs completed within budget_s"
    elif succeeded:
        verdict = "hypothesis-supported"
    else:
        verdict = (f"bound-reached: {len(runs)} runs without exit {success_exit}; "
                   "revise the hypothesis rather than raising the bound")
    return {
        "hypothesis": spec["hypothesis"],
        "runs": runs,
        "succeeded": succeeded,
        "bound": max_runs,
        "run_state": run_state,
        "preflight": preflight,
        "verdict": verdict,
        "cycle_seq": cycle_record["sequence"],
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
