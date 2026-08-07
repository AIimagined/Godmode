"""Lifecycle stages and the troubleshooting SOP, gated by the archive's own records.

A stage name announced by a session is a mood; a stage earned from the record is a
fact. Each stage's entry requirement is derived from records the work already had
to produce (an inventory, a decision, an approved plan, a change, a check that
ran), so entering a stage costs no new bookkeeping and cannot be talked into.
Skipping a stage is allowed only as a recorded decision with a reason - the skip
then reads as a choice someone made, not a step nobody noticed was missing.

The troubleshooting SOP works the same way: fifteen steps whose completion is a
set of attestations, not a memory. The step the record shows as next is the next
step, whichever step the current session feels ready for - and a root-cause claim
made before reproduction, staleness, and guard-observation are attested is named
premature, because an RCA without those three is a guess wearing a conclusion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .godmode_attest import record_step
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_plan import APPROVED, active_plan
from .godmode_reconcile import reconcile_docs

STAGES = (
    "discover", "preflight", "parity", "plan", "change",
    "verify", "document", "report", "checkpoint",
)

# A skip is a decision record with this subject shape. It satisfies a stage only
# when it states a reason: a reasonless skip is indistinguishable from the very
# omission this machine exists to catch.
SKIP_SUBJECT = "stage-skip:"


def _plan_approved(archive: Chronicle, project: Path, records: list[dict[str, Any]],
                   session: str | None) -> tuple[bool, str]:
    plan = active_plan(archive)
    if plan is not None and plan["state"] == APPROVED:
        return True, f"plan {plan['id']} is approved"
    if plan is None:
        return False, "no plan exists; run `planmode specify` then `planmode start`"
    return False, f"plan {plan['id']} is {plan['state']}, not approved"


def _stage_checks() -> dict[str, tuple[str, Callable[..., tuple[bool, str]]]]:
    """Requirement per stage, each derived from records the work already produced.

    Built as a function rather than a module-level table so every closure reads
    the same signature; the indirection buys nothing else and claims nothing else.
    """

    def discover(archive, project, records, session):
        return True, "the pipeline starts here; discovery needs no prior record"

    def preflight(archive, project, records, session):
        for record in records:
            if record["kind"] == "inventory":
                return True, f"inventory recorded at seq:{record['sequence']}"
        return False, "no inventory record; capture one so preflight starts from what exists"

    def parity(archive, project, records, session):
        for record in records:
            if record["kind"] == "decision" and record["subject"].startswith("parity"):
                return True, f"parity decision at seq:{record['sequence']}"
        return False, ("no decision with a subject starting 'parity'; compare the sibling "
                       "surface or skip the stage with a stated reason")

    def verify(archive, project, records, session):
        for record in records:
            if record["kind"] == "change":
                return True, f"change recorded at seq:{record['sequence']}"
        return False, "no change record; there is nothing to verify yet"

    def document(archive, project, records, session):
        for record in records:
            if (record["kind"] == "attestation" and record["subject"].startswith("check:")
                    and record["data"].get("status") == "ran"
                    and (session is None or record["data"].get("session") == session)):
                return True, f"{record['subject']} ran at seq:{record['sequence']}"
        return False, "no check attested as ran; a verification that never ran documents nothing"

    def report(archive, project, records, session):
        try:
            reconciled = reconcile_docs(project)
        except ArchiveError as exc:
            # A project without Git cannot be diffed, and pretending either verdict
            # would be a fabrication; the honest state is that an operator must decide.
            return False, f"needs-input: {exc}"
        if reconciled["verdict"] == "reconciled":
            return True, f"documentation reconciled across {reconciled['changed']} changed paths"
        gaps = ", ".join(m["trigger"] for m in reconciled["missing"])
        return False, f"documentation missing for: {gaps}"

    def checkpoint(archive, project, records, session):
        for record in records:
            if (record["kind"] == "claim" and not record["data"].get("downgraded")
                    and (session is None or record["data"].get("session") == session)):
                return True, f"claim at seq:{record['sequence']} held its grade"
        return False, ("every claim was downgraded or none exists; a checkpoint built on "
                       "downgraded claims checkpoints nothing")

    return {
        "discover": ("nothing; discovery is the entry point", discover),
        "preflight": ("an inventory record", preflight),
        "parity": ("a decision with subject starting 'parity'", parity),
        "plan": ("an approved plan", _plan_approved),
        "change": ("an approved plan authorising mutation", _plan_approved),
        "verify": ("at least one change record", verify),
        "document": ("at least one check: attestation with status ran", document),
        "report": ("documentation reconciled against the change", report),
        "checkpoint": ("at least one claim that was not downgraded", checkpoint),
    }


_REQUIREMENTS = _stage_checks()


def _skips(records: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    """Recorded skips with reasons, and the reasonless ones that count for nothing."""
    with_reason: dict[str, str] = {}
    reasonless: set[str] = set()
    for record in records:
        if record["kind"] != "decision" or not record["subject"].startswith(SKIP_SUBJECT):
            continue
        stage = record["subject"][len(SKIP_SUBJECT):]
        reason = str(record["data"].get("reason", "")).strip()
        if reason:
            with_reason[stage] = reason
        else:
            reasonless.add(stage)
    return with_reason, reasonless


def skip_stage(archive: Chronicle, session: str, stage: str, reason: str) -> dict[str, Any]:
    """Record an explicit stage skip. The reason is the record's whole point."""
    if stage not in STAGES:
        raise ArchiveError(f"Unknown stage '{stage}'; expected one of {', '.join(STAGES)}")
    if not reason.strip():
        raise ArchiveError("A stage skip requires a reason; a reasonless skip is an omission")
    record = archive.append(
        "decision", f"{SKIP_SUBJECT}{stage}",
        {"session": session, "reason": reason.strip()}, evidence=[],
    )
    return {"stage": stage, "skipped": True, "sequence": record["sequence"]}


