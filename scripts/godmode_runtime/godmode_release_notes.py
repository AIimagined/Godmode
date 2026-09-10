"""Release notes as a verb (2026-09-10).

A release note says what the reader gets, grouped by kind, with how to
verify it - never how the release was made. `build` derives the note for
a version from that version's CHANGELOG section (the fragment merge's
output), so the two cannot drift; `check` holds an existing note to the
same shape: present, every changelog entry covered, no empty section, no
process narration, a Verifying section. Own implementation; the shape
follows the fragment-and-category tools the field settled on.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .godmode_changelog import _existing_section, _parse_entries
from .godmode_docslint import _narration_findings

NOTES_DIR = Path("docs") / "releases"
_CATEGORY_ORDER = ("added", "changed", "fixed", "removed", "deprecated", "security")
_TEST_REF = re.compile(r"tests?[./](test_[A-Za-z0-9_]+)(?:\.py)?")
_FIRST_WORDS = re.compile(r"[A-Za-z0-9`_-]+")
_STOP = frozenset({"which", "their", "there", "these", "those", "while", "where", "under", "after", "before",
                   "every", "still", "never", "names", "named", "reads"})


def notes_path(project: Path, version: str) -> Path:
    return Path(project) / NOTES_DIR / f"RELEASE_NOTES_v{version}.md"


def changelog_entries(project: Path, version: str) -> dict[str, list[str]]:
    body = (Path(project) / "CHANGELOG.md").read_text(encoding="utf-8", errors="replace")
    section, _before, _after = _existing_section(body, version)
    return _parse_entries(section)


def _verifying_lines(entries: dict[str, list[str]]) -> list[str]:
    modules: list[str] = []
    for bullets in entries.values():
        for bullet in bullets:
            for match in _TEST_REF.finditer(bullet):
                name = match.group(1)
                if name not in modules:
                    modules.append(name)
    lines = [f"- `python -m unittest tests.{name}`" for name in modules[:6]]
    lines.append("- `python -m unittest discover -s tests` for the whole suite.")
    return lines


def render_notes(version: str, entries: dict[str, list[str]], title: str = "Godmode") -> str:
    out = [f"# {title} v{version}", ""]
    for category in _CATEGORY_ORDER:
        bullets = entries.get(category) or []
        if not bullets:
            continue
        out.append(f"## {category.capitalize()}")
        out.append("")
        out.extend(bullets)
        out.append("")
    out.append("## Verifying")
    out.append("")
    out.extend(_verifying_lines(entries))
    out.append("")
    return "\n".join(out)


def build_notes(project: Path, version: str, force: bool = False) -> dict[str, Any]:
    entries = changelog_entries(project, version)
    if not entries:
        return {"version": version, "written": False,
                "refused": f"CHANGELOG.md has no `## [{version}]` section with entries; run "
                           f"`godmode changelog merge --set-version {version}` first"}
    target = notes_path(project, version)
    if target.exists() and not force:
        return {"version": version, "written": False, "path": str(target.relative_to(project)),
                "refused": "the note already exists; pass --force to regenerate it from the changelog"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_notes(version, entries), encoding="utf-8")
    return {"version": version, "written": True, "path": str(target.relative_to(project)),
            "sections": {k: len(v) for k, v in entries.items()}}


def _bullet_key(bullet: str) -> str:
    first = bullet.splitlines()[0][2:] if bullet.startswith("- ") else bullet
    first = re.sub(r"\*\*", "", first)
    words = [w.casefold() for w in _FIRST_WORDS.findall(first)[:8]]
    return " ".join(w for w in words if len(w) >= 5 and w not in _STOP)


def check_notes(project: Path, version: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    target = notes_path(project, version)
    relative = str(NOTES_DIR / target.name).replace("\\", "/")
    entries = changelog_entries(project, version)
    if not entries:
        findings.append({"check": "changelog-section-missing", "severity": "high",
                         "why": f"CHANGELOG.md has no `## [{version}]` section with entries"})
    if not target.exists():
        findings.append({"check": "note-missing", "severity": "high",
                         "why": f"{relative} does not exist",
                         "remedy": f"godmode release-notes build {version}"})
        return {"version": version, "ok": False, "findings": findings}
    text = target.read_text(encoding="utf-8", errors="replace")
    headings = {m.group(1).strip().casefold(): m.start() for m in re.finditer(r"^## (.+?)\s*$", text, re.M)}
    if "verifying" not in headings:
        findings.append({"check": "missing-section", "severity": "high",
                         "why": "no `Verifying` section: the reader cannot check the note"})
    for title, start in headings.items():
        rest = text[start:]
        body = re.split(r"^## ", rest[3:], maxsplit=1, flags=re.M)[0]
        if not re.sub(r"^[^\n]*\n", "", body, count=1).strip():
            findings.append({"check": "empty-section", "severity": "high", "why": f"`{title}` carries no content"})
    for finding in _narration_findings(relative, text):
        findings.append({"check": finding["check"], "severity": finding["severity"],
                         "line": finding["line"], "why": finding["why"]})
    haystack = text.casefold()
    for category, bullets in entries.items():
        for bullet in bullets:
            key = _bullet_key(bullet)
            words = key.split()
            if words and not any(w in haystack for w in words):
                findings.append({"check": "entry-uncovered", "severity": "medium",
                                 "why": f"changelog entry under {category} has no counterpart in the note: "
                                        f"{bullet.splitlines()[0][:80]}"})
    return {"version": version, "ok": not any(f["severity"] == "high" for f in findings),
            "findings": findings, "entries": sum(len(v) for v in entries.values())}
