"""Plan mode: a state that gates mutation, not a new subsystem.

Naming an approach is choosing it. "No code written yet" is not a defence, because a
stated approach is what the next session inherits and builds on. So plan mode opens
on the approach, holds mutation closed until the contract is complete and approved,
and binds every later implementation record back to the plan that authorised it.
"""

from __future__ import annotations

from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# The plan contract. Every field must be filled before a plan can be approved; the
# empty ones are named rather than silently accepted.
CONTRACT_FIELDS = (
    "objective",
    "acceptance",
    "scope",
    "out_of_scope",
    "current_state",
    "assumptions",
    "parity",
    "steps",
    "risk",
    "rollback",
    "verification",
    "points",
    "editable",
)

# Fields a contract may leave empty. `scope` and `out_of_scope` are prose an
# operator reads; `editable` is the machine-checkable form of the same claim,
# and an edit outside it is refused rather than reported. It is optional
# because making it mandatory would refuse every plan written before the fence
# existed - and because a fence nobody wrote should fence nothing rather than
# everything. The gap is reported by `fence_verdict`, not inferred.
OPTIONAL_FIELDS = ("editable",)

# The spec is the what/why; the plan is the how. A plan without a spec is a
# solution to an unstated problem, so `start` refuses until one exists.
SPEC_FIELDS = ("objective", "outcome", "acceptance", "non_goals")

OPEN = "open"
APPROVED = "approved"
CLOSED = "closed"


def _plans(archive: Chronicle) -> list[dict[str, Any]]:
    return [
        record
        for record in archive.select(kind="plan", limit=500)
        if "state" in record["data"] and "contract" in record["data"]
    ]


def active_plan(archive: Chronicle, session: str | None = None) -> dict[str, Any] | None:
    """Latest non-closed plan, optionally scoped to one session."""
    # select() is chronological; walk backwards so the newest plan wins.
    for record in reversed(_plans(archive)):
        data = record["data"]
        if session and data.get("session") != session:
            continue
        if data["state"] != CLOSED:
            return {
                "id": f"P-{record['record_hash'][:12]}",
                "title": record["subject"],
                "state": data["state"],
                "session": data.get("session"),
                "contract": data["contract"],
                "spec": data.get("spec_id"),
                "sequence": record["sequence"],
            }
    return None


def specify(archive: Chronicle, session: str, title: str, fields: dict[str, str]) -> dict[str, Any]:
    """Record the what/why before any plan states a how."""
    filled = {field: str(fields.get(field, "")).strip() for field in SPEC_FIELDS}
    missing = [field for field in SPEC_FIELDS if not filled[field]]
    if missing:
        raise ArchiveError("A specification needs every field; missing: " + ", ".join(missing))
    record = archive.append(
        "plan", title, {"state": "spec", "session": session, "spec": filled}, evidence=[]
    )
    return {"id": f"SPEC-{record['record_hash'][:12]}", "sequence": record["sequence"]}


def latest_spec(archive: Chronicle, title: str | None = None) -> dict[str, Any] | None:
    for record in reversed(archive.select(kind="plan", limit=500)):
        if "spec" in record["data"] and (title is None or record["subject"] == title):
            return {
                "id": f"SPEC-{record['record_hash'][:12]}",
                "title": record["subject"],
                "spec": record["data"]["spec"],
                "sequence": record["sequence"],
            }
    return None


def start(archive: Chronicle, session: str, title: str, contract: dict[str, str]) -> dict[str, Any]:
    spec = latest_spec(archive, title) or latest_spec(archive)
    if spec is None:
        raise ArchiveError(
            "A plan without a spec is refused; run `planmode specify` first so the "
            "what/why exists before the how"
        )
    filled = {field: str(contract.get(field, "")).strip() for field in CONTRACT_FIELDS}
    record = archive.append(
        "plan",
        title,
        {"state": OPEN, "session": session, "contract": filled, "spec_id": spec["id"]},
        evidence=[],
    )
    return {
        "id": f"P-{record['record_hash'][:12]}", "state": OPEN, "gaps": gaps(filled),
        "spec": spec["id"],
    }


def gaps(contract: dict[str, str]) -> list[str]:
    return [field for field in CONTRACT_FIELDS
            if field not in OPTIONAL_FIELDS
            and not str(contract.get(field, "")).strip()]


