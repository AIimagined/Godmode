"""Disposition register with superseded states and rejection precedent (U-V2).

A closed-enumeration register over decisions where "was true, got superseded"
and "worse than baseline" are first-class facts, refusals become citable
precedent instead of tribal memory, and every entry points at the evidence
that put it there.

**Derived view, never stored.** The register is not a record kind of its
own - it is a pure fold over `decision` records whose subject is
`reg:<domain>:<key>`, the same regeneration rule E52 named: a view computed
fresh from the archive on every read can never drift from the ledger that
backs it, because there is no second copy to drift. `register_view()`
recomputes latest-state-per-key, with full lineage, every time it is called.

**Closed enumeration, not free text.** A state that is not one of `STATES`
is not a new disposition someone invented on the fly; it is a mistake. An
unlisted key - one nobody ever wrote a register record for - reads as the
explicit named default `open`, not as an error and not as `None`: "nothing
decided yet" is itself a fact this register can state.

**Evidence is not optional.** Every non-`open` entry must carry at least one
`witness:`/`verdict:`/`file:` evidence citation - E52's defect was a
register with no evidence discipline, so a state and the reason for it could
drift apart with nothing to notice. Refused at `set_state()`, and refused
again at the archive seam itself (`godmode_invariants._register_invariants`,
seeded eagerly into `Chronicle.append()`'s `KIND_INVARIANTS`) so a raw
`archive.append()` that bypasses this module is held to the same rule.

**Legal transitions only.** `open` is the only state anything may enter
freely - there is nothing yet to contradict. Every other state is a closed
disposition: leaving it requires a record that names `supersedes:<seq>`
citing the exact record it replaces, so the lineage is an explicit chain of
citations rather than "whichever record is newest wins by default." The one
path back into `established` from a closed disposition - including
`rejected-precedent` - is that same citing supersede; nothing else reopens
it. `set_state()` enforces this at write time for every caller that goes
through it. A raw `archive.append()` cannot be refused the same way, because
enforcing it needs the archive's history and the kind-invariant hook the
archive seam offers only ever sees one record's `data` in isolation - so an
illegal transition written that way lands on disk, and `conflict_findings()`
is the read-time detector that catches it: a planted conflicting record
becomes a blocking finding, not a silent state flip.

**Rejection precedent.** A `rejected-precedent` entry is a refusal a later
session can cite instead of re-litigating: `precheck()` (see
`godmode_precheck.py`) matches a task's normalized terms against every
`rejected-precedent` key across every domain and surfaces the precedent's
sequence with the instruction that closes the loop - cite it and supersede
it, or drop the work.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# Closed enumeration. Anything not in this tuple is not a fourth kind of
# "sort of decided" - it is refused at set_state() and at the archive seam,
# never silently accepted and never silently coerced into a listed state.
STATES = (
    "established", "superseded", "refuted", "worse-than-baseline",
    "matched-baseline", "rejected-precedent", "open",
)

# Evidence prefixes that count as "this state points at something checkable."
# Mirrored (not imported) in godmode_invariants._register_invariants - see
# that module's docstring for why the duplication is deliberate.
EVIDENCE_PREFIXES = ("witness:", "verdict:", "file:")

# The legal target states reachable FROM each state. `open` is the implicit
# default for a key with no records at all, and it is also a state a caller
# may write explicitly (e.g. to attach a delta with no firm disposition
# yet) - either way, anything is reachable from it, because nothing has been
# decided yet to contradict. Every other state is a closed disposition:
# `established` is the live center, reachable only from `open` or (via a
# citing supersede) from any closed disposition; the four terminal outcomes
# (`superseded`, `refuted`, `worse-than-baseline`, `matched-baseline`) are
# reached only by first being `established` and then superseded out of it,
# or directly from `open` for a first-time evaluation against a baseline;
# `rejected-precedent` is reached only from `open` - a proposal rejected
# before it was ever established - and its only way out is back to
# `established`, and only by citing it.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset(STATES),
    "established": frozenset(
        {"superseded", "refuted", "worse-than-baseline", "matched-baseline"}
    ),
    "superseded": frozenset({"established"}),
    "refuted": frozenset({"established"}),
    "worse-than-baseline": frozenset({"established"}),
    "matched-baseline": frozenset({"established"}),
    "rejected-precedent": frozenset({"established"}),
}

DELTAS = ("added", "modified", "removed")

_SUBJECT_PREFIX = "reg:"


def _subject(domain: str, key: str) -> str:
    return f"{_SUBJECT_PREFIX}{domain}:{key}"


def _domain_records(archive: Chronicle, domain: str) -> list[dict[str, Any]]:
    if not archive.initialized():
        return []
    prefix = f"{_SUBJECT_PREFIX}{domain}:"
    return [
        record for record in archive.read_events()
        if record.get("kind") == "decision" and record.get("subject", "").startswith(prefix)
    ]


def _key_of(record: dict[str, Any]) -> str | None:
    data = record.get("data") or {}
    key = data.get("register_key")
    return str(key) if key else None


def _grouped_by_key(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = _key_of(record)
        if key is None:
            continue
        by_key[key].append(record)
    for entries in by_key.values():
        entries.sort(key=lambda r: r["sequence"])
    return by_key


def register_view(archive: Chronicle, domain: str) -> dict[str, dict[str, Any]]:
    """Fold every `reg:<domain>:<key>` record into latest-state-per-key.

    Pure function of the archive's current content - never stored, never
    cached beyond one call. Only keys with at least one record appear here;
    an unlisted key's state is the named default `open`, read through
    `state_of()` rather than a missing dict entry, so "nothing decided" has
    an explicit name instead of being inferred from a `KeyError`.
    """
    view: dict[str, dict[str, Any]] = {}
    for key, entries in _grouped_by_key(_domain_records(archive, domain)).items():
        latest = entries[-1]
        data = latest.get("data") or {}
        view[key] = {
            "state": data.get("state", "open"),
            "sequence": latest["sequence"],
            "evidence": list(latest.get("evidence") or []),
            "lineage": [entry["sequence"] for entry in entries],
            "delta": data.get("delta"),
        }
    return view


def state_of(archive: Chronicle, domain: str, key: str) -> str:
    """The current state of one key - `open` by explicit default, not absence."""
    entry = register_view(archive, domain).get(key)
    return entry["state"] if entry is not None else "open"


def domains(archive: Chronicle) -> set[str]:
    """Every domain with at least one register record."""
    if not archive.initialized():
        return set()
    found: set[str] = set()
    for record in archive.read_events():
        if record.get("kind") != "decision":
            continue
        subject = record.get("subject", "")
        if not subject.startswith(_SUBJECT_PREFIX):
            continue
        # reg:<domain>:<key> - domain never contains ':', keys may (matches
        # rsplit-free parsing everywhere else in this module).
        parts = subject.split(":", 2)
        if len(parts) >= 2 and parts[1]:
            found.add(parts[1])
    return found


def set_state(
    archive: Chronicle,
    domain: str,
    key: str,
    state: str,
    evidence: list[str] | None,
    *,
    supersedes: int | None = None,
    delta: str | None = None,
) -> dict[str, Any]:
    """Record a disposition for `reg:<domain>:<key>`, refusing an illegal write.

    Refuses (ArchiveError) before ever touching the archive: an unlisted
    state, a non-open state with no witness:/verdict:/file: evidence, an
    illegal transition per `LEGAL_TRANSITIONS`, or a transition away from a
    non-open state whose `supersedes` does not name the exact record it
    replaces. The same evidence/state-membership rule is also enforced by
    `godmode_invariants._register_invariants` at the archive seam, so a raw
    `archive.append()` that skips this function cannot slip either check
    past silently - but the transition/supersedes rule needs this
    function's read of the archive's history to enforce at write time; a
    raw append that gets the state and evidence right but the lineage wrong
    lands on disk and is caught instead by `conflict_findings()`.
    """
    if state not in STATES:
        raise ArchiveError(f"Unknown register state '{state}'; expected one of {', '.join(STATES)}")
    if delta is not None and delta not in DELTAS:
        raise ArchiveError(f"Unknown delta '{delta}'; expected one of {', '.join(DELTAS)}")
    evidence = list(evidence or [])
    if state != "open" and not any(e.startswith(EVIDENCE_PREFIXES) for e in evidence):
        raise ArchiveError(
            f"Register state '{state}' needs witness:/verdict:/file: evidence; none given"
        )

    view = register_view(archive, domain)
    current = view.get(key)
    current_state = current["state"] if current is not None else "open"
    legal_targets = LEGAL_TRANSITIONS.get(current_state, frozenset())
    if state not in legal_targets:
        raise ArchiveError(
            f"Illegal register transition for '{domain}:{key}': "
            f"'{current_state}' -> '{state}' is not permitted "
            f"(legal targets from '{current_state}': {sorted(legal_targets) or 'none'})"
        )
    if current_state != "open":
        current_seq = current["sequence"]
        if supersedes != current_seq:
            raise ArchiveError(
                f"Leaving '{current_state}' for '{domain}:{key}' needs "
                f"supersedes={current_seq} (the record it replaces); got {supersedes!r}"
            )

    data = {
        "register_domain": domain,
        "register_key": key,
        "state": state,
        "supersedes": supersedes,
        "delta": delta,
        # Denormalised copy of `evidence`: the archive-seam invariant hook
        # (godmode_invariants._register_invariants) sees only `data`, never
        # the separate `evidence=` argument append() also stores, so the
        # evidence-sufficiency rule needs its own citations inside `data`
        # to be enforceable for a raw append that bypasses this function.
        "evidence": list(evidence),
    }
    return archive.append("decision", _subject(domain, key), data, evidence=evidence)


def conflict_findings(archive: Chronicle, domain: str) -> list[dict[str, Any]]:
    """Illegal lineages a raw append could write that `set_state()` would refuse.

    `set_state()` enforces legal-transition-only and correct-supersedes-citation
    at write time, but only for callers that go through it; a hand-built
    `archive.append("decision", "reg:...", ...)` bypasses it entirely and
    the archive-seam invariant hook cannot catch a lineage error because it
    only ever sees one record's `data`, never the archive's history. This
    walks every key's full lineage in sequence order and reports exactly
    the same two violations `set_state()` would have refused - a HARD halt
    finding per E6: "conflict, ask before doing anything else," not a
    silent latest-wins.
    """
    findings: list[dict[str, Any]] = []
    for key, entries in _grouped_by_key(_domain_records(archive, domain)).items():
        state = "open"
        seq: int | None = None
        for record in entries:
            data = record.get("data") or {}
            next_state = data.get("state")
            next_seq = record["sequence"]
            if next_state not in STATES:
                findings.append({
                    "domain": domain, "key": key, "sequence": next_seq,
                    "conflict": "unknown-state",
                    "message": f"seq:{next_seq} declares unlisted state '{next_state}'",
                })
                state, seq = "open", None
                continue
            legal_targets = LEGAL_TRANSITIONS.get(state, frozenset())
            illegal_transition = next_state not in legal_targets
            bad_supersedes = state != "open" and data.get("supersedes") != seq
            if illegal_transition or bad_supersedes:
                findings.append({
                    "domain": domain, "key": key, "sequence": next_seq,
                    "conflict": "illegal-transition" if illegal_transition else "bad-supersedes",
                    "message": (
                        f"seq:{next_seq} moves '{key}' from '{state}' to '{next_state}' "
                        f"without a legal, correctly-cited supersede "
                        f"(supersedes={data.get('supersedes')!r}, expected {seq!r}): "
                        "conflict - ask before doing anything else"
                    ),
                })
            state, seq = next_state, next_seq
    return findings


def rejected_precedents(archive: Chronicle) -> list[dict[str, Any]]:
    """Every key, across every domain, whose latest state is `rejected-precedent`.

    Read by `godmode_precheck.py` so a task about to redo refused work is
    told to cite the precedent's sequence and supersede it, or drop the
    work, instead of re-litigating a decision the archive already made.
    """
    hits: list[dict[str, Any]] = []
    for domain in sorted(domains(archive)):
        for key, entry in register_view(archive, domain).items():
            if entry["state"] == "rejected-precedent":
                hits.append({"domain": domain, "key": key, "sequence": entry["sequence"]})
    return hits
