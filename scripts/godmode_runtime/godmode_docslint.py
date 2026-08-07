"""Public prose held to the standard the runtime already holds claims to.

`record_claim` refuses an assertion about project state that cites nothing.
Documentation asserts constantly and cites nothing, and until now nothing
checked it - so a README could carry an unfalsifiable superlative, or a
justification for a decision nobody questioned, and only a reader would notice.

The seed case was exactly that: a licence section arguing Apache over MIT.
Nobody had asked. Internal deliberation on a public surface costs every reader
attention, invites a debate the project does not need, and belongs in a
decision record where it is answered once.

Four classes, each with a remedy rather than a scold:

* rationale-leak - defending a choice against an alternative nobody raised;
* unverifiable-claim - a superlative no reader can check;
* counterfactual-claim - asserting what would have happened otherwise;
* internal-leak / unfinished-marker / local-path - notes, markers, and machine
  paths that were never meant to ship.

Private surfaces are never linted: a decision record is exactly where the
rationale belongs, so flagging it there would invert the point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONFIG_FILENAME = ".godmode-docslint.json"

# Documents a stranger reads. Everything else is working material.
_PUBLIC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})
_PRIVATE_PARTS = frozenset({
    ".godmode-private", ".research", ".planning", ".sprints", ".checkpoints",
    ".handovers", ".evidence", ".decisions", ".lessons", ".git", "node_modules",
    "changelog.d", "tests", "evals",
})

CHECKS: dict[str, dict[str, Any]] = {
    "rationale-leak": {
        "pattern": re.compile(
            r"(?i)\b(?:chosen|picked|selected|opted|went)\s+(?:for\s+)?"
            r"(?:over|instead\s+of|rather\s+than)\b"
            r"|\b(?:we|i)\s+(?:chose|picked|selected|use[d]?|prefer(?:red)?)\b[^.]{0,60}"
            r"\b(?:over|instead\s+of|rather\s+than)\b"
            r"|\bwas\s+chosen\s+(?:over|instead\s+of|rather\s+than)\b"),
        "why": "defends a choice against an alternative the reader did not raise",
        "remedy": "state the choice plainly; move the reasoning to a decision record",
        "severity": "medium",
    },
    "unverifiable-claim": {
        # Anchored on a copula, because the target is a claim about the product
        # ("is the most secure"), not the ordinary English word: a code of
        # conduct saying "what is best for the community" asserts nothing about
        # software, and flagging it would teach the reader to skip the check.
        "pattern": re.compile(
            r"(?i)\b(?:is|are|remains?|stays?|becomes?)\s+(?:by\s+far\s+)?the\s+"
            r"(?:most|best|fastest|safest|strongest|leading|simplest|only)\b"
            r"|\b(?:world[- ]class|industry[- ]leading|state[- ]of[- ]the[- ]art|"
            r"unmatched|unparalleled|bulletproof|rock[- ]solid)\b"),
        "why": "a superlative the reader cannot check, and the runtime would downgrade",
        "remedy": "replace with the measurement, or drop the comparison",
        "severity": "medium",
    },
    "counterfactual-claim": {
        "pattern": re.compile(
            r"(?i)\b(?:prevented|averted|would\s+have\s+(?:caused|broken|failed|cost)|"
            r"saved\s+you|stopped\s+\d+\s+(?:bugs|errors|incidents|defects))\b"),
        # Negation exempts the line: "refusals recorded, not disasters averted"
        # is the disclaimer, not the boast. Flagging the sentence that refuses
        # the claim would teach a writer to delete the honesty and keep the
        # claim - the precise inversion of the point.
        "unless": re.compile(
            r"(?i)\b(?:never|not|rather\s+than|instead\s+of|cannot|can(?:no|')t|"
            r"unmeasurable|unknowable)\b"),
        "why": "asserts what would have happened, which nothing here can measure",
        "remedy": "report what was recorded instead of what it might have prevented",
        "severity": "high",
    },
    "internal-leak": {
        "pattern": re.compile(
            r"(?i)\b(?:as\s+(?:we|i)\s+discussed|per\s+our\s+(?:chat|call|discussion)|"
            r"internal\s+note|for\s+now,?\s+until\s+(?:we|i))\b"),
        "why": "internal deliberation on a public surface",
        "remedy": "delete it, or record it as a decision with its rationale",
        "severity": "medium",
    },
    "unfinished-marker": {
        "pattern": re.compile(r"\b(?:TODO|FIXME|XXX|HACK|WIP|TBD)\b(?!\s*:?\s*\|)"),
        "why": "an unfinished marker shipped to readers",
        "remedy": "finish it, or move it to the tracker",
        "severity": "medium",
    },
    "local-path": {
        "pattern": re.compile(
            r"(?i)(?:[a-z]:\\users\\[^\s\\]+|/(?:home|Users)/[a-z0-9._-]{2,})"),
        "why": "a machine-specific path that will not exist for the reader",
        "remedy": "use a relative path or a placeholder",
        "severity": "high",
    },
}


def _config(project: Path) -> dict[str, Any]:
    path = Path(project) / CONFIG_FILENAME
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _is_public(path: Path, project: Path) -> bool:
    if path.suffix.lower() not in _PUBLIC_SUFFIXES:
        return False
    try:
        relative = path.relative_to(project)
    except ValueError:
        return False
    return not any(part in _PRIVATE_PARTS for part in relative.parts)


def lint_text(path: str, text: str, ignore: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Findings for one document's text. Code blocks are skipped: a fenced
    example may legitimately contain any of these shapes."""
    findings: list[dict[str, Any]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(("    ", "\t")):
            continue
        for name, check in CHECKS.items():
            if name in ignore:
                continue
            exemption = check.get("unless")
            if exemption is not None and exemption.search(line):
                continue
            match = check["pattern"].search(line)
            if match:
                findings.append({
                    "path": path,
                    "line": number,
                    "check": name,
                    "severity": check["severity"],
                    "why": check["why"],
                    "remedy": check["remedy"],
                    "excerpt": line.strip()[:160],
                })
    return findings


def lint_docs(project: Path) -> dict[str, Any]:
    """Lint every public document in the project."""
    project = Path(project)
    ignore = tuple(_config(project).get("ignore_checks") or ())
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(project.rglob("*")):
        if not path.is_file() or not _is_public(path, project):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        findings.extend(
            lint_text(path.relative_to(project).as_posix(), text, ignore=ignore))
    high = [f for f in findings if f["severity"] == "high"]
    return {
        "documents_scanned": scanned,
        "findings": findings,
        "high_severity": len(high),
        "ignored_checks": list(ignore),
        "verdict": "clean" if not findings else "findings",
    }
