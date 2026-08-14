"""Kind-specific record-shape invariants, enforced INNATELY by the archive.

Fix-round-1 registered a verdict validator as a side effect of importing
`godmode_verdict.py` - which meant a process that imported `godmode_chronicle`
without ever importing `godmode_verdict` (directly or transitively) saw an
empty registry and could append either forbidden verdict combination
unchecked. That is the same bypass the invariant exists to close, reborn
through import order.

This module fixes that by being the thing `godmode_chronicle.py` imports
itself, at its own module load, rather than waiting for some other module to
opt in. It is deliberately dependency-free with respect to the archive: it
imports nothing from `godmode_chronicle` or `godmode_verdict` (only the
plain exception type, which has no imports of its own), so
`godmode_chronicle` can import it unconditionally with no cycle. The result:
`KIND_INVARIANTS` in `godmode_chronicle.py` is populated the moment
`godmode_chronicle` is imported - before any `Chronicle.append()` call is
even possible - regardless of what else the calling process has or has not
imported.

A future kind that needs a shape invariant (U-V2's `register`, U-R3's
experiment ledger's own `verdict` records) adds its validator function HERE
and lists it in `KIND_VALIDATORS` below - never inside the kind's own owning
module, where it would just reproduce this same import-order gap.
"""

from __future__ import annotations

from typing import Any, Callable

from .godmode_errors import ArchiveError

KindInvariant = Callable[[dict[str, Any]], None]


def _verdict_invariants(data: dict[str, Any]) -> None:
    """U-V1's two forbidden combinations - never two dispositions worth of trust for one.

    Drive-vs-acquit: a self-acquitted "confirmed" would let an agent grade
    its own quality as verified; only an independent checker may do that.
    Terminated-vs-truncated: a "confirmed" on a truncated (budget/timeout
    cutoff) run would let exhaustion impersonate completion.
    """
    if data.get("disposition") != "confirmed":
        return
    if data.get("acquitted_by") == "self":
        raise ArchiveError(
            "acquitted_by='self' may attest execution completeness only; a "
            "'confirmed' disposition needs an independent checker "
            "(acquitted_by='independent') - self-acquitted quality is refused"
        )
    if data.get("run_state") == "truncated":
        raise ArchiveError(
            "a truncated run cannot be recorded 'confirmed'; budget or "
            "timeout exhaustion must not impersonate completion"
        )


# U-V2's register/evidence disconnect - kept in sync with
# godmode_register.STATES and godmode_register.EVIDENCE_PREFIXES by hand,
# not by import: this module stays dependency-free (see the module
# docstring above) so godmode_chronicle can keep importing it with no
# cycle risk, and godmode_register itself imports godmode_chronicle, so a
# reverse import here (invariants -> register -> chronicle) would recreate
# the very cycle that dependency-freedom exists to avoid. tests.test_register
# asserts the two tuples still agree.
_REGISTER_STATES = (
    "established", "superseded", "refuted", "worse-than-baseline",
    "matched-baseline", "rejected-precedent", "open",
)
_REGISTER_EVIDENCE_PREFIXES = ("witness:", "verdict:", "file:")


def _register_invariants(data: dict[str, Any]) -> None:
    """U-V2's structural facts, checkable from `data` alone.

    Only fires for register-shaped `decision` records - every other subject
    this kind carries (removals, capability negotiations, charter reviews,
    skill lifecycle...) has no `register_key` field and passes through
    unexamined. Once `register_key` IS present, though, the record has
    declared itself register-shaped, and everything below is enforced -
    there is no such thing as a register-shaped record this hook lets
    through unexamined:

    - `state` must be present at all. Fix-round-1 review caught a gap here:
      an earlier version of this guard skipped validation entirely for a
      register-shaped record with no `state` field, which then read as a
      silent `open` through `state_of()`/`register_view()` while
      `conflict_findings()` simultaneously flagged the very same record as
      an unknown-state conflict - two read paths disagreeing about one
      record, reachable only through a raw append (`set_state()` always
      supplies `state` from a required argument). A missing `state` is not
      "not register-shaped," it is a malformed register record, and is
      refused here on that same structural, single-record basis.
    - the declared state must be one of the closed enumeration; an unlisted
      spelling is refused outright rather than silently read as `open`, so
      garbage never reaches the ledger for a later reader to explain away.
    - a non-open state must carry at least one witness:/verdict:/file:
      evidence citation. `godmode_register.set_state()` denormalises its
      evidence list into `data["evidence"]` for exactly this reason - this
      hook is called with `data` only, never the separate `evidence=`
      argument `Chronicle.append()` also stores, so the citation has to
      already be inside `data` to be checkable here at all.

    What this does NOT check - because it structurally cannot - is transition
    legality, whether a `supersedes` value names the record it actually
    replaces, or whether the subject's own key segment agrees with
    `data["register_key"]`: all three need either the archive's history or
    the record's real stored `subject`, neither of which a single record's
    `data` carries. `godmode_register.set_state()` refuses the
    history-dependent ones at write time for callers that go through it;
    `conflict_findings()` detects all three at read time for a raw append
    that does not.
    """
    if "register_key" not in data:
        return
    state = data.get("state")
    if state is None:
        raise ArchiveError(
            "Register-shaped decision record (register_key present) has no "
            "'state' field - a register entry with no state is malformed, "
            "not implicitly 'open'"
        )
    if state not in _REGISTER_STATES:
        raise ArchiveError(
            f"Unknown register state '{state}'; expected one of "
            f"{', '.join(_REGISTER_STATES)}"
        )
    if state == "open":
        return
    evidence = data.get("evidence") or []
    if not any(isinstance(item, str) and item.startswith(_REGISTER_EVIDENCE_PREFIXES)
               for item in evidence):
        raise ArchiveError(
            f"Register state '{state}' needs witness:/verdict:/file: evidence; none given"
        )


# kind -> validator. Every entry here is enforced unconditionally the moment
# godmode_chronicle.py is imported - see KIND_INVARIANTS in that module,
# which is seeded from this dict at chronicle module load, not populated
# lazily by whichever kind-owning module happens to be imported.
KIND_VALIDATORS: dict[str, KindInvariant] = {
    "verdict": _verdict_invariants,
    "decision": _register_invariants,
}