def stage_gate(
    archive: Chronicle, project: Path, target_stage: str, session: str | None = None
) -> dict[str, Any]:
    """Whether the record supports entering `target_stage`.

    Every stage up to and including the target must have its entry requirement in
    the record, or a skip decision with a reason. Checking the whole prefix rather
    than only the target is deliberate: a stage entered over unmet predecessors is
    exactly how work arrives at `report` with nothing behind it.
    """
    if target_stage not in STAGES:
        raise ArchiveError(
            f"Unknown stage '{target_stage}'; expected one of {', '.join(STAGES)}")
    project = Path(project)
    records = archive.read_events()
    skipped, reasonless = _skips(records)

    satisfied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for stage in STAGES[: STAGES.index(target_stage) + 1]:
        requirement, check = _REQUIREMENTS[stage]
        if stage in skipped:
            satisfied.append({"stage": stage, "via": f"skip: {skipped[stage]}"})
            continue
        held, detail = check(archive, project, records, session)
        if held:
            satisfied.append({"stage": stage, "via": detail})
            continue
        if stage in reasonless:
            detail += ("; a stage-skip decision exists but states no reason, "
                       "and a reasonless skip counts for nothing")
        missing.append({"stage": stage, "requirement": requirement, "detail": detail})

    return {
        "stage": target_stage,
        "satisfied": satisfied,
        "missing": missing,
        "allowed": not missing,
    }


def advance(archive: Chronicle, project: Path, stage: str, session: str) -> dict[str, Any]:
    """Attest entry into a stage - only when its gate passes.

    The refusal is an exception rather than a flag because an unrecorded advance
    and a refused one must not read alike to a caller that forgot to check.
    """
    verdict = stage_gate(archive, project, stage, session=session)
    if not verdict["allowed"]:
        unmet = "; ".join(f"{m['stage']}: {m['detail']}" for m in verdict["missing"])
        raise ArchiveError(f"Cannot advance to '{stage}': {unmet}")
    record = record_step(
        archive, session, f"stage:{stage}", "ran",
        result="entered via stage gate: " + ", ".join(
            e["stage"] for e in verdict["satisfied"]),
    )
    return {"stage": stage, "recorded": True, "sequence": record["sequence"],
            "gate": verdict}


# ---------------------------------------------------------------------------
# §15.1 troubleshooting SOP. The steps are data, their completion is attestations,
# and the engine only reads; nothing here trusts a session's account of itself.

