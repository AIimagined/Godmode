"""Skill frontmatter rules that the shipped structural lint does not cover.

`validate_skill` proves the frontmatter parses, names match, the description
fits and carries a trigger. This module adds the rules a routing skill needs
to stay routable and stay honest about why it exists: a negative-scope
clause (what the skill is NOT for), a description budget, no reference to a
path that does not exist, and - for a skill this repository actually ships -
a `PURPOSE.md` naming the archive record(s) that justified it. It runs as a
selftest control so a skill cannot ship without them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .godmode_anchor import resolve_anchor
from .godmode_chronicle import Chronicle
from .godmode_fingerprint import existing_sequences, seq_cite_resolves
from .godmode_forge import _FRONTMATTER, ForgeError, validate_skill

NEGATIVE_SCOPE_MARKERS = ("not for", "do not use", "not when", "never for", "does not cover")
_PATH_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_./-]+\.(?:md|py|json|yml|yaml|txt|cmd|sh))`")
# Single-line `description:` field, the same shape `validate_skill` itself
# parses (godmode_forge.py's frontmatter loop is line-by-line key: value); a
# description that wraps past its own line is not read by either parser.
_DESCRIPTION = re.compile(r"^description:\s*(.*)$", re.M)
# A `seq:<n>` token anywhere in PURPOSE.md's prose - not anchored to a whole
# line or field the way `godmode_attest._SEQ_CITE` is, because PURPOSE.md is
# free-form prose that cites a record mid-sentence.
_SEQ_TOKEN = re.compile(r"\bseq:(\d+)\b")


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


def _purpose_findings(skill_dir: Path, root: Path, archive: Chronicle | None,
                      existing: set[int] | None = None) -> tuple[list[str], list[str]]:
    """NS-12b: a shipped skill's `PURPOSE.md` names the record(s) that justified it.

    Returns `(findings, advisories)`. Two hard requirements need no archive
    at all - present, and citing at least one well-formed `seq:<n>` token -
    so both are checked, reported in `findings`, and fail the lint even when
    `archive` cannot be opened (a non-git fixture, an unreadable state
    home): these are portable and checkable on any clone.

    Whether every cited sequence actually *resolves* is a different
    question - the referential-integrity check `require_seq_cite` runs for
    a `claim --cite seq:` (`godmode_fingerprint.seq_cite_resolves`), applied
    here to a PURPOSE file's own citations. It cannot be a hard requirement:
    the archive that could prove a record exists lives only in the one
    checkout that accumulated it (`resolve_anchor` roots it under that
    checkout's own `.git`, never shipped, never cloned, never shared by a
    real `git clone`). A fresh clone, CI, or another contributor's machine
    opens the *same kind* of archive, empty, and would fail this control for
    every cite it has no way to check - not a defect in the skill. So an
    unresolved cite is reported only in `advisories`, which never flips
    `passed`; it is silently accepted only in the sense that "silent" would
    mean, which this is not - the note is right there in the next run's
    report for whoever has the archive to check it against.
    """
    purpose_path = skill_dir / "PURPOSE.md"
    if not purpose_path.is_file():
        return (["purpose: PURPOSE.md is missing (add a PURPOSE.md citing the seq: "
                  "record(s) that motivated this skill)"], [])
    text = purpose_path.read_text(encoding="utf-8", errors="replace")
    cites = sorted({int(n) for n in _SEQ_TOKEN.findall(text)})
    if not cites:
        return (["purpose: PURPOSE.md cites no seq: record (add a seq: cite naming "
                  "the real record)"], [])
    if archive is None:
        return ([], [])
    if existing is None:
        existing = existing_sequences(archive)
    unresolved = [n for n in cites if not seq_cite_resolves(archive, n, existing=existing)]
    if not unresolved:
        return ([], [])
    named = ", ".join(f"seq:{n}" for n in unresolved)
    return ([], [f"purpose-unresolved: PURPOSE.md cites {named}, which does not resolve in "
                 "this checkout's archive (resolution needs the archive that originated the "
                 "record - a fresh clone or CI checkout has none; this is reported, not a "
                 "lint failure)"])


def _project_archive(root: Path) -> Chronicle | None:
    """The real, local archive `root` resolves to - never a write, only a read.

    `resolve_anchor` can fail on a directory git cannot see cleanly, or one
    this process cannot resolve a state home for; either way that is not a
    lint finding of its own; `_purpose_findings` above degrades to the
    checks that need no archive when this returns `None`.
    """
    try:
        return Chronicle(resolve_anchor(root))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: no archive to check seq: cites against; presence+cite checks still ran
        return None


def lint_frontmatter(skill_dir: Path, budget: int = 1024, archive: Chronicle | None = None,
                     existing: set[int] | None = None) -> dict[str, Any]:
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
    # fixture built under a synthetic root (no real `skills/`) has no
    # archive to cite records from and is not what this rule protects.
    if _is_shipped_skill(skill_dir, root):
        purpose_archive = archive if archive is not None else _project_archive(root)
        purpose_findings, purpose_advisories = _purpose_findings(skill_dir, root, purpose_archive,
                                                                     existing if purpose_archive is archive else None)
        findings.extend(purpose_findings)
        advisories.extend(purpose_advisories)

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
    # One archive open (and one full `existing_sequences` read) shared across
    # every skill in this call, instead of one per skill - `_purpose_findings`
    # only ever reads it, so sharing changes no result, only the cost.
    archive = _project_archive(skills_root.parent)
    existing = existing_sequences(archive) if archive is not None else None
    per_skill: dict[str, dict[str, Any]] = {}
    for skill_dir in sorted(p for p in skills_root.iterdir() if (p / "SKILL.md").is_file()):
        per_skill[skill_dir.name] = lint_frontmatter(skill_dir, budget, archive=archive, existing=existing)
    return {"passed": all(r["passed"] for r in per_skill.values()), "per_skill": per_skill}
