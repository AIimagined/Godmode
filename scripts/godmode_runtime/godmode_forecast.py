"""B6-B: pre-flight risk forecast and retroactive policy replay.

Both read the same corpus. The archive holds every refusal the gate ever
produced - operation, tool, category, and the tier it carried at the time -
so both answers come from this project's own history rather than from a
heuristic tuned by feel.

**Forecast** classifies an operation before it runs and says whether this
project has met its shape before. A tier on its own is a rule; a tier plus
"this category was refused 44 times here" is a reason, and a reason is what
makes an interruption worth reading.

**Replay** re-classifies operations the archive already holds under
*today's* rules and compares against the tier recorded then. It is the only
way to see what a policy change did to work already done - a question that
cannot be asked of the policy file, because the policy file has no memory
of what it used to say.

The direction of drift carries the meaning. A rule that got stricter is
expected: the ratchet only tightens. A rule that got **looser** means
something once stopped would now pass, which is exactly the regression the
ratchet exists to prevent - so the two are reported separately rather than
summed into a count of differences that hides which way they went.

Nothing here writes a record or changes a policy. It reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_sentinel import classify_action

# Harmless to irreversible. Ordered rather than compared as strings so
# "R10" would not sort below "R2" if the scale is ever extended.
TIER_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}

_UNPROTECTED_TIER = "R0"
_MAX_EXAMPLES = 5

# `godmode hooks probe` records refusals whose "operation" is a sentinel
# token rather than a command. The plain classifier cannot rate a token, so
# replaying one reads as a rule that went soft. Nine sat in this project's
# archive and accounted for the entire apparent relaxation, so they are
# counted apart rather than mixed into drift.
_SYNTHETIC_PREFIX = "godmode-probe:"


def _refusals(archive: Chronicle) -> list[dict[str, Any]]:
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return []
    return [r for r in events if r.get("kind") == "refusal"]


def _classify(operation: str, project_root: Path | None) -> dict[str, Any]:
    try:
        return classify_action(operation, project_root=project_root)
    except Exception:
        # The classifier is the thing under test in replay; a shape it
        # cannot parse must not take the whole report down with it. The
        # caller sees an unclassified row rather than a traceback.
        return {}


def _tier_of(verdict: dict[str, Any]) -> str:
    """The classifier's own tier, which is NOT the same question as `protected`.

    `classify_action` can answer `protected: False` while still rating the
    operation - a worktree file mutation comes back R2 and unprotected,
    meaning "this is what it touches, and no rule stops it here". Reading
    the flag instead of the tier and calling an unprotected operation R0
    invents a drop from whatever tier it actually carries.

    Found by replaying this project's own archive: it reported 22
    relaxations that were all this mapping, not a policy change.
    """
    tier = verdict.get("tier")
    if tier:
        return str(tier)
    return _UNPROTECTED_TIER


def forecast(archive: Chronicle, operation: str,
             project_root: Path | None = None) -> dict[str, Any]:
    """What this operation would be classified as, and what precedent exists."""
    operation = operation.strip()
    if not operation:
        raise ArchiveError("Nothing to forecast: the operation is empty")
    verdict = _classify(operation, project_root)
    category = verdict.get("category")
    tier = _tier_of(verdict)
    same_category: list[str] = []
    for record in _refusals(archive):
        data = record.get("data") or {}
        if category and data.get("category") == category:
            text = str(data.get("operation", ""))
            if text and text not in same_category:
                same_category.append(text)
    return {
        "operation": operation,
        "protected": bool(verdict.get("protected")),
        "tier": tier,
        "category": category,
        "impact": verdict.get("impact") or [],
        "second_confirmation_required": bool(
            verdict.get("second_confirmation_required")),
        "precedent": {
            # Counted over distinct operations, not raw records: the same
            # command refused forty times is one precedent said forty
            # times, and reporting the record count would overstate how
            # much independent evidence there is.
            "same_category": len(same_category),
            "examples": same_category[:_MAX_EXAMPLES],
        },
        "note": ("classification is from today's rules; precedent is what "
                 "this project already refused in the same category"),
    }


def replay(archive: Chronicle,
           project_root: Path | None = None) -> dict[str, Any]:
    """Re-classify recorded operations under today's rules and report drift."""
    drifted: list[dict[str, Any]] = []
    relaxed: list[dict[str, Any]] = []
    tightened: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    synthetic: list[dict[str, Any]] = []
    total = 0
    for record in _refusals(archive):
        data = record.get("data") or {}
        operation = str(data.get("operation", "")).strip()
        if not operation:
            continue
        if operation.startswith(_SYNTHETIC_PREFIX):
            synthetic.append(
                {"sequence": record.get("sequence"), "operation": operation})
            continue
        total += 1
        then_tier = str(data.get("tier") or _UNPROTECTED_TIER)
        then_category = data.get("category")
        verdict = _classify(operation, project_root)
        if not verdict:
            unclassified.append(
                {"sequence": record.get("sequence"), "operation": operation})
            continue
        now_tier = _tier_of(verdict)
        now_category = verdict.get("category")
        if now_tier == then_tier and now_category == then_category:
            continue
        entry = {
            "sequence": record.get("sequence"),
            "operation": operation,
            "then": {"tier": then_tier, "category": then_category},
            "now": {"tier": now_tier, "category": now_category},
        }
        drifted.append(entry)
        before = TIER_ORDER.get(then_tier, 0)
        after = TIER_ORDER.get(now_tier, 0)
        if after < before:
            relaxed.append(entry)
        elif after > before:
            tightened.append(entry)
    return {
        "total": total,
        "drifted": drifted,
        # Separated deliberately: a tightening is the ratchet working, a
        # relaxation is the regression it exists to catch. A single count
        # of differences would hide which of the two happened.
        "relaxed": relaxed,
        "tightened": tightened,
        "unclassified": unclassified,
        # Probe sentinels, excluded from `total` and from drift: they are
        # tokens the probe wrote, not commands anyone ran.
        "synthetic": synthetic,
        "note": ("`relaxed` is the one to read: an operation once stopped "
                 "that today's rules would let through"),
    }
