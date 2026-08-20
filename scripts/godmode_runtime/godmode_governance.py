"""Sprint 8: governance proposed from this project's own record.

The pivot: stop shipping generic frames, start proposing the rules this
project's history already argues for. Every input exists already - refusals
carrying categories and tiers, obligations, lessons - and the promotion
target ships too, since the charter compiles and enforces rules. This adds
a synthesizer, not a subsystem.

Three guardrails, taken from the sprint plan and enforced structurally
rather than by convention:

1. **Propose, never install.** Nothing here writes to the charter. Reading
   candidates is a pure fold and does not write at all - if the review
   surface were itself a write, it would have become the enforcement
   surface. Promotion is a separate, explicit, human-invoked call.
2. **Tighten-only.** A candidate may add an obligation, never relax one.
   Structural, not checked after the fact: the synthesizer can only emit
   `direction: tighten`, because every rule class it knows how to build
   declares something protected or required. Relaxing stays a manual,
   chronicled operator act.
3. **Provenance and expiry.** Every candidate names the records supporting
   it, how many there are, and the window they span, so a reviewer can go
   read them instead of trusting a count.

And the trap the brainstorm agenda named: **approval fatigue is evidence of
tolerance, not of correctness.** A count is not a verdict. Candidates are
phrased as proposals carrying their evidence, never as findings, because
the thing that repeated might be a bad habit that happened to repeat.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
# The sprint plan left "merge or layer?" open for the recurring-ask miner.
# Layered: U-E10 already folds the request ledger into charter-rule
# candidates under this same propose-never-install shape. A second
# implementation over the same ledger would be a duplicate authority - two
# components answering "what keeps getting asked" that drift apart the
# moment either is edited - so this imports the miner instead of
# re-deriving what it already knows.
from .godmode_recurrence import mine_recurring_asks

# How much evidence before a candidate is worth a reviewer's attention.
# Per class, because the classes differ in how much a single observation
# means: one refused category is noise, while a repeated obligation is a
# person saying the same thing twice.
MIN_OBSERVATIONS = {
    "protected-category": 3,
    "repeated-obligation": 2,
}

_PROMOTION_PREFIX = "governance:promoted:"


def _events(archive: Chronicle) -> list[dict[str, Any]]:
    try:
        return archive.read_events(verify=False)
    except ArchiveError:
        return []


def _candidate_id(rule_class: str, subject: str) -> str:
    """Stable across reads, so a reviewer can promote what they just read.

    Derived from class and subject rather than from a counter: a counter
    would renumber whenever the archive grew, and the id a person copied
    out of yesterday's report would promote something else today.
    """
    seed = f"{rule_class}:{subject}".encode("utf-8", "replace")
    return f"{rule_class}-" + hashlib.sha256(seed).hexdigest()[:10]


def promoted_rules(archive: Chronicle) -> set[str]:
    """Candidate ids a person has already promoted."""
    promoted: set[str] = set()
    for record in _events(archive):
        subject = str(record.get("subject", ""))
        if record.get("kind") == "decision" and subject.startswith(_PROMOTION_PREFIX):
            promoted.add(subject[len(_PROMOTION_PREFIX):])
    return promoted


def _protected_category_candidates(
        events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One candidate per refusal category with enough distinct operations.

    Counted over DISTINCT operations, not raw records: the same command
    refused forty times is one habit observed forty times, and letting the
    record count drive the threshold would mint a rule from a single
    command someone retried in a loop.
    """
    by_category: dict[str, dict[str, Any]] = {}
    for record in events:
        if record.get("kind") != "refusal":
            continue
        data = record.get("data") or {}
        category = data.get("category")
        operation = str(data.get("operation", "")).strip()
        if not category or not operation:
            continue
        bucket = by_category.setdefault(str(category), {
            "operations": set(), "citations": [], "tiers": set(),
            "first_seen": None, "last_seen": None,
        })
        bucket["operations"].add(operation)
        if len(bucket["citations"]) < 10:
            bucket["citations"].append(f"seq:{record.get('sequence')}")
        if data.get("tier"):
            bucket["tiers"].add(str(data["tier"]))
        stamp = record.get("recorded_at")
        if stamp:
            if bucket["first_seen"] is None:
                bucket["first_seen"] = stamp
            bucket["last_seen"] = stamp
    results: list[dict[str, Any]] = []
    for category, bucket in sorted(by_category.items()):
        observations = len(bucket["operations"])
        if observations < MIN_OBSERVATIONS["protected-category"]:
            continue
        highest = max(bucket["tiers"], default="R0")
        results.append({
            "id": _candidate_id("protected-category", category),
            "class": "protected-category",
            "category": category,
            # Phrased as a proposal carrying its evidence. A reviewer who
            # disagrees needs to see what it stands on, not a verdict.
            "rule": (f"Declare '{category}' a protected category for this "
                     f"project: {observations} distinct operations in it have "
                     f"been refused here, up to {highest}."),
            "direction": "tighten",
            "observations": observations,
            "citations": bucket["citations"],
            "first_seen": bucket["first_seen"],
            "last_seen": bucket["last_seen"],
            "caution": ("frequency is evidence of what happened, not proof "
                        "that blocking it is right - read the citations"),
        })
    return results


