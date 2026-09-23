"""Checklist templates: a ritual written down as items a record can be read against.

The RCA ritual (NS-13g) is six steps, in order: what failed (expected,
actual, and a reproduction), when it started (a bisect or the last green
run), where it lives (the smallest failing unit), why (a method record whose
contract is complete), the fix at the root, and the lock (a test, and an
invariant when one is needed). `method --check-record` reads the checklist
when the record carries one, and a skipped step makes the record incomplete
by name - `incomplete:when` - instead of letting a confident story stand in
for the step nobody did.

A checklist is either inline in the RCA record (`"rca": {step: {...}}`) or a
label naming archived `checklist` items `rca:<label>:<step>` written with
`checklist update --status complete --evidence ...`.
"""

from __future__ import annotations

import re
from typing import Any

from .godmode_chronicle import Chronicle

RCA_STEPS = ("what", "when", "where", "why", "fix-root", "lock")

TEMPLATES: dict[str, tuple[dict[str, str], ...]] = {
    "rca": (
        {"step": "what", "text": "What failed: expected, actual, and the reproduction command.",
         "evidence": "repro:<the failing command> & expected:<what should happen> & actual:<what happened>"},
        {"step": "when", "text": "When it started: a bisect, or the last green run against the first red.",
         "evidence": "cmd:git bisect ... | cmd:git log ... | diff:<seq> | seq:<last green run>"},
        {"step": "where", "text": "Where it lives: the smallest unit that still fails.",
         "evidence": "file:<path>#L<a>-L<b>"},
        {"step": "why", "text": "Why: a method record whose completion contract holds.",
         "evidence": "the record `method --check-record` reads"},
        {"step": "fix-root", "text": "Fix the root, not the symptom.",
         "evidence": "file:<path>#L<a>-L<b>"},
        {"step": "lock", "text": "Lock it: a test that fails without the fix, and an invariant if one is needed.",
         "evidence": "cmd:<the test run>"},
    ),
}

_DONE = ("complete", "done")
_WHEN_CITE = re.compile(r"^(?:diff:\d+|seq:\d+|cmd:git\s+(?:bisect|log)\b|last-green:.+)")
# A lock is a test that runs: a command naming a test runner, or a test file.
# A cite that merely contains the letters "test" (`file:latest.md`) is not.
_LOCK_CITE = re.compile(
    r"(?i)^cmd:.*\b(?:unittest|pytest|nose2|tox|jest|vitest|mocha|rspec|phpunit|ctest"
    r"|(?:npm|pnpm|yarn|go|cargo|dotnet|mix|make)\s+test)\b"
    r"|^file:(?:[^#]*[/\\])?(?:tests?[/\\]|test_[^/\\#]+|[^/\\#]+_test\.)")


def _evidence(step: Any) -> list[str]:
    if not isinstance(step, dict):
        return []
    return [str(c) for c in step.get("evidence") or [] if str(c).strip()]


def rca_gaps(steps: dict[str, Any], contract_complete: bool) -> list[str]:
    """`incomplete:<step>` for each RCA step the checklist skipped or left unproven."""
    gaps: list[str] = []
    for name in RCA_STEPS:
        step = steps.get(name)
        cites = _evidence(step)
        if name == "what":
            # Expected and actual are required either way: inline fields, or
            # `expected:`/`actual:` evidence entries on an archived item.
            def stated(field: str) -> bool:
                return (isinstance(step, dict) and bool(str(step.get(field, "")).strip())) or any(
                    c.startswith(f"{field}:") and c[len(field) + 1:].strip() for c in cites)
            held = any(c.startswith("repro:") for c in cites) and stated("expected") and stated("actual")
        elif name == "when":
            held = any(_WHEN_CITE.match(c) for c in cites)
        elif name == "why":
            held = bool(cites) and contract_complete
        elif name == "lock":
            held = any(_LOCK_CITE.search(c) for c in cites)
        else:
            held = bool(cites)
        if not held:
            gaps.append(f"incomplete:{name}")
    return gaps


def archived_rca(archive: Chronicle, label: str) -> dict[str, Any]:
    """The newest complete `rca:<label>:<step>` checklist item per step."""
    prefix = f"rca:{label}:"
    steps: dict[str, Any] = {}
    for record in archive.read_events():
        if record.get("kind") != "checklist" or not str(record.get("subject", "")).startswith(prefix):
            continue
        name = record["subject"][len(prefix):]
        data = record.get("data") or {}
        if data.get("status") in _DONE:
            steps[name] = {"evidence": list(record.get("evidence") or []),
                           "note": data.get("note"), "archived": True}
        else:
            steps.pop(name, None)
    return steps


def template_items(name: str, label: str) -> list[dict[str, str]]:
    """The template's items as paste-ready `checklist update` rows for `label`."""
    rows = []
    for item in TEMPLATES[name]:
        subject = f"{name}:{label}:{item['step']}"
        # " & " joins evidence that is all required; " | " separates alternatives.
        required = item["evidence"].split(" | ")[0].split(" & ")
        flags = " ".join(f'--evidence "{cite}"' for cite in required)
        rows.append({
            "item": subject, "text": item["text"], "evidence": item["evidence"],
            "command": f'godmode checklist update --item "{subject}" --status complete {flags}',
        })
    return rows
