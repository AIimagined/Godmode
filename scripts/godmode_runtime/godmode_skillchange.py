"""Project skill changes made while nobody is watching.

A project skill is ordinary work: an agent may edit, forge, retire or
restore one in any session. What changes when no operator is presumed
present is visibility - each such change is recorded, reported once per
session and skill, and listed by `godmode status`, so the diff is read by
someone before the skill is trusted again. A skill the operator wants
locked is declared in `.godmode-boundaries.json`, which refuses every
writer alike (`skill_boundary_refusal`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SUBJECT = "skill-changed-unattended"

_SKILL_ROOTS: tuple[tuple[str, ...], ...] = (("skills",), (".claude", "skills"))


def project_skill_of(project_root: Path, target: Any) -> str | None:
    """The project skill a write target falls inside, or None:
    `skills/<name>/...` and `.claude/skills/<name>/...`."""
    try:
        path = Path(str(target))
        if not path.is_absolute():
            path = project_root / path
        parts = path.resolve().relative_to(project_root.resolve()).parts
    except (OSError, ValueError, RuntimeError):
        return None
    lowered = tuple(part.lower() for part in parts)
    for root in _SKILL_ROOTS:
        depth = len(root)
        if len(parts) > depth + 1 and lowered[:depth] == root:
            return parts[depth]
    return None


def report_line(skill: str, how: str) -> str:
    return f"skills/{skill} changed ({how}) in an unattended session - review the diff"


def record_unattended_change(archive: Any, session: str | None, skill: str,
                             how: str) -> str | None:
    """Record one unattended change; the report line the first time this
    skill changes in this session, else None."""
    key = session or "unsessioned"
    seen = any(
        (record.get("data") or {}).get("session") == key
        and (record.get("data") or {}).get("skill") == skill
        for record in archive.select(kind="action", subject=SUBJECT, limit=500))
    archive.append("action", SUBJECT, {"session": key, "skill": skill, "how": how})
    return None if seen else report_line(skill, how)


def unattended_changes(archive: Any, session: str | None) -> list[dict[str, Any]]:
    """One row per skill changed unattended in `session`, with every way it
    changed, oldest first."""
    key = session or "unsessioned"
    rows: dict[str, dict[str, Any]] = {}
    for record in archive.select(kind="action", subject=SUBJECT, limit=500):
        data = record.get("data") or {}
        if data.get("session") != key:
            continue
        skill = str(data.get("skill") or "")
        row = rows.setdefault(skill, {"skill": skill, "how": [], "sequence": record.get("sequence")})
        how = str(data.get("how") or "")
        if how and how not in row["how"]:
            row["how"].append(how)
    return [dict(row, line=report_line(row["skill"], ", ".join(row["how"])))
            for row in rows.values()]


def skill_boundary_refusal(project_root: Path, skill_dir: Path, action: str, *,
                           operator_verified: bool = False, archive: Any = None,
                           primary: str = "SKILL.md") -> str | None:
    """The refusal for a skill writer whose skill a declared design
    boundary covers, or None. The same `design_verdict` the pre-tool hook
    applies to an Edit/Write is asked of the skill's own files, in every
    session, `primary` (the file this action writes) first. Only the
    operator moves it, the same two ways as the hook's refusal: an approval
    staged with the password for the first locked file (spent here, once),
    or the command run `--as-operator` with the password verified."""
    from .godmode_fence import _PLUGIN_ROOT, design_verdict
    from .godmode_sentinel import CapabilityBroker, design_edit_operation, stage_operation_hint

    if operator_verified:
        return None
    root = Path(project_root)
    candidates = [skill_dir / primary, skill_dir / "SKILL.md", skill_dir / "godmode-evals.json"]
    if skill_dir.is_dir():
        candidates += sorted(path for path in skill_dir.rglob("*") if path.is_file())
    for path in candidates:
        verdict = design_verdict(root, str(path))
        if verdict["allowed"]:
            continue
        operation = design_edit_operation(str(verdict["path"]))
        if archive is not None:
            spent = CapabilityBroker(archive).consume_staged(operation)
            if spent and spent.get("protected"):
                return None
        return (f"Refusing to {action} skill '{skill_dir.name}': {verdict['detail']}. "
                "The operator stages it with the password from `godmode authorize setup`: "
                f"{stage_operation_hint(_PLUGIN_ROOT, operation)}, or runs the skill "
                "command themselves with `--as-operator`")
    return None