def _repeated_obligation_candidates(
        events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """An obligation restated across sessions is a rule trying to exist."""
    by_subject: dict[str, dict[str, Any]] = {}
    for record in events:
        if record.get("kind") != "obligation":
            continue
        subject = str(record.get("subject", "")).strip()
        if not subject:
            continue
        bucket = by_subject.setdefault(subject, {
            "count": 0, "citations": [], "first_seen": None, "last_seen": None,
        })
        bucket["count"] += 1
        if len(bucket["citations"]) < 10:
            bucket["citations"].append(f"seq:{record.get('sequence')}")
        stamp = record.get("recorded_at")
        if stamp:
            if bucket["first_seen"] is None:
                bucket["first_seen"] = stamp
            bucket["last_seen"] = stamp
    results: list[dict[str, Any]] = []
    for subject, bucket in sorted(by_subject.items()):
        if bucket["count"] < MIN_OBSERVATIONS["repeated-obligation"]:
            continue
        results.append({
            "id": _candidate_id("repeated-obligation", subject),
            "class": "repeated-obligation",
            "category": None,
            "rule": (f"Promote the repeated obligation '{subject}' to a "
                     f"charter rule: it has been restated {bucket['count']} "
                     f"times without being discharged."),
            "direction": "tighten",
            "observations": bucket["count"],
            "citations": bucket["citations"],
            "first_seen": bucket["first_seen"],
            "last_seen": bucket["last_seen"],
            "caution": ("a carried obligation may be waiting on a decision "
                        "rather than on a rule - check which before promoting"),
        })
    return results


def _recurring_ask_candidates(archive: Chronicle) -> list[dict[str, Any]]:
    """U-E10's own candidates, re-dressed in the candidate shape.

    The miner owns the clustering (it shares `_terms` with the precheck, so
    "the same ask" means one thing across the runtime); this only adopts its
    output. Its threshold is its own - overriding it here would put the
    decision about what counts as recurring in two places.
    """
    try:
        mined = mine_recurring_asks(archive)
    except ArchiveError:
        # The miner reads the same archive this fold already read. If it
        # cannot, the other classes are still worth showing - governance
        # failing closed on one class would hide the rest. Narrow on
        # purpose: a broad catch here would swallow a real defect in the
        # miner and register against the swallow ratchet, which only ever
        # tightens.
        return []
    results: list[dict[str, Any]] = []
    for entry in mined.get("candidates") or []:
        terms = ", ".join(entry.get("terms") or [])
        if not terms:
            continue
        sessions = entry.get("sessions", 0)
        results.append({
            "id": _candidate_id("recurring-ask", terms),
            "class": "recurring-ask",
            "category": None,
            "rule": (f"Consider a SOFT charter rule for the recurring ask "
                     f"'{terms}': it has come up in {sessions} distinct "
                     f"sessions."),
            "direction": "tighten",
            "observations": sessions,
            "citations": list(entry.get("refs") or []),
            "first_seen": None,
            "last_seen": None,
            "caution": ("mined from prompts, which record what was wanted, "
                        "not what turned out to be right"),
        })
    return results


def candidates(archive: Chronicle) -> list[dict[str, Any]]:
    """Rules this project's record argues for. A pure read - never writes."""
    events = _events(archive)
    already = promoted_rules(archive)
    found = (_protected_category_candidates(events)
             + _repeated_obligation_candidates(events)
             + _recurring_ask_candidates(archive))
    # A promoted candidate stops being proposed: leaving it in the review
    # surface would ask the same person the same question forever, which is
    # how a review surface trains people to skim it.
    return [c for c in found if c["id"] not in already]


def promote(archive: Chronicle, candidate_id: str, *,
            reason: str) -> dict[str, Any]:
    """Record a person's decision to adopt a candidate.

    Refuses an id that is not currently proposed, so a typo cannot promote
    a rule nobody reviewed, and an already-promoted id cannot be recorded
    twice as though it were reviewed afresh.
    """
    candidate_id = candidate_id.strip()
    reason = (reason or "").strip()
    if not reason:
        raise ArchiveError("Promotion needs a reason: who reviewed it, and why")
    known = {c["id"]: c for c in candidates(archive)}
    if candidate_id not in known:
        raise ArchiveError(
            f"No candidate '{candidate_id}' is currently proposed; run "
            f"`godmode governance` to see the current review surface")
    candidate = known[candidate_id]
    return archive.append(
        "decision", f"{_PROMOTION_PREFIX}{candidate_id}",
        {"rule": candidate["rule"], "class": candidate["class"],
         "direction": candidate["direction"], "reason": reason,
         "observations": candidate["observations"]},
        evidence=list(candidate["citations"]),
    )


def governance_report(archive: Chronicle) -> dict[str, Any]:
    """The review surface, with the propose-never-install stance stated."""
    proposed = candidates(archive)
    return {
        "candidates": proposed,
        "promoted": sorted(promoted_rules(archive)),
        # Stated in the payload rather than left to be inferred: a reader
        # must never have to wonder whether looking at this changed
        # anything.
        "installed": False,
        "note": ("proposals only - nothing here is in force, and nothing "
                 "reaches the charter without `godmode governance promote`"),
    }
