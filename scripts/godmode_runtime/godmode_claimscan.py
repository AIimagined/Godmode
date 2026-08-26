"""Claim-gate enforcement on public surfaces.

The claim gate downgrades an unsupported claim - but only one that went
through `godmode claim`. Prose typed into README never met it. This module
closes that gap with a definition, and a scan the tests run over this
repository's own surfaces.

A **claim** is a sentence on a public surface that carries a measured
number with a unit or percent, or a verb that promises an outcome
(prevents, guarantees, eliminates, ensures, blocks every, catches every).
*Never* and *always* are deliberately not claims: on these surfaces they
state what godmode does not do, which is honesty rather than a promise.

A claim is **covered** when its line names its own reproduction - a
backticked `godmode` or `python` command, a `tests/`, `docs/` or
`scripts/` path, a markdown link - or when a `claim` record in the archive
carries the sentence's text. Description is not gated: the doctrine is
that every number cites the command that reproduces it, and this is the
check that makes that doctrine a gate instead of a sentence.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

PUBLIC_SURFACES: tuple[str, ...] = (
    "README.md", "docs/LISTING.md", "docs/CAPABILITY-COVERAGE.md", "llms.txt", "GODMODE.md",
)

_UNIT = (r"%|ms\b|s\b|x\b|×|tests?\b|commits?\b|files?\b|sessions?\b|lines?\b|rules?\b|"
         r"entries\b|shapes\b|attacks?\b|commands?\b|records?\b|failures?\b|regressions?\b|"
         r"detectors?\b|capabilit(?:y|ies)\b|hosts?\b|tokens?\b|seconds?\b|minutes?\b")
_NUMBER = re.compile(rf"(?<![\w.])\d[\d,]*(?:\.\d+)?(?:-\w+)?\s*(?:{_UNIT})", re.I)
_PROMISE = re.compile(r"\b(?:prevents?|guarantees?|eliminates?|ensures?|blocks every|catches every)\b", re.I)
_REPRODUCTION = re.compile(
    r"`(?:godmode|python)\b[^`]*`|\b(?:tests|docs|scripts)/[\w./-]+|\]\([^)]+\)|\bcommit:[0-9a-f]{7,}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(\[])")
_FENCE = re.compile(r"^\s*```")
# An HTML line is markup, not prose - a badge URL carries `3.11%2B`, which
# is a version in an encoded query string, not a percentage anyone claimed.
_HTML = re.compile(r"^\s*<")


def _sentences(line: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(line.strip()) if s.strip()]


def is_claim(sentence: str) -> bool:
    return bool(_NUMBER.search(sentence) or _PROMISE.search(sentence))


def _normalise(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _recorded_claims(archive: Any) -> set[str]:
    if not archive.initialized():
        return set()
    out: set[str] = set()
    for record in archive.read_events(verify=False):
        if record.get("kind") != "claim":
            continue
        data = record.get("data") or {}
        for text in (data.get("text"), record.get("subject")):
            if isinstance(text, str) and text.strip():
                out.add(_normalise(text))
    return out


def scan_public_surfaces(project: Path | str, archive: Any,
                         surfaces: tuple[str, ...] = PUBLIC_SURFACES) -> dict[str, Any]:
    project = Path(project)
    recorded = _recorded_claims(archive)
    scanned: list[str] = []
    uncovered: list[dict[str, Any]] = []
    claims = 0
    for relative in surfaces:
        path = project / relative
        if not path.is_file():
            continue
        scanned.append(relative)
        in_fence = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence or not line.strip() or _HTML.match(line):
                continue
            line_reproduces = bool(_REPRODUCTION.search(line))
            for sentence in _sentences(line):
                if not is_claim(sentence):
                    continue
                claims += 1
                if line_reproduces or _normalise(sentence) in recorded:
                    continue
                uncovered.append({"file": relative, "line": number, "sentence": sentence[:240]})
    return {
        "scanned": scanned,
        "claims": claims,
        "uncovered": uncovered,
        "definition": "a sentence with a measured number and unit, or a verb that promises "
                      "an outcome; covered when its line names a reproduction or a claim "
                      "record carries its text",
        "verdict": "uncovered" if uncovered else "covered",
    }
