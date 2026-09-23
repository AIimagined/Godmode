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
    "accept",
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

# E62: `acceptance` is prose an operator reads; `accept` is its executable
# form - one or more `cmd:<command>` entries that must actually be run and
# attested before completion (see `unattested_accept_commands`). A list
# field, so it is kept out of the generic string-coercion loop in `start`.
LIST_FIELDS = ("accept",)

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


def start(archive: Chronicle, session: str, title: str, contract: dict[str, Any]) -> dict[str, Any]:
    spec = latest_spec(archive, title) or latest_spec(archive)
    if spec is None:
        raise ArchiveError(
            "A plan without a spec is refused; run `planmode specify` first so the "
            "what/why exists before the how"
        )
    filled = {
        field: str(contract.get(field, "")).strip()
        for field in CONTRACT_FIELDS if field not in LIST_FIELDS
    }
    filled["accept"] = _normalize_accept(contract.get("accept"))
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


def _normalize_accept(raw: Any) -> list[str]:
    """Coerce a plan's `accept` field to a list of `cmd:<command>` strings.

    Accepts a single string (one command, the CLI's natural shape for a
    repeated `--accept` flag collapsing to one value) or a list; anything
    else is empty. Every non-empty entry must already read `cmd:...` - E62
    is specifically executable acceptance, not another prose field wearing
    a new name.
    """
    if raw is None:
        entries: list[Any] = []
    elif isinstance(raw, str):
        entries = [raw] if raw.strip() else []
    elif isinstance(raw, (list, tuple)):
        entries = list(raw)
    else:
        entries = []
    accept = [str(entry).strip() for entry in entries if str(entry).strip()]
    for entry in accept:
        if not entry.startswith("cmd:"):
            raise ArchiveError(
                f"plan 'accept' entries must read 'cmd:<command>'; got {entry!r}"
            )
    return accept


def gaps(contract: dict[str, Any]) -> list[str]:
    missing = []
    for field in CONTRACT_FIELDS:
        if field in OPTIONAL_FIELDS:
            continue
        if field in LIST_FIELDS:
            if not contract.get(field):
                missing.append(field)
            continue
        if not str(contract.get(field, "")).strip():
            missing.append(field)
    return missing


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


# NS-13d: plan-first. A change that touches more than one file needs an
# approved plan before the edit that makes it multi-file.
PLAN_FIRST_CATEGORY = "unplanned-multi-file-change"
PLAN_FIRST_TIER = "R2"
# An edit that changes at most this many lines is exempt even inside a
# multi-file change: a tiny fix does not need a plan.
PLAN_FIRST_SMALL_EDIT_LINES = 40
PLAN_FIRST_REMEDY = (
    "record and approve a plan first: godmode planmode specify --title T ... && "
    "godmode planmode start --title T ... && godmode planmode approve "
    '(or declare a spike: godmode branches --record --role throwaway, or '
    '"plan_first": "off" in .godmode-authorization-policy.json)')


def _line_count(text: Any) -> int:
    return len(str(text).splitlines()) if text else 0


def edit_size_lines(tool_input: dict[str, Any] | None) -> int | None:
    """How many lines an edit tool call changes, read from its input: the
    larger side of an old/new replacement, the whole content of a write,
    the +/- lines of a patch, summed over a multi-edit. None when the input
    carries none of these shapes - the size is unknown, never guessed small.
    """
    if not isinstance(tool_input, dict):
        return None
    edits = tool_input.get("edits")
    if isinstance(edits, list) and edits:
        return sum(max(_line_count(e.get("old_string")), _line_count(e.get("new_string")))
                   for e in edits if isinstance(e, dict))
    if "old_string" in tool_input or "new_string" in tool_input:
        return max(_line_count(tool_input.get("old_string")),
                   _line_count(tool_input.get("new_string")))
    for key in ("content", "new_source", "file_text", "CodeContent"):
        if key in tool_input:
            return _line_count(tool_input.get(key))
    for key in ("patch", "input"):
        if isinstance(tool_input.get(key), str):
            return sum(1 for line in tool_input[key].splitlines()
                       if line[:1] in "+-" and not line.startswith(("+++", "---")))
    return None


def _change_since_boundary(archive: Chronicle) -> set[str]:
    """Paths enrolled in the current change: edited since the newest of the
    session start, a checkpoint, or a plan approval, by at least one edit
    the gate did not exempt as small (review H2). A file touched only by
    small exempt edits is not enrolled, so a large edit to it later is
    judged as a new file - the exemption covers the edit, not the file."""
    from collections import Counter

    from .godmode_constants import EDIT_RECORD_SUBJECT, PLAN_FIRST_EXEMPT_SUBJECT
    from .godmode_hookproof import SUBJECT_ANCHOR

    edits: Counter[str] = Counter()
    exempt: Counter[str] = Counter()
    for record in reversed(archive.read_events()):
        kind = record.get("kind")
        data = record.get("data") or {}
        if (kind in ("session", "checkpoint")
                or (kind == "action" and record.get("subject") == SUBJECT_ANCHOR)
                or (kind == "plan" and data.get("state") == APPROVED)):
            break
        if kind != "action":
            continue
        if record.get("subject") == EDIT_RECORD_SUBJECT:
            path = data.get("path")
            if isinstance(path, str) and path:
                edits[path] += 1
        elif record.get("subject") == PLAN_FIRST_EXEMPT_SUBJECT:
            for path in data.get("paths") or []:
                if isinstance(path, str) and path:
                    exempt[path] += 1
    return {path for path, count in edits.items() if count > exempt[path]}


