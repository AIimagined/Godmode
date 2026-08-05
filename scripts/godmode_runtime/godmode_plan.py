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
    "risk",
    "rollback",
    "verification",
)

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
                "sequence": record["sequence"],
            }
    return None


def start(archive: Chronicle, session: str, title: str, contract: dict[str, str]) -> dict[str, Any]:
    filled = {field: str(contract.get(field, "")).strip() for field in CONTRACT_FIELDS}
    record = archive.append(
        "plan",
        title,
        {"state": OPEN, "session": session, "contract": filled},
        evidence=[],
    )
    return {"id": f"P-{record['record_hash'][:12]}", "state": OPEN, "gaps": gaps(filled)}


def gaps(contract: dict[str, str]) -> list[str]:
    return [field for field in CONTRACT_FIELDS if not str(contract.get(field, "")).strip()]


def approve(archive: Chronicle, session: str) -> dict[str, Any]:
    """Approve only a complete contract. Missing fields are named, not waived."""
    plan = active_plan(archive, session)
    if plan is None:
        raise ArchiveError("No open plan for this session; run `plan start` first")
    missing = gaps(plan["contract"])
    if missing:
        return {"approved": False, "id": plan["id"], "missing": missing}
    archive.append(
        "plan",
        plan["title"],
        {"state": APPROVED, "session": session, "contract": plan["contract"]},
        evidence=[],
    )
    return {"approved": True, "id": plan["id"], "missing": []}


def mutation_verdict(archive: Chronicle, session: str) -> dict[str, Any]:
    """Plan mode blocks project mutation until the plan is approved.

    Read-only and local-compute work is unaffected; this only gates the tier that
    changes the project.
    """
    plan = active_plan(archive, session)
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
    plan = active_plan(archive, session)
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

            partial = start(archive, session, "stop token replay", {"objective": "stop replay"})
            assert partial["state"] == OPEN
            assert "acceptance" in partial["gaps"]

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
                "risk": "sessions invalidated early",
                "rollback": "restore prior checkpoint",
                "verification": "planted replay fails then passes",
            })
            assert approve(archive, session)["approved"]
            assert mutation_verdict(archive, session)["allowed"]

            bound = bind_execution(archive, session, "reject replayed tokens",
                                   ["src/auth/rotate.py", "src/billing/invoice.py"])
            assert bound["outside_scope"] == ["src/billing/invoice.py"], bound

    print("godmode_plan self-check OK")


if __name__ == "__main__":
    _self_check()
