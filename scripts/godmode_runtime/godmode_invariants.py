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

from datetime import datetime, timezone
import re
from typing import Any, Callable

from .godmode_constants import REGISTER_EVIDENCE_PREFIXES, REGISTER_STATES
from .godmode_errors import ArchiveError

KindInvariant = Callable[[dict[str, Any]], None]

# Fix round 1, C1(b) (Critical): the absolute ceiling a `hook-interception-
# proof` record's `expiry` may claim, checked here at APPEND time (the
# normal-write path's outright refusal) - `godmode_hookproof.py` checks the
# SAME literal, independently, at GRADING time (`_expiry_out_of_bounds`),
# so a record that somehow reaches disk anyway (an older archive, a
# hand-edited file) still cannot grade above `DEGRADED`. This module stays
# import-free of every archive-owning module on purpose (see the module
# docstring above) - including `godmode_hookproof.py`, which imports
# `godmode_chronicle` - so this is a DELIBERATE, independent copy of the
# same value, not an import, kept in sync BY HAND exactly the way
# `TOOL_ERROR_ACK` below already is with `godmode_verdict.py`'s own copy;
# `tests/test_failure_semantics.py` pins the two literals equal.
_PROOF_MAX_TTL_SECONDS = 24 * 60 * 60

# PARTIAL-P3/B3-7: kept in sync BY HAND with `godmode_verdict.TOOL_ERROR_ACK`
# - this module stays dependency-free of the archive-owning modules on
# purpose (see the module docstring above), so it cannot import the other
# copy; `tests.test_tool_error_gate` asserts the two patterns agree, the
# same discipline `_REGISTER_STATES` below already uses against
# `godmode_register.STATES`.
_TOOL_ERROR_ACK = re.compile(r"^acknowledged-remediated$|^acknowledged-deferred: .+$")