def record_small_edit_exemption(archive: Chronicle, paths: list[str]) -> None:
    """Note that the plan-first gate let an edit to `paths` through only
    because it was small (see `_change_since_boundary`)."""
    import hashlib

    from .godmode_constants import PLAN_FIRST_EXEMPT_SUBJECT

    joined = "|".join(sorted(paths))
    archive.append("action", PLAN_FIRST_EXEMPT_SUBJECT, {
        "paths": sorted(paths),
        "operation": "plan-first-exempt:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12],
    }, evidence=[])


def plan_first_verdict(archive: Chronicle, targets: list[str], *, project_root: Any,
                       tool_input: dict[str, Any] | None = None,
                       policy: dict[str, Any] | None = None,
                       branch: str | None = None) -> dict[str, Any]:
    """Whether an edit to `targets` may proceed without an approved plan.

    Refused only when every one of these holds: the policy has not switched
    the gate off; the branch is not a throwaway; no approved plan is active;
    the change - the files edited since the session start, the last
    checkpoint or the last plan approval, plus these targets - spans more
    than one file; at least one target is new to the change; and the edit
    is larger than `PLAN_FIRST_SMALL_EDIT_LINES`. A single-file change is
    never refused. The hook only reaches this in an initialized project.
    """
    from pathlib import Path

    from .godmode_branchrole import THROWAWAY, branch_role
    from .godmode_paths import contain

    if (policy or {}).get("plan_first") == "off":
        return {"allowed": True, "reason": "plan_first is off in the authorization policy"}
    role = branch_role(archive, branch)
    if role["role"] == THROWAWAY:
        return {"allowed": True, "reason": f"branch {branch} is throwaway ({role['source']})"}
    plan = active_plan(archive)
    if plan is not None and plan["state"] == APPROVED:
        return {"allowed": True, "reason": f"plan {plan['id']} approved", "plan": plan["id"]}
    root = Path(project_root)
    current: set[str] = set()
    for target in targets:
        resolved = contain(target, [root])
        if resolved is not None:
            current.add(resolved.relative_to(root.resolve()).as_posix())
    if not current:
        return {"allowed": True, "reason": "no target inside the project"}
    earlier = _change_since_boundary(archive)
    touched = earlier | current
    if len(touched) <= 1:
        return {"allowed": True, "reason": "single-file change"}
    new_files = sorted(current - earlier)
    if not new_files:
        return {"allowed": True, "reason": "every target is already part of this change"}
    size = edit_size_lines(tool_input)
    if size is not None and size <= PLAN_FIRST_SMALL_EDIT_LINES:
        return {"allowed": True, "exempt_files": new_files,
                "reason": f"small edit ({size} lines) exempt from the plan-first rule"}
    shown = ", ".join(sorted(touched)[:4]) + (" ..." if len(touched) > 4 else "")
    return {
        "allowed": False,
        "category": PLAN_FIRST_CATEGORY,
        "tier": PLAN_FIRST_TIER,
        "files": sorted(touched),
        "detail": (f"unplanned multi-file change: {new_files[0]} would be file "
                   f"{len(touched)} of this change ({shown}) and no approved plan exists"),
        "remedy": PLAN_FIRST_REMEDY,
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


def unattested_accept_commands(archive: Chronicle, session: str) -> list[str]:
    """E62: accept commands from the active plan with no this-session attestation.

    An `accept` entry is a `cmd:<command>` citation. It is "attested" the
    same way any other command citation is: an `attestation` record from
    this session carries the exact string in its evidence - see `run_check`
    in `godmode_attest`, which writes precisely that. Reading it back here
    rather than importing `godmode_attest` keeps this module's only
    dependency on the archive's own record shape, which every other
    citation check in this codebase already relies on.

    An empty list means either no active plan, or a plan whose `accept`
    field is empty - `approve` already refuses the latter via `gaps`, so
    this function's job is narrower: of the accept commands a plan DOES
    carry, which ones this session has not actually run.
    """
    plan = active_plan(archive)
    if plan is None:
        return []
    accept = plan["contract"].get("accept") or []
    if not accept:
        return []
    cited: set[str] = set()
    for record in archive.select(kind="attestation", limit=1000):
        if record["data"].get("session") != session:
            continue
        cited.update(record.get("evidence", []))
    return [command for command in accept if command not in cited]


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
            except ArchiveError:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
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
                "accept": ["cmd:pytest tests/auth/rotate_test.py"],
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

            # E62: an approved plan's accept command has not run this session yet.
            assert unattested_accept_commands(archive, session) == [
                "cmd:pytest tests/auth/rotate_test.py"
            ]
            archive.append(
                "attestation", "check:rotate",
                {"session": session, "status": "ran", "result": "exit 0"},
                evidence=["cmd:pytest tests/auth/rotate_test.py"],
            )
            assert unattested_accept_commands(archive, session) == []

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