SOP_STEPS: tuple[dict[str, str], ...] = (
    {"id": "T0", "evidence_kind": "text",
     "text": "Restate the symptom with the exact error text, verbatim."},
    {"id": "T1", "evidence_kind": "command",
     "text": "Reproduce the failure before changing anything."},
    {"id": "T2", "evidence_kind": "command",
     "binding": "godmode_mistakes.stale_runtime",
     "text": "Check the running process's age against the newest source mtime; "
             "a process older than the code it runs is diagnosed as a ghost."},
    {"id": "T3", "evidence_kind": "output",
     "text": "Capture the failing output verbatim, not a paraphrase of it."},
    {"id": "T4", "evidence_kind": "text",
     "text": "Form exactly one hypothesis and name the variable it turns on."},
    {"id": "T5", "evidence_kind": "record",
     "text": "Query every tracking surface: the status store, open obligations, "
             "and prior incidents."},
    {"id": "T6", "evidence_kind": "command",
     "text": "Run the minimal probe that discriminates the hypothesis."},
    {"id": "T7", "evidence_kind": "record",
     "text": "Record the probe's outcome for or against the hypothesis."},
    {"id": "T8", "evidence_kind": "command",
     "text": "Restart any stale process, then re-reproduce against fresh code."},
    {"id": "T9", "evidence_kind": "text",
     "text": "Widen the search only after the current hypothesis is spent."},
    {"id": "T10", "evidence_kind": "file",
     "text": "Identify the deciding location as file:line, not as a region."},
    {"id": "T11", "evidence_kind": "file",
     "text": "Fix at the root, not at the symptom."},
    {"id": "T12", "evidence_kind": "command",
     "text": "Plant-and-observe the guard: see it fail against the planted "
             "violation, then pass once restored."},
    {"id": "T13", "evidence_kind": "command",
     "text": "Verify fresh and end-to-end, from a state the fix has not warmed."},
    {"id": "T14", "evidence_kind": "record",
     "text": "Record the lesson with its guard, or retire the hypothesis."},
)

_SOP_IDS = tuple(step["id"] for step in SOP_STEPS)

# An RCA rests on these three: the failure was seen (T1), the runtime was current
# (T2), and the guard was observed failing (T12). A root-cause claim recorded
# before all three is reported as premature rather than blocked - the flag makes
# the guess visible without pretending the machine knows the cause better.
RCA_PREREQUISITES = ("T1", "T2", "T12")


def sop_attest(
    archive: Chronicle,
    session: str,
    step: str,
    status: str = "ran",
    result: str = "",
    evidence: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Attest one SOP step, refusing ids the SOP does not contain."""
    if step not in _SOP_IDS:
        raise ArchiveError(
            f"Unknown SOP step '{step}'; expected one of {', '.join(_SOP_IDS)}")
    return record_step(archive, session, f"sop:{step}", status,
                       result=result, evidence=evidence, reason=reason)


def sop_status(archive: Chronicle, session: str) -> dict[str, Any]:
    """What the record shows done, what is missing, and what comes next.

    Ordered by the SOP, not by what was attested: attesting T6 before T1 does not
    move `next` past T1, because the sequence is the method - a probe run before
    reproduction discriminates nothing.
    """
    attested: dict[str, int] = {}
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") != session:
            continue
        subject = record["subject"]
        if subject.startswith("sop:") and data.get("status") in ("ran", "empty"):
            attested[subject[len("sop:"):]] = record["sequence"]

    missing = [step_id for step_id in _SOP_IDS if step_id not in attested]
    next_id = missing[0] if missing else None
    next_step = next((s for s in SOP_STEPS if s["id"] == next_id), None)

    rca_claims = [
        record["subject"]
        for record in archive.select(kind="claim", limit=500)
        if record["data"].get("session") == session
        and "root cause" in str(record["data"].get("text", "")).lower()
    ]
    rca_missing = [step_id for step_id in RCA_PREREQUISITES if step_id not in attested]
    premature = bool(rca_claims) and bool(rca_missing)

    return {
        "session": session,
        "attested": [{"id": step_id, "sequence": attested[step_id]}
                     for step_id in _SOP_IDS if step_id in attested],
        "missing": missing,
        "next": next_id,
        "next_text": next_step["text"] if next_step else None,
        "premature_rca": premature,
        "premature_rca_missing": rca_missing if premature else [],
        "premature_rca_claims": rca_claims if premature else [],
        "verdict": ("sop-complete" if not missing
                    else "premature-rca" if premature else "in-progress"),
    }
