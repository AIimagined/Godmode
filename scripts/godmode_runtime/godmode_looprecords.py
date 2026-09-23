"""NS-1: loop records - a chained failure signature per retry attempt.

A retry loop never sees itself repeating - each attempt arrives with a
plausible next idea and the same underlying failure. `loop_step` records
one attempt's failure signature (the failing test ids plus the shape of
the diff that produced them) and its remaining budget; `advance` compares
a new attempt's signature against the last two recorded for the same
task and refuses (`loop_halt`) the third identical one. Budgets -
an operator's own stop flag, then steps, tokens, and wall time, in that
order - are checked BEFORE the signature test ever runs, so a run that is
merely out of budget is never misdiagnosed as a stuck hypothesis.

A halt is not permanent: `resume` reopens a task, but only on evidence
written by a different actor than whoever hit the halt - the checker
reading the failure fresh, not the same agent asking again. This mirrors
the single-writer/writer-trust discipline `godmode_chronicle.py` already
enforces elsewhere (Task 5): separateness is an actor comparison, never a
role label taken at its word.

The existing `godmode loop` detector (`godmode_loop.py`, its `.godmode-
loop.json` declared contracts and `declare_loop`/`tick_loop`/`close_loop`)
is untouched - this is a second, narrower mechanism: one task, one
failure signature, one halt rule.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_guardrails import OPERATOR_STOP_FLAG, declared_ceilings, usage_ledger_totals
from .godmode_stop import OperatorStop

# Subject a task's loop_step/loop_halt records share, so every reader can
# find one task's whole history with a single subject filter - the same
# shape `godmode_loop.py`'s own `f"{_PREFIX}{name}"` uses for its
# (unrelated) declared contracts.
_SUBJECT_PREFIX = "loop:"

# The resume marker's subject prefix. An `action` record, not a third
# loop-owned kind: NS-1 names exactly two kinds (`loop_step`, `loop_halt`)
# and a resume is bookkeeping about who reopened a task, not a new fact
# about an attempt. Built with an f-string (never a bare literal), the
# same way `godmode_guardrails.EXPERIMENT_CYCLE_PREFIX` mints its own
# per-name `action` subjects - dynamic per-task subjects are not part of
# the fixed `ACTION_SUBJECTS` vocabulary that census enforces.
_RESUME_SUBJECT_PREFIX = "loop-resume:"

# Budget names, checked in this fixed order - an operator's own stop
# request outranks every declared ceiling, and among ceilings, steps
# exhaust before tokens exhaust before wall time (design NS-1 order:
# interrupted > steps > tokens > wall-time).
BUDGET_NAMES = ("steps", "tokens", "wall_time")
REASON_INTERRUPTED = "operator-interrupted"
REASON_SIGNATURE_REPEATED = "loop-signature-repeated"


def _budget_reason(name: str) -> str:
    return f"{name}-exhausted"


# godmode_invariants.py cannot import this module (it stays dependency-free
# of every archive-owning module by design), so its own `LOOP_HALT_REASONS`
# is a hand-kept copy of what this module can actually produce.
# tests/test_atlas_loop.py pins the two sets equal.
def halt_reasons() -> frozenset[str]:
    return frozenset({_budget_reason(name) for name in BUDGET_NAMES}
                      | {REASON_INTERRUPTED, REASON_SIGNATURE_REPEATED})


def signature(failing_test_ids: list[str], diff_shape: dict[str, Any]) -> str:
    """sha256 over the failing test ids and the shape of the diff that
    produced them - never the diff's own bytes, so two runs that touch the
    same files with the same number of hunks compare equal even when the
    exact line content differs run to run (the "normalised failure
    signature" NS-1 asks for, not raw output).

    Order-independent in the test ids and file list (both sorted before
    hashing) so a reporter that lists them in a different order each run
    does not manufacture a false "changed" signature; sensitive to the
    actual membership of either, and to the hunk count.
    """
    shape = diff_shape or {}
    files = sorted(str(f) for f in (shape.get("files") or []))
    try:
        hunks = int(shape.get("hunks") or 0)
    except (TypeError, ValueError):
        hunks = 0
    payload = {
        "failing_test_ids": sorted(str(t) for t in (failing_test_ids or [])),
        "diff_shape": {"files": files, "hunks": hunks},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def diff_shape_from_git(project: Path) -> dict[str, Any]:
    """`--diff-from-git`: the working tree's own unstaged diff, reduced to
    its shape - the files it touches and how many hunks it has - never its
    content. No wall clock, no randomness: the same working tree always
    yields the same shape.

    Scope: the unstaged working tree only. This reads `git diff`, never
    `git diff --cached`, so staged changes and brand-new untracked files
    are invisible to the shape - a caller who stages before running the
    tests records an empty shape, and two attempts that differ only in
    what was staged share one signature."""
    names = run_git(Path(project), "diff", "--name-only") or ""
    files = sorted(name.strip() for name in names.splitlines() if name.strip())
    unified = run_git(Path(project), "diff", "--unified=0") or ""
    hunks = sum(1 for line in unified.splitlines() if line.startswith("@@ "))
    return {"files": files, "hunks": hunks}


def loop_ceilings(project: Path) -> dict[str, int]:
    """The declared `.godmode-ceilings.json` ceilings, renamed onto this
    module's own budget vocabulary - `tool_calls` is what NS-1 calls
    `steps`, `seconds` is what it calls `wall_time`. One declared-ceilings
    file, read the same way `check_ceilings` already reads it, never a
    second config surface."""
    declared = declared_ceilings(Path(project))
    return {
        "steps": int(declared.get("tool_calls", 0) or 0),
        "tokens": int(declared.get("tokens", 0) or 0),
        "wall_time": int(declared.get("seconds", 0) or 0),
    }


def check_budgets(
    ceilings: dict[str, int], spent: dict[str, int], *, interrupted: str | None = None
) -> dict[str, Any]:
    """Pure budget check, in the fixed priority order: an operator's own
    stop request first (its presence is passed in as `interrupted`, the
    reason string `OperatorStop` returns, or `None`), then steps, tokens,
    wall_time against their declared ceilings - a ceiling of 0 means "no
    ceiling declared" and never exhausts.

    Deliberately pure: no archive read, no clock, no filesystem - a
    caller (test or CLI) supplies `ceilings` and `spent` already measured,
    so this function is exercised with fabricated numbers and asserts
    state, never wall-clock.
    """
    if interrupted:
        return {
            "halted": True, "reason": REASON_INTERRUPTED, "detail": interrupted,
            "remaining": None,
        }
    for name in BUDGET_NAMES:
        try:
            limit = int(ceilings.get(name, 0) or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit <= 0:
            continue
        try:
            used = int(spent.get(name, 0) or 0)
        except (TypeError, ValueError):
            used = 0
        if used > limit:
            return {
                "halted": True, "reason": _budget_reason(name),
                "detail": f"{name} spent {used} exceeds the declared ceiling of {limit}",
                "remaining": None,
            }
    remaining: dict[str, int | None] = {}
    for name in BUDGET_NAMES:
        limit = int(ceilings.get(name, 0) or 0)
        used = int(spent.get(name, 0) or 0)
        remaining[name] = (limit - used) if limit > 0 else None
    return {"halted": False, "reason": None, "detail": None, "remaining": remaining}


def _loop_steps_since_resume(archive: Chronicle, task: str) -> list[dict[str, Any]]:
    """Every `loop_step` record for `task`, in sequence order, since the
    latest successful `resume` (or since the start of the archive when
    none exists yet).

    A halt does not erase history - the archive is append-only - so the
    "last two signatures" window a resumed task compares against must be
    scoped to start again at the resume, the same way `godmode_loop.py`'s
    own `_repeated_actions` resets its run on a mutation record rather
    than deleting anything.
    """
    events = archive.read_events()
    resume_subject = f"{_RESUME_SUBJECT_PREFIX}{task}"
    last_resume_seq = 0
    for record in events:
        if record.get("kind") == "action" and record.get("subject") == resume_subject:
            last_resume_seq = int(record.get("sequence", 0))
    subject = f"{_SUBJECT_PREFIX}{task}"
    return [
        record for record in events
        if record.get("kind") == "loop_step" and record.get("subject") == subject
        and int(record.get("sequence", 0)) > last_resume_seq
    ]


def advance_with_budgets(
    archive: Chronicle, *, task: str, failing_test_ids: list[str],
    diff_shape: dict[str, Any], ceilings: dict[str, int], spent: dict[str, int],
    interrupted: str | None = None,
) -> dict[str, Any]:
    """The testable core of `atlas loop advance`: budgets, ceilings and
    spend are all supplied explicitly (no archive scan for spend, no
    clock), so this is exercised directly with fabricated ceilings.

    Order: budgets are checked before the signature is even computed -
    a run that is out of budget never reaches the signature test, and a
    budget halt's `loop_halt` therefore always carries `signatures: []`
    (nothing was computed yet). Only once budgets clear does the new
    attempt's signature get compared against the task's last two.
    """
    subject = f"{_SUBJECT_PREFIX}{task}"
    budgets = check_budgets(ceilings, spent, interrupted=interrupted)
    if budgets["halted"]:
        record = archive.append("loop_halt", subject, {
            "task": task, "reason": budgets["reason"], "signatures": [],
        })
        return {
            "halted": True, "reason": budgets["reason"], "detail": budgets["detail"],
            "signatures": [], "record": record,
        }
    new_signature = signature(failing_test_ids, diff_shape)
    prior = _loop_steps_since_resume(archive, task)
    if len(prior) >= 2:
        last_two = [
            prior[-2]["data"]["failure_signature_hash"],
            prior[-1]["data"]["failure_signature_hash"],
        ]
        if last_two[0] == last_two[1] == new_signature:
            signatures = [*last_two, new_signature]
            record = archive.append("loop_halt", subject, {
                "task": task, "reason": REASON_SIGNATURE_REPEATED, "signatures": signatures,
            })
            return {
                "halted": True, "reason": REASON_SIGNATURE_REPEATED,
                "detail": (
                    "the same failure signature repeated a third time; retrieve the "
                    "outcome already recorded for it instead of retrying unchanged"
                ),
                "signatures": signatures, "record": record,
            }
    attempt_n = len(prior) + 1
    record = archive.append("loop_step", subject, {
        "task": task, "attempt_n": attempt_n, "failure_signature_hash": new_signature,
        "budget_remaining": budgets["remaining"],
    })
    return {
        "halted": False, "attempt_n": attempt_n, "signature": new_signature, "record": record,
    }


def _wall_time_spent(prior_steps: list[dict[str, Any]], now: datetime | None) -> int:
    if not prior_steps:
        return 0
    started = datetime.fromisoformat(prior_steps[0]["recorded_at"])
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - started).total_seconds()))


def advance(
    archive: Chronicle, project: str | Path, *, task: str, failing_test_ids: list[str],
    diff_shape: dict[str, Any] | None = None, diff_from_git: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """`atlas loop advance` wiring: real ceilings (`.godmode-ceilings.json`),
    real spend (steps = attempts already recorded since the last resume,
    tokens = the host's own reported usage, wall_time = elapsed since the
    first attempt in this window), and the operator's own stop flag -
    then delegates to `advance_with_budgets`, the pure core tests exercise
    directly with fabricated numbers.

    One scoping asymmetry the numbers carry: `steps` and `wall_time` are
    scoped to this task since its last resume, while `tokens` is the
    current session's own total, which can include tokens spent on
    unrelated tasks in the same session. That is the session-scoped
    convention `check_ceilings`'s other caller already uses, so the token
    budget reads as a session ceiling consulted per task rather than a
    per-task count.
    """
    project = Path(project)
    if diff_from_git:
        diff_shape = diff_shape_from_git(project)
    elif diff_shape is None:
        diff_shape = {"files": [], "hunks": 0}
    prior = _loop_steps_since_resume(archive, task)
    ceilings = loop_ceilings(project)
    spent = {
        "steps": len(prior),
        "tokens": int(usage_ledger_totals(archive).get("total_tokens", 0) or 0),
        "wall_time": _wall_time_spent(prior, now),
    }
    interrupted = OperatorStop(project / OPERATOR_STOP_FLAG)([])
    return advance_with_budgets(
        archive, task=task, failing_test_ids=failing_test_ids, diff_shape=diff_shape,
        ceilings=ceilings, spent=spent, interrupted=interrupted,
    )


def _record_at_sequence(archive: Chronicle, cite: str) -> dict[str, Any]:
    """Resolve a `seq:<n>` evidence citation to its record, or raise.

    `atlas loop resume` needs the actual record (to read who wrote it),
    not merely whether it exists - `godmode_fingerprint.require_seq_cite`
    answers the existence question alone, so this does the same
    referential check and returns the record itself.
    """
    if not cite.startswith("seq:"):
        raise ArchiveError(
            f"--evidence must be a 'seq:<n>' citation naming the record whose "
            f"writer differs from the halting actor; got {cite!r}"
        )
    rest = cite[len("seq:"):]
    if not (rest.isascii() and rest.isdecimal()):
        raise ArchiveError(f"malformed evidence citation: {cite!r}")
    sequence = int(rest)
    for record in archive.read_events():
        if int(record.get("sequence", 0)) == sequence:
            return record
    raise ArchiveError(f"evidence citation {cite!r} does not exist")


def resume(archive: Chronicle, *, task: str, evidence_cite: str) -> dict[str, Any]:
    """`atlas loop resume`: reopens `task` only when `evidence_cite`'s own
    writer (its `agent_id` fingerprint - Task 5's `writer_fingerprint`)
    differs from whoever wrote the halt being resumed. The same actor
    citing themselves as "new evidence" is exactly the rubber stamp this
    verb exists to refuse - a different actor (the checker, the operator)
    is what actually reopens it.

    Records nothing new about the halt itself; instead it appends an
    `action` bookkeeping record (`loop-resume:<task>`) that
    `_loop_steps_since_resume` reads to reset the signature-comparison
    window for the next `advance` - a resumed task starts its
    third-identical-failure count over, the same way a mutation record
    resets `godmode_loop.py`'s own repeat counter.

    Inert wherever per-agent ids are undeclared: with no
    `GODMODE_AGENT_ID` every process on one project derives the same
    `agent_id`, so the halting actor and the cited evidence's actor
    compare equal and resume refuses `same-actor` no matter who actually
    wrote the evidence. It bites exactly where the single-writer guard
    already bites - once the host declares a distinct id per agent.
    """
    subject = f"{_SUBJECT_PREFIX}{task}"
    halts = [r for r in archive.read_events()
             if r.get("kind") == "loop_halt" and r.get("subject") == subject]
    if not halts:
        return {
            "resumed": False, "reason": "no-halt",
            "detail": f"no loop_halt recorded for task {task!r}; nothing to resume",
        }
    halt = halts[-1]
    halting_agent = str((halt.get("agent") or {}).get("agent_id", ""))
    evidence_record = _record_at_sequence(archive, evidence_cite)
    evidence_agent = str((evidence_record.get("agent") or {}).get("agent_id", ""))
    if evidence_agent == halting_agent:
        return {
            "resumed": False, "reason": "same-actor",
            "detail": (
                "the cited evidence was written by the same actor that halted "
                f"this task ({halting_agent!r}); resume needs evidence from a "
                "different actor"
            ),
        }
    record = archive.append("action", f"{_RESUME_SUBJECT_PREFIX}{task}", {
        "task": task, "halt_seq": halt["sequence"], "evidence": evidence_cite,
        "halting_agent": halting_agent, "evidence_agent": evidence_agent,
    }, evidence=[evidence_cite])
    return {"resumed": True, "record": record}
