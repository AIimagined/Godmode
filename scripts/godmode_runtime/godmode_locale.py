"""Localized guidance that cannot quietly drift from what it translates.

A translation is a copy that stops being maintained the day it lands, so the
scaffold is a contract instead of a convention: a variant under
`locales/<lang>/` must mirror an existing English guidance file, keep its
heading structure (levels and order; the words may translate), and keep every
fenced code block byte-identical - commands are not prose. `check` fails on any
violation, so a stale or invented variant is a build failure, not a surprise.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

LOCALE_DIR = "locales"
_HEADING = re.compile(r"^(#{1,6})\s", flags=re.MULTILINE)
_FENCE = re.compile(r"^```.*?^```", flags=re.MULTILINE | re.DOTALL)


def guidance_sources(project: Path) -> list[str]:
    """The English surfaces a locale may translate."""
    sources = [p for p in ("GODMODE.md", "README.md") if (project / p).is_file()]
    sources += sorted(
        p.relative_to(project).as_posix() for p in project.glob("skills/*/SKILL.md")
    )
    return sources


def _structure(text: str) -> list[int]:
    return [len(match) for match in _HEADING.findall(_FENCE.sub("", text))]


def _fences(text: str) -> list[str]:
    return [block.strip() for block in _FENCE.findall(text)]


def _compare(source_text: str, variant_text: str) -> str | None:
    if _structure(variant_text) != _structure(source_text):
        return "heading structure differs from the English source"
    source_fences = _fences(source_text)
    variant_fences = _fences(variant_text)
    if variant_fences != source_fences:
        return "fenced code blocks differ from the English source; commands are not prose"
    return None


def check_locales(project: Path) -> dict[str, Any]:
    root = project / LOCALE_DIR
    sources = guidance_sources(project)
    locales: dict[str, Any] = {}
    problems: list[str] = []

    for language_dir in sorted(root.iterdir()) if root.is_dir() else []:
        if not language_dir.is_dir():
            continue
        language = language_dir.name
        validated: list[str] = []
        for variant in sorted(language_dir.rglob("*.md")):
            relative = variant.relative_to(language_dir).as_posix()
            if relative not in sources:
                problems.append(
                    f"{LOCALE_DIR}/{language}/{relative}: no English source at {relative}"
                )
                continue
            fault = _compare(
                (project / relative).read_text(encoding="utf-8"),
                variant.read_text(encoding="utf-8"),
            )
            if fault:
                problems.append(f"{LOCALE_DIR}/{language}/{relative}: {fault}")
            else:
                validated.append(relative)
        locales[language] = {
            "validated": validated,
            "missing": sorted(set(sources) - set(validated)),
        }

    return {
        "sources": sources,
        "locales": locales,
        "problems": problems,
        "valid": not problems,
        "verdict": "valid" if not problems else "drifted",
    }