def _verdict_invariants(data: dict[str, Any]) -> None:
    """U-V1's forbidden combinations, extended by U-E4's panel fold - never a
    disposition worth of trust the record's own detail contradicts.

    Drive-vs-acquit: a self-acquitted "confirmed" would let an agent grade
    its own quality as verified; only an independent checker may do that.
    Terminated-vs-truncated: a "confirmed" on a truncated (budget/timeout
    cutoff) run would let exhaustion impersonate completion.
    Fold-vs-check (U-E4): a "confirmed" fold whose own `checks` list carries
    a checker that came back `refuted` is not confirmed, it is a fold that
    buried a dissent - that combination is `contested` or nothing, never
    `confirmed`. A raw append that hand-builds a `checks` list is held to
    this exactly as `record_verdict`'s own fold is (`godmode_verdict._fold_panel`
    can never itself produce it, but a raw append bypasses the fold, which is
    the whole reason this needs to be enforced here too).
    Tool-error-vs-ack (PARTIAL-P3/B3-7): a "confirmed" fold whose own
    `tool_error_findings` is non-empty (a checker's captured output matched
    a DECLARED tool error pattern - `godmode_verdict.record_verdict`
    computes and denormalises this at write time so it is checkable here
    from `data` alone, without this module needing archive access) needs a
    valid `tool_error_ack`. Empty `tool_error_findings` (the common case:
    no tool declared, or a declared tool's pattern never matched) costs
    this check nothing - it is skipped entirely.
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
    checks = data.get("checks") or []
    if any(isinstance(c, dict) and c.get("disposition") == "refuted" for c in checks):
        raise ArchiveError(
            "a 'confirmed' fold cannot carry a 'checks' entry that came back "
            "'refuted'; a panel with any refuting check is 'contested' at "
            "best, never 'confirmed' - this combination is refused outright"
        )
    if data.get("tool_error_findings"):
        ack = data.get("tool_error_ack")
        # Fix-round-1 (review M1): stripped before matching, same reasoning
        # as `godmode_verdict.record_verdict`'s own copy of this check - a
        # whitespace-only "reason" must refuse here too, for a raw append
        # that never went through record_verdict's own stripping.
        if not (isinstance(ack, str) and _TOOL_ERROR_ACK.match(ack.strip())):
            raise ArchiveError(
                "a 'confirmed' verdict whose checker output matched a "
                "declared tool error pattern needs tool_error_ack="
                "'acknowledged-remediated' or 'acknowledged-deferred: "
                "<reason>' - a raw append is held to the same rule "
                "record_verdict enforces"
            )


# U-V2's register/evidence vocabulary, read from `godmode_constants` - the
# one module with no runtime imports, so taking it from there keeps this
# module dependency-free for `godmode_chronicle` while avoiding the
# invariants -> register -> chronicle cycle a direct import would close.
# Two hand-synced copies with a test asserting they still agreed came
# before this; one definition makes the drift unrepresentable instead.
_REGISTER_STATES = REGISTER_STATES
_REGISTER_EVIDENCE_PREFIXES = REGISTER_EVIDENCE_PREFIXES


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


# B3-1's paired-verdict rule, checkable from `data` alone. Kept in sync with
# godmode_upstream.DISPOSITIONS / BEHAVIOR_VERDICTS by hand, not by import -
# same convention as _REGISTER_STATES above: this module stays dependency-
# free with respect to every kind-owning module, not only the ones that
# would actually cycle back through godmode_chronicle, so the guarantee
# never depends on which kind-owning module happens to have been written
# first. tests/test_upstream.py asserts the two tuples still agree.
_UPSTREAM_DISPOSITIONS = ("adopt", "extend", "diverge-deliberately", "n/a-different-surface")
_UPSTREAM_BEHAVIOR_VERDICTS = ("confirmed-we-have-it", "confirmed-we-dont", "unverified")


def _upstream_diff_invariants(data: dict[str, Any]) -> None:
    """B3-1: a `finding` that carries a `disposition` (the import verdict -
    can this upstream symbol be reused as-is) must also carry a
    `behavior_verdict` (the separately-required second verdict - does the
    defect/capability this symbol implies also exist in our own independent
    implementation). `n/a-different-surface` on the import question can
    never stand in for the behavior answer, so it is held to this exactly
    like every other disposition - see godmode_upstream.py's module
    docstring for the full two-verdict contract this protects.

    `godmode_upstream.record_upstream_diff` already refuses this before
    ever calling `Chronicle.append`; this is the same defense-in-depth
    `_register_invariants` and `_pin_invariants` above apply to their own
    kinds, so a raw append cannot bypass what the owning function enforces.
    A finding with `disposition: None` (undecided, not yet reviewed) passes
    through unexamined - only a disposition that was actually SET incurs the
    requirement.
    """
    findings = data.get("findings")
    if not isinstance(findings, list):
        return
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        disposition = finding.get("disposition")
        if disposition is None:
            continue
        if disposition not in _UPSTREAM_DISPOSITIONS:
            raise ArchiveError(
                f"Unknown upstream-diff disposition {disposition!r}; expected "
                f"one of {_UPSTREAM_DISPOSITIONS}"
            )
        behavior_verdict = finding.get("behavior_verdict")
        if behavior_verdict is None:
            raise ArchiveError(
                "An upstream-diff finding cannot carry a disposition with no "
                "behavior_verdict; 'n/a' on the import question can never "
                "stand in for the behavior answer - refused"
            )
        if behavior_verdict not in _UPSTREAM_BEHAVIOR_VERDICTS:
            raise ArchiveError(
                f"Unknown upstream-diff behavior_verdict {behavior_verdict!r}; "
                f"expected one of {_UPSTREAM_BEHAVIOR_VERDICTS}"
            )


def _pin_invariants(data: dict[str, Any]) -> None:
    """U-B2's protected-evaluator pins - the archived sha256 IS the security
    property this whole mechanism rests on. A pin record with no valid digest
    would sit in the archive claiming to protect a file while enforcing
    nothing, and nothing downstream re-derives or re-checks the shape at read
    time - `pinned_evaluators()` trusts whatever a `pin`-kind record says, the
    same way `_register_invariants` above notes a raw append can otherwise
    bypass a fold that would have refused it.

    `action` distinguishes a pin from an unpin on the same evolving-history
    shape every other folded kind here uses (state carried by replaying
    records, not by mutating one in place). Only `pin` needs a digest; an
    `unpin` names what it released and nothing else.
    """
    action = data.get("action")
    if action not in ("pin", "unpin"):
        raise ArchiveError(
            "a pin-kind record must declare action 'pin' or 'unpin'"
        )
    path = data.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ArchiveError("a pin-kind record must name a non-empty path")
    if action == "unpin":
        return
    digest = data.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest.lower()
    ):
        raise ArchiveError(
            "a pin record must carry the sha256 digest of the pinned file; "
            "an archived pin with no valid hash enforces nothing while "
            "claiming to"
        )


def _action_invariants(data: dict[str, Any]) -> None:
    """CX-1: only the `hook-interception-proof` shape is checked here.

    `action` is the busiest kind in the archive - deletion-prechecks,
    license-checks, experiment cycles, pin/unpin all use it with entirely
    different `data` shapes, and this validator runs on every one of them.
    It refuses to become a second, drifting home for their invariants, so it
    recognises exactly one shape (`data["proof"] is True`, the marker
    `record_interception_proof` always sets) and is a no-op on everything
    else - which is every `action` record this codebase already writes.

    A malformed proof record - missing host, tool, or the nonce that ties it
    back to the probe that produced it - would sit in the archive claiming
    interception is provable while proving nothing, the same failure
    `_pin_invariants` above refuses for a pin with no digest. Refused here,
    at the same seam a raw `archive.append()` cannot route around.
    """
    if data.get("interrupted") is True:
        # B4-4: an interrupted-intent record is counts + hashes by CONTRACT,
        # enforced here at the seam a raw append cannot route around - a
        # free-text field smuggled into this shape would persist the very
        # content the record exists to avoid persisting.
        allowed = {"interrupted", "open_obligations", "staged_capabilities",
                   "plan_fence_active", "subject_hashes"}
        extras = sorted(set(data) - allowed)
        if extras:
            raise ArchiveError(
                f"an interrupted-intent record carries counts and hashes only; "
                f"unexpected fields: {extras}")
        for field in ("open_obligations", "staged_capabilities"):
            value = data.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ArchiveError(
                    f"interrupted-intent '{field}' must be a non-negative count")
        hashes = data.get("subject_hashes", [])
        if (not isinstance(hashes, list) or len(hashes) > 16
                or not all(isinstance(h, str)
                           and re.fullmatch(r"[0-9a-f]{16}", h)
                           for h in hashes)):
            raise ArchiveError(
                "interrupted-intent subject_hashes must be at most 16 "
                "16-hex-character digests")
        return
    if data.get("proof") is not True:
        return
    for field in ("host", "tool", "request_id"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ArchiveError(
                f"a hook-interception-proof record must carry a non-empty '{field}'; "
                "an archived proof with a blank field enforces nothing while "
                "claiming to"
            )
    # CX-5: enrichment fields are OPTIONAL (a pre-CX-5 minimal record must
    # still validate - see godmode_hookproof.py's own backward-compatibility
    # note) - so nothing here is required. When one IS present, though, its
    # SHAPE is checked, additively, alongside the CX-1 checks above rather
    # than replacing them: a proof claiming an `expiry`/`hook_version`/hash
    # that is not even a string proves nothing while claiming to, exactly
    # the same failure the three required fields above already refuse.
    for field in (
        "hook_version", "project_identity_hash", "trusted_hook_hash",
        "nonce_hash", "observed_decision", "expiry",
    ):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            raise ArchiveError(
                f"a hook-interception-proof record's '{field}', when present, must be "
                "a string"
            )
    if "host_acknowledgement" in data and data["host_acknowledgement"] is not None \
            and not isinstance(data["host_acknowledgement"], bool):
        raise ArchiveError(
            "a hook-interception-proof record's 'host_acknowledgement', when present, "
            "must be a boolean or null"
        )
    # Fix round 1, C1(b) (Critical): the reviewer's live repro minted a
    # record claiming `expiry: "9999-12-31T23:59:59+00:00"` - nothing
    # anywhere bounded how far into the future an `expiry` may plausibly
    # sit. Refused here, at append time, for the normal write path;
    # `godmode_hookproof._expiry_out_of_bounds` independently re-checks the
    # SAME ceiling at grading time, so a record that reaches disk some
    # other way still cannot grade above `DEGRADED`. Compared against
    # "now," not the record's own eventual `recorded_at` (which is not set
    # until AFTER this validator returns, inside `Chronicle._write_record`)
    # - the two are the same instant to within microseconds, so an honest
    # write's own `expiry` (computed moments earlier, from the same "now")
    # is never rejected by its own ceiling.
    if "expiry" in data and isinstance(data["expiry"], str) and data["expiry"]:
        try:
            expiry_dt = datetime.fromisoformat(data["expiry"])
        except ValueError as exc:
            raise ArchiveError(
                "a hook-interception-proof record's 'expiry' is not a valid "
                "ISO-8601 timestamp"
            ) from exc
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if (expiry_dt - now).total_seconds() > _PROOF_MAX_TTL_SECONDS:
            raise ArchiveError(
                "a hook-interception-proof record's 'expiry' may not be more than "
                f"{_PROOF_MAX_TTL_SECONDS}s from now; a far-future expiry "
                "(fix round 1, C1(b) - the reviewer's year-9999 repro) proves "
                "nothing while claiming permanence"
            )


# kind -> validator. Every entry here is enforced unconditionally the moment
# godmode_chronicle.py is imported - see KIND_INVARIANTS in that module,
# which is seeded from this dict at chronicle module load, not populated
# lazily by whichever kind-owning module happens to be imported.
KIND_VALIDATORS: dict[str, KindInvariant] = {
    "verdict": _verdict_invariants,
    "decision": _register_invariants,
    "pin": _pin_invariants,
    "upstream-diff": _upstream_diff_invariants,
    "action": _action_invariants,
}
