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


# kind -> validator. Every entry here is enforced unconditionally the moment
# godmode_chronicle.py is imported - see KIND_INVARIANTS in that module,
# which is seeded from this dict at chronicle module load, not populated
# lazily by whichever kind-owning module happens to be imported.
KIND_VALIDATORS: dict[str, KindInvariant] = {
    "verdict": _verdict_invariants,
}