def approve(archive: Chronicle, session: str) -> dict[str, Any]:
    """Approve only a complete contract. Missing fields are named, not waived."""
    # No session filter: a plan is project state, not conversation state, so the
    # approving session need not be the authoring one.
    plan = active_plan(archive)
    if plan is None:
        raise ArchiveError("No open plan; run `plan start` first")
    missing = gaps(plan["contract"])
    if missing:
        return {"approved": False, "id": plan["id"], "missing": missing}
    archive.append(
        "plan",
        plan["title"],
        {"state": APPROVED, "session": session, "contract": plan["contract"],
         "spec_id": plan.get("spec")},
        evidence=[],
    )
    return {"approved": True, "id": plan["id"], "missing": [], "spec": plan.get("spec")}


def mutation_verdict(archive: Chronicle, session: str) -> dict[str, Any]:
    """Plan mode blocks project mutation until the plan is approved.

    Read-only and local-compute work is unaffected; this only gates the tier that
    changes the project. The plan is found across sessions: an approved plan
    survives a handoff, and an unapproved one keeps blocking after one too.
    """
    plan = active_plan(archive)
    if plan is None:
        return {"allowed": True, "reason": "no plan mode active"}
    if plan["state"] == APPROVED:
        return {"allowed": True, "reason": f"plan {plan['id']} approved", "plan": plan["id"]}
    return {
        "allowed": False,
        "reason": f"plan {plan['id']} is {plan['state']}; mutation is closed until it is approved",
        "plan": plan["id"],
        "missing": gaps(plan["contract"]),
    }


def bind_execution(archive: Chronicle, session: str, summary: str, files: list[str]) -> dict[str, Any]:
    """Record work against its plan and report anything outside the declared scope."""
    plan = active_plan(archive)
    if plan is None or plan["state"] != APPROVED:
        raise ArchiveError("Implementation must cite an approved plan; run `plan approve` first")
    scope = plan["contract"]["scope"].lower()
    drift = [path for path in files if path.lower() not in scope]
    archive.append(
        "change",
        summary[:120],
        {"plan": plan["id"], "session": session, "files": sorted(files), "drift": sorted(drift)},
        evidence=[],
    )
    return {"plan": plan["id"], "files": sorted(files), "outside_scope": sorted(drift)}


def _self_check() -> None:
    import os
    import tempfile
    from pathlib import Path
    from unittest import mock

    from .godmode_anchor import resolve_anchor

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            session = "S-test"

            assert mutation_verdict(archive, session)["allowed"], "no plan means no plan-mode gate"

            # A plan without a spec is refused: the how needs a stated what/why.
            try:
                start(archive, session, "stop token replay", {"objective": "stop replay"})
                raise AssertionError("plan started without a spec")
            except ArchiveError:
                pass
            specify(archive, session, "stop token replay", {
                "objective": "stop refresh-token replay",
                "outcome": "a replayed token is rejected at rotation",
                "acceptance": "planted replay fails; fresh token passes",
                "non_goals": "session revocation UX",
            })

            partial = start(archive, session, "stop token replay", {"objective": "stop replay"})
            assert partial["state"] == OPEN
            assert "acceptance" in partial["gaps"]
            assert partial["spec"].startswith("SPEC-")

            # Mutation is closed while the plan is incomplete.
            blocked = mutation_verdict(archive, session)
            assert not blocked["allowed"] and blocked["missing"]

            refused = approve(archive, session)
            assert not refused["approved"] and refused["missing"]

            start(archive, session, "stop token replay", {
                "objective": "stop refresh-token replay",
                "acceptance": "a replayed token is rejected",
                "scope": "src/auth/rotate.py tests/auth/rotate_test.py",
                "out_of_scope": "billing",
                "current_state": "rotation reuses the token",
                "assumptions": "clock skew under 30s",
                "parity": "matches the access-token rotation path",
                "steps": "add nonce; reject repeats; extend tests",
                "risk": "sessions invalidated early",
                "rollback": "restore prior checkpoint",
                "verification": "planted replay fails then passes",
                "points": "3",
            })
            assert approve(archive, session)["approved"]
            assert mutation_verdict(archive, session)["allowed"]

            # The approved plan survives a handoff: a different session executes it.
            successor = "S-next-model"
            carried = mutation_verdict(archive, successor)
            assert carried["allowed"] and carried["plan"], carried
            bound = bind_execution(archive, successor, "reject replayed tokens",
                                   ["src/auth/rotate.py", "src/billing/invoice.py"])
            assert bound["outside_scope"] == ["src/billing/invoice.py"], bound

    print("godmode_plan self-check OK")


if __name__ == "__main__":
    _self_check()
