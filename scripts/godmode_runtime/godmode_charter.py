"""Compile a project's prose operating guidance into addressable rules.

Prose cannot be enforced. A paragraph that says "never push without asking" is a
suggestion with formatting; a rule with an id, a trigger and a verification method is
a gate. This module performs that conversion and is honest about its limits: a rule
whose compliance cannot be checked is admitted and labelled ADVISORY, never dropped
and never dressed up as enforced.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .godmode_corpus import Binding, Segment, resolve_roles, segment_document

HARD = "HARD"
SOFT = "SOFT"
ADVISORY = "ADVISORY"

TRIGGERS = (
    "session_open",
    "before_approach",
    "before_mutation",
    "before_completion",
    "session_close",
    "always",
)

# A rule only earns HARD when a shape below tells us how to check it. The table is
# deliberately small: guessing a verification method would manufacture exactly the
# false enforcement the honest-enforcement guarantee exists to prevent.
_SHAPES: tuple[tuple[str, str, str, str], ...] = (
    # pattern, verify kind, trigger, enforcement
    (r"\bcite[sd]?\b|\bevidence (?:before|first)\b|\bwith evidence\b",
     "citation_resolves", "before_completion", HARD),
    (r"\bnever\b.*\bwithout\b|\bnot\b.*\bunless\b|\bonly (?:after|with)\b",
     "attestation_present", "before_mutation", HARD),
    (r"\bbefore (?:any|every|touching|changing|proposing|writing|the fix)\b|\bpre-?flight\b",
     "attestation_present", "before_mutation", HARD),
    (r"\b(?:both|together|and its guard|paired|same pass)\b",
     "pair_complete", "before_completion", HARD),
    (r"\b(?:check|read|scan|search|verify) .*\bfirst\b",
     "attestation_present", "before_approach", HARD),
    (r"\bevery (?:fix|change|task|bug) .*\bguard\b|\bguard\b.*\bmust\b",
     "attestation_present", "before_completion", HARD),
    (r"\bre-?run\b|\bmust pass\b|\bexit(?:s)? (?:zero|non-zero)\b",
     "command_exit_zero", "before_completion", SOFT),
    (r"\benumerate\b|\blist every\b|\breport (?:what|every|all)\b",
     "record_field_set", "before_completion", SOFT),
)

# Lines that read as directives. Everything else is narration.
_DIRECTIVE = re.compile(
    r"\b(?:must|never|always|do not|don't|shall|require[sd]?|before|after|"
    r"ensure|verify|confirm|check|prohibited|forbidden|mandatory)\b",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_NOISE = re.compile(r"^\s*(?:\||#|>|<)")


@dataclass(frozen=True)
class Rule:
    """One compiled, addressable rule."""

    id: str
    role: str
    path: str
    line: int
    text: str
    trigger: str
    enforcement: str
    verify: str

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "source": f"{self.path}:{self.line}",
            "text": self.text,
            "trigger": self.trigger,
            "enforcement": self.enforcement,
            "verify": self.verify,
        }


def _classify(text: str) -> tuple[str, str, str]:
    """Return (enforcement, verify_kind, trigger) for one directive."""
    lowered = text.lower()
    for pattern, kind, trigger, enforcement in _SHAPES:
        if re.search(pattern, lowered):
            return enforcement, kind, trigger
    return ADVISORY, "none", "always"


def _rule_id(role: str, path: str, text: str) -> str:
    digest = hashlib.sha256(f"{role}\x00{path}\x00{text}".encode("utf-8")).hexdigest()
    return f"R-{digest[:10]}"


def _directives(segment: Segment) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    fenced = False
    for offset, raw in enumerate(segment.body.splitlines()):
        if _FENCE.match(raw):
            fenced = not fenced
            continue
        if fenced:
            continue
        line = _BULLET.sub("", raw).strip()
        if not line or _NOISE.match(raw) and not _BULLET.match(raw):
            continue
        # Strip emphasis and inline markup so shape matching sees plain words.
        line = re.sub(r"[*_`]+", "", line).strip()
        if len(line) < 12 or not _DIRECTIVE.search(line):
            continue
        found.append((segment.start_line + offset, line))
    return found


def compile_binding(binding: Binding, project: Path) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for segment in segment_document(binding, project):
        for line, text in _directives(segment):
            enforcement, verify, trigger = _classify(text)
            identifier = _rule_id(segment.role, segment.path, text)
            if identifier in seen:
                continue
            seen.add(identifier)
            rules.append(
                Rule(
                    id=identifier,
                    role=segment.role,
                    path=segment.path,
                    line=line,
                    text=text,
                    trigger=trigger,
                    enforcement=enforcement,
                    verify=verify,
                )
            )
    return rules


def compile_charter(project: Path) -> dict[str, Any]:
    """Compile every bound authority document into a rule set.

    Reported counts are the point: a project learns how much of its own guidance is
    actually checkable, rather than assuming all of it is.
    """
    resolution = resolve_roles(project)
    rules: list[Rule] = []
    for binding in resolution.bindings:
        rules.extend(compile_binding(binding, resolution.project))

    rules.sort(key=lambda rule: (rule.path, rule.line))
    counts = {level: 0 for level in (HARD, SOFT, ADVISORY)}
    by_role: dict[str, int] = {}
    for rule in rules:
        counts[rule.enforcement] += 1
        by_role[rule.role] = by_role.get(rule.role, 0) + 1

    return {
        "rules": len(rules),
        "enforcement": counts,
        "by_role": dict(sorted(by_role.items())),
        "documents": len(resolution.bindings),
        "compiled": [rule.view() for rule in rules],
    }


def rules_for(charter: dict[str, Any], trigger: str, enforcement: str | None = None) -> list[dict[str, Any]]:
    return [
        rule
        for rule in charter["compiled"]
        if rule["trigger"] == trigger and (enforcement is None or rule["enforcement"] == enforcement)
    ]


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "GODMODE.md").write_text(
            "# Gates\n"
            "- Never commit without an explicit ask.\n"
            "- Before any fix, scan the invariant registry first.\n"
            "- Every fix must own a guard and its guard must be seen to fail.\n"
            "- A claim must cite evidence before completion.\n"
            "- The product is a local-first control plane.\n"
            "```\nnever run this code block directive\n```\n",
            encoding="utf-8",
        )
        charter = compile_charter(project)

        assert charter["rules"] >= 4, charter["enforcement"]
        assert charter["enforcement"][HARD] >= 3, charter["enforcement"]

        texts = [rule["text"] for rule in charter["compiled"]]
        # Narration is not a rule.
        assert not any("control plane" in text for text in texts), texts
        # Fenced code is never compiled into a rule.
        assert not any("code block directive" in text for text in texts), texts

        kinds = {rule["verify"] for rule in charter["compiled"]}
        assert "citation_resolves" in kinds, kinds

        # Ids are stable across runs, so attestations can reference them durably.
        again = compile_charter(project)
        assert [r["id"] for r in charter["compiled"]] == [r["id"] for r in again["compiled"]]

        # An unverifiable directive is admitted and labelled, never dropped.
        (project / "GODMODE.md").write_text(
            "# Feel\n- The interface must feel premium.\n", encoding="utf-8"
        )
        soft = compile_charter(project)
        assert soft["rules"] == 1, soft
        assert soft["enforcement"][ADVISORY] == 1, soft

    print("godmode_charter self-check OK")


if __name__ == "__main__":
    _self_check()
