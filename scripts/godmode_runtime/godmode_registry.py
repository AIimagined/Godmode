"""Registry-aware recurrence and design reads (field report file Part 6,
2026-09-10).

Two recurrences that month had a registry row and a green guard, and both
came back because the guard pinned the incident's geometry. `recurrences`
counts repeated failed checks; it had no notion of a fixed-registry row
whose SYMPTOM text matches a new report. This module reads the project's
fixed registry (a markdown table with a symptom column) and scores a new
text against every row, and it reads the project's bound design and
inventory documents for the terms a reply calls "by design". Text only,
language-neutral, no model.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

REGISTRY_CANDIDATES = ("docs/FIXED-REGISTRY.md", "FIXED-REGISTRY.md", "docs/fixed-registry.md",
                       "docs/REGISTRY.md", "docs/FIXED.md")
DESIGN_CANDIDATES = ("docs/INVENTORY.md", "INVENTORY.md", "docs/DESIGN.md", "DESIGN.md", "docs/ARCHITECTURE.md",
                     "ARCHITECTURE.md", "docs/features.md", "docs/FEATURES.md", "docs/DECISIONS.md", "DECISIONS.md")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
_STOP = frozenset("""that this with from have were been when then than them they their there these those what which
while would could should about after before again still into over under only also just very more most some such
does done being those where every never always because through during without within between against user users
video render rendered file files line lines item items case cases thing things show shows shown make makes made
""".split())
_DESIGN_VERDICT = re.compile(
    r"(?i)\b(?:product decision|by design|as designed|designed to|design decision|intended behaviou?r|"
    r"working as intended|out of scope|not a bug|expected behaviou?r)\b")


def tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP}


def registry_path(project: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = Path(project) / path
        return path if path.is_file() else None
    for candidate in REGISTRY_CANDIDATES:
        path = Path(project) / candidate
        if path.is_file():
            return path
    return None


def parse_registry(path: Path) -> list[dict[str, Any]]:
    """Rows of the first markdown table that has a symptom column."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    header: list[str] | None = None
    symptom_at = id_at = guard_at = None
    for number, line in enumerate(lines, 1):
        if not line.lstrip().startswith("|"):
            if rows:
                break
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            lowered = [c.lower() for c in cells]
            if any("symptom" in c for c in lowered):
                header = cells
                symptom_at = next(i for i, c in enumerate(lowered) if "symptom" in c)
                id_at = 0
                guard_at = next((i for i, c in enumerate(lowered) if "guard" in c or "test" in c or "proof" in c), None)
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if symptom_at is None or len(cells) <= symptom_at:
            continue
        rows.append({"line": number, "id": cells[id_at][:80] if id_at is not None else "",
                     "symptom": cells[symptom_at][:400],
                     "guard": cells[guard_at][:200] if guard_at is not None and len(cells) > guard_at else ""})
    return rows


def match_feedback(text: str, rows: list[dict[str, Any]], limit: int = 3,
                   floor: float = 0.12) -> list[dict[str, Any]]:
    """Rows whose symptom shares distinctive words with `text`, scored by
    cosine over word sets; two shared words is the least that counts."""
    query = tokens(text)
    if not query:
        return []
    scored: list[dict[str, Any]] = []
    for row in rows:
        words = tokens(row["symptom"] + " " + row["id"])
        shared = query & words
        if len(shared) < 2 or not words:
            continue
        score = len(shared) / math.sqrt(len(query) * len(words))
        if score >= floor:
            scored.append({**row, "score": round(score, 3), "shared": sorted(shared)[:6]})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def design_documents(project: Path) -> list[Path]:
    """Bound authority documents (roles that describe design or inventory)
    plus the conventional files, existing ones only, no duplicates."""
    out: list[Path] = []
    try:
        from .godmode_corpus import resolve_roles
        for binding in resolve_roles(Path(project)).bindings:
            if binding.role in ("inventory", "decisions", "operating-guide", "state", "sprint-truth", "design"):
                if binding.path not in out:
                    out.append(binding.path)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: no role declaration means the conventional files alone
        pass
    for candidate in DESIGN_CANDIDATES:
        path = Path(project) / candidate
        if path.is_file() and path not in out:
            out.append(path)
    return out


def design_mentions(project: Path, text: str, limit: int = 5) -> list[dict[str, Any]]:
    """Lines in the design and inventory documents that share two or more
    distinctive words with `text`, best first."""
    query = tokens(text)
    if len(query) < 2:
        return []
    hits: list[dict[str, Any]] = []
    for path in design_documents(project):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            shared = query & tokens(line)
            if len(shared) >= 2:
                try:
                    relative = str(path.relative_to(Path(project))).replace("\\", "/")
                except ValueError:
                    relative = str(path)
                hits.append({"path": relative, "line": number, "shared": sorted(shared)[:5],
                             "text": line.strip()[:160], "score": len(shared)})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:limit]


def design_verdict_sentences(reply: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", reply or "") if _DESIGN_VERDICT.search(s)]
