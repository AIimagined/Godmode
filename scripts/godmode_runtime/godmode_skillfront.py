"""Skill frontmatter rules that the shipped structural lint does not cover.

`validate_skill` proves the frontmatter parses, names match, the description
fits and carries a trigger. This module adds the rules a routing skill needs
to stay routable and stay honest about why it exists: a negative-scope
clause (what the skill is NOT for), a description budget, no reference to a
path that does not exist, and - for a skill this repository actually ships -
a `PURPOSE.md` that states, in plain public language, the problem the skill
solves. It runs as a selftest control so a skill cannot ship without them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .godmode_forge import _FRONTMATTER, ForgeError, validate_skill

NEGATIVE_SCOPE_MARKERS = ("not for", "do not use", "not when", "never for", "does not cover")
_PATH_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.(?:md|py|json|yml|yaml|txt|cmd|sh))`")
# Single-line `description:` field, the same shape `validate_skill` itself
# parses (godmode_forge.py's frontmatter loop is line-by-line key: value); a
# description that wraps past its own line is not read by either parser.
_DESCRIPTION = re.compile(r"^description:\s*(.*)$", re.M)
# A `seq:<n>` token anywhere in PURPOSE.md's prose. A shipped PURPOSE.md is a
# public surface every reader of the skill sees; a `seq:<n>` cite points at a
# private, per-checkout archive record that a fresh clone or CI checkout can
# never open. That citation belongs in the local archive that produced it,
# never in a file that ships, so its presence here is a finding, not merely
# unresolved.
_SEQ_TOKEN = re.compile(r"\bseq:(\d+)\b")
# The public problem statement a shipped PURPOSE.md carries: read between its
# own heading and the next `## ` heading (or end of file), the same way this
# suite's other section readers work.
_GAP_SECTION = re.compile(r"^## Gap evidence\s*$(?P<body>.*?)(?=^## |\Z)", re.M | re.S)
_GAP_MIN_CHARS = 40


def _repo_root(skill_dir: Path) -> Path:
    for parent in (skill_dir, *skill_dir.parents):
        if (parent / "skills").is_dir() and (parent / "scripts").is_dir():
            return parent
    return skill_dir.parent.parent


def _is_shipped_skill(skill_dir: Path, root: Path) -> bool:
    """True when `skill_dir` is a direct child of this repo's own `skills/`.

    A fixture built under a temp directory never satisfies this (its
    synthetic root has no real `skills/`), so only a skill this project
    actually ships is held to the companion-files requirement below.
    """
    return skill_dir.resolve().parent == (root / "skills").resolve()


def _purpose_findings(skill_dir: Path) -> list[str]:
    """NS-12b: a shipped skill's `PURPOSE.md` states, in plain public
    language, the problem the skill solves.

    This used to require a `seq:<n>` citation into the local archive - a
    private, per-checkout record (`resolve_anchor` roots it under that
    checkout's own `.git`, never shipped, never cloned, never shared by a
    real `git clone`). Requiring it inside a shipped file blurred a real
    distinction: the archive record that motivated a skill is a private
    decision trail for this project's own use; `PURPOSE.md` is a public
    surface every reader of the shipped skill sees. So the requirement
    now runs the other way: a `## Gap evidence` section must state the
    problem in plain prose any reader can check for themselves, and must
    carry no `seq:<n>` token - that citation stays in the local archive
    that produced it, never in a file that ships. Both checks need no
    archive at all and are checkable on any clone.
    """
    purpose_path = skill_dir / "PURPOSE.md"
    if not purpose_path.is_file():
        return ["purpose: PURPOSE.md is missing (add a PURPOSE.md with a "
                "'## Gap evidence' section stating, in plain public "
                "language, the problem this skill solves)"]
    text = purpose_path.read_text(encoding="utf-8", errors="replace")
    match = _GAP_SECTION.search(text)
    if not match:
        return ["purpose: PURPOSE.md has no '## Gap evidence' section "
                "(add one stating, in plain public language, the problem "
                "this skill solves)"]
    body = match.group("body")
    if _SEQ_TOKEN.search(body):
        return ["purpose: PURPOSE.md's gap evidence cites a private archive "
                "record (seq:<n>); state the problem in plain public "
                "language instead and keep the archive citation in the "
                "local archive"]
    prose = re.sub(r"[#*`_>-]+", " ", body).strip()
    if len(prose) < _GAP_MIN_CHARS:
        return [f"purpose: PURPOSE.md's gap evidence is too short to state "
                f"a concrete problem ({_GAP_MIN_CHARS} characters of plain "
                "prose minimum)"]
    return []


def lint_frontmatter(skill_dir: Path, budget: int = 1024) -> dict[str, Any]:
    findings: list[str] = []
    advisories: list[str] = []
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    root = _repo_root(skill_dir)
    match = _FRONTMATTER.match(text)
    body = match.group("body") if match else ""
    desc_match = _DESCRIPTION.search(body)
    description = desc_match.group(1).strip() if desc_match else ""

    # `validate_skill` also requires agents/openai.yaml and godmode-evals.json
    # to exist, checked before it even looks at the frontmatter, so it cannot
    # be called at all when either is missing without losing every other
    # check it runs. Call it only when both companions exist; otherwise do
    # the frontmatter-shape checks it would have done ourselves, and - for a
    # skill this repo actually ships - report the missing companions as their
    # own finding instead of silently skipping validate_skill's checks.
    has_companions = (
        (skill_dir / "agents" / "openai.yaml").is_file()
        and (skill_dir / "godmode-evals.json").is_file()
    )
    if has_companions:
        try:
            validate_skill(skill_dir)
        except ForgeError as exc:
            findings.append(f"structure: {exc}")
    else:
        if match is None:
            findings.append("structure: SKILL.md frontmatter is missing")
        elif not description:
            findings.append("structure: Skill description is empty or too long")
        fields: dict[str, str] = {}
        for line in body.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip()] = value.strip()
        if fields.get("name") != skill_dir.name:
            findings.append("structure: Skill name must match its directory")
        if _is_shipped_skill(skill_dir, root):
            findings.append("companions: missing agents/openai.yaml or godmode-evals.json")

    # NS-12b: only a skill this repo actually ships is held to PURPOSE.md - a
    # fixture built under a synthetic root (no real `skills/`) is not what
    # this rule protects.
    if _is_shipped_skill(skill_dir, root):
        findings.extend(_purpose_findings(skill_dir))

    if len(description) > budget:
        findings.append(f"budget: description is {len(description)} chars, budget {budget}")
    if not any(marker in description.lower() for marker in NEGATIVE_SCOPE_MARKERS):
        findings.append("negative-scope: description names no case the skill is not for "
                        f"(expected one of {', '.join(repr(m) for m in NEGATIVE_SCOPE_MARKERS)})")
    for token in _PATH_TOKEN.findall(text):
        if not ((skill_dir / token).exists() or (root / token).exists()):
            findings.append(f"orphan-reference: {token} does not exist beside the skill or in the repository")
    return {"passed": not findings, "findings": findings, "advisories": advisories,
            "description_length": len(description)}


def lint_all(skills_root: Path, budget: int = 1024) -> dict[str, Any]:
    per_skill: dict[str, dict[str, Any]] = {}
    for skill_dir in sorted(p for p in skills_root.iterdir() if (p / "SKILL.md").is_file()):
        per_skill[skill_dir.name] = lint_frontmatter(skill_dir, budget)
    return {"passed": all(r["passed"] for r in per_skill.values()), "per_skill": per_skill}
