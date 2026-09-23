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

from .godmode_constants import (
    EVENT_KINDS,
    REGISTER_EVIDENCE_PREFIXES,
    REGISTER_STATES,
    checker_commands_match,
)
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
    # N-11 (final review S1): the witness/checker self-reference rule is
    # checked UNCONDITIONALLY, above the `disposition != "confirmed"` early
    # return below - `godmode_verdict.record_verdict` applies this same rule
    # unconditionally too, and for the same reason its own comment gives: an
    # unreadable witness of kind other than `file`/`seq` (a bare `cmd:`
    # witness, say) still folds to `witness-malformed`, never `confirmed`, so
    # gating this on "folded == confirmed" would silently let the
    # self-referential case through unrefused on a raw append. The other
    # rules below (`not_checked`, `criteria`) are correctly confirmed-only -
    # a non-confirmed verdict may legitimately carry both - so only this one
    # check moves above the gate.
    witness_ref = (data.get("witness") or {}).get("ref")
    if isinstance(witness_ref, str) and witness_ref and any(
        isinstance(check, dict) and isinstance(check.get("checker"), str)
        and checker_commands_match(check["checker"], witness_ref)
        for check in (data.get("checks") or [])
    ):
        raise ArchiveError(
            f"the witness cannot be the same command as a checker: {witness_ref!r} "
            "- a checker must recompute from data, not judge itself; a raw "
            "append is held to the same rule record_verdict enforces"
        )

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
    # N-11: the record is the single source of truth; these are the raw-append
    # copies of the three rules `godmode_verdict.record_verdict` enforces on the
    # normal path. Checkable from `data` alone because `_append_verdict`
    # denormalises `not_checked`/`criteria` and the witness ref into the record.
    if data.get("not_checked"):
        raise ArchiveError(
            "a 'confirmed' verdict cannot carry not_checked items: "
            + ", ".join(str(item) for item in data.get("not_checked") or [])
            + " - a raw append is held to the same rule record_verdict enforces"
        )
    criteria = data.get("criteria")
    # Re-review finding C: present-but-wrong-shaped (a list, a string) used
    # to skip the check entirely instead of being refused as malformed - the
    # CLI already type-checks `criteria` before this point, so only a raw
    # append can reach this, and it should not reach `confirmed` un-noticed.
    if criteria is not None and not isinstance(criteria, dict):
        raise ArchiveError(
            "a 'confirmed' verdict's criteria must be an object of name to "
            f"evidence, not a {type(criteria).__name__} - a raw append is "
            "held to the same rule record_verdict enforces"
        )
    if isinstance(criteria, dict):
        blank = [str(name) for name, evidence in criteria.items()
                 if not str(evidence).strip()]
        if blank:
            raise ArchiveError(
                "a 'confirmed' verdict criterion needs non-empty evidence: "
                + ", ".join(blank)
                + " - a raw append is held to the same rule record_verdict enforces"
            )
    # (the witness/checker self-reference rule now lives above the
    # `disposition != "confirmed"` early return - see final review S1.)


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


# NS-11c: the semantic layer's ontology for a `decision` - subject, value,
# evidence - checked the same way `_register_invariants` above already
# checks a register-shaped one: from `data` alone, because `Chronicle.
# append()` calls a kind's validator with `data` only, never the separate
# `evidence=` argument it also stores (see that function's own docstring).
#
# This CANNOT be a blanket rule on every `decision` record without
# rewriting roughly twenty existing call sites across this codebase (leases,
# delegations, removals, register entries, parity observations, skill
# lifecycle, absorb verdicts, ...), each with its own bespoke `data` shape
# and its own already-established validation - and several of them are
# exercised by name in tests this sprint keeps green with no evidence at
# all (`tests/test_writer_trust.py`, `tests/test_supersession.py`: bare
# `remember --kind decision --subject s --value v` and
# `archive.append("decision", "d", {"value": "v1"})` with no `--evidence`,
# asserting `code == 0`). A mandatory, unconditional evidence requirement
# would refuse both.
#
# So this is declared-contract, exactly the way `register_key` gates the
# check above: a decision only enters the new ontology by declaring its own
# semantic `data["subject"]`, distinct from the record's own label subject,
# which is often a compound/prefixed key like `"removal:foo"` or
# `"skill-created:bar"`. No writer in this tree sets that key today, so
# this cannot regress a single one of them; any future write that wants the
# memory contract's semantic-fact shape opts in by setting it, and gets
# refused with a named remedy the moment it does so incompletely.
#
# Fix round 1, M1 - what this comment used to claim, and no longer does:
# that the label subject is "unsuitable for the contradiction-detection
# grouping NS-11e/Task 7 needs". Task 7 has since landed and
# `godmode_forget._flag_contradictions` groups by exactly that label
# subject. The honest statement of where this stands: the opt-in key has no
# writer, so the ontology is unreached rather than bypassable, and the
# consumer this comment named consumes the other subject. Deciding whether
# it becomes mandatory (behind a compatibility shim for the ~20 existing
# writers) or is dropped is carried to 0.3.29; nothing here should be read
# as a claim that another module is already using it.
_SEMANTIC_DECISION_FIELDS = ("subject", "value", "evidence")


def _semantic_decision_invariants(data: dict[str, Any]) -> None:
    if "subject" not in data:
        return
    missing = [field for field in _SEMANTIC_DECISION_FIELDS if not data.get(field)]
    if missing:
        raise ArchiveError(
            "A semantic decision (data['subject'] present) must carry "
            "subject, value and evidence, all non-empty (NS-11c); missing: "
            + ", ".join(missing)
            + " - remedy: supply every field, e.g. "
              "data={'subject': '<the fact this is about>', "
              "'value': '<what is true>', 'evidence': ['seq:<n>']}, or "
              "drop data['subject'] entirely for a decision that predates "
              "this contract"
        )


def _decision_invariants(data: dict[str, Any]) -> None:
    """Dispatcher for the `decision` kind: register-shaped records keep
    `_register_invariants`'s existing rule unchanged; every decision (
    register-shaped or not) also passes through the NS-11c semantic-fact
    check, which is a no-op unless the record opts in (see above)."""
    _register_invariants(data)
    _semantic_decision_invariants(data)


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


def _lesson_invariants(data: dict[str, Any]) -> None:
    """I-1 (0.3.28 Plan 5 Task 4): a lesson's `enforce` field, when present,
    must already be the parsed `{kind, predicate}` shape - never a raw
    `--enforce` string that slipped past `godmode_law.parse_enforce_spec`.
    Re-validates `predicate` against the same grammar `parse_enforce_spec`
    checks (same defense-in-depth this module applies to every other kind):
    a malformed predicate is refused here too, regardless of whether it
    arrived through `remember --enforce` or a raw `Chronicle.append` call
    that built the dict by hand.
    """
    enforce = data.get("enforce")
    if enforce is None:
        return
    if not isinstance(enforce, dict):
        raise ArchiveError("a lesson's 'enforce' field must be a {kind, predicate} mapping")
    kind = enforce.get("kind")
    predicate = enforce.get("predicate")
    if not isinstance(kind, str) or not kind or kind not in EVENT_KINDS:
        raise ArchiveError(
            f"a lesson's enforce.kind {kind!r} is not a recognised record kind")
    from .godmode_law import ENFORCE_FORBIDDEN_KINDS
    if kind in ENFORCE_FORBIDDEN_KINDS:
        # I-1 fix round 1 (Blocking 3): same defence-in-depth this module
        # already applies to the predicate grammar below - a raw
        # `Chronicle.append` that built the dict by hand, bypassing
        # `godmode_law.parse_enforce_spec`, is refused here too.
        raise ArchiveError(
            f"a lesson's enforce.kind {kind!r} is refused: it is the gate's "
            "own audit trail, written by hooks - see godmode_law."
            "ENFORCE_FORBIDDEN_KINDS")
    if not isinstance(predicate, str) or not predicate.strip():
        raise ArchiveError("a lesson's enforce.predicate must be a non-empty string")
    from .godmode_law import parse_enforce_predicate
    parse_enforce_predicate(predicate)


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


def _pattern_invariants(data: dict[str, Any]) -> None:
    """NS-12e: a `pattern` record with no class or no occurrence enforces
    nothing while claiming to track a recurring failure - the same
    defense-in-depth `_pin_invariants` above applies to a pin with no
    digest, held here against a raw append that bypasses
    `godmode_mistakes.record_pattern`'s own checks.

    `class` is checked for PRESENCE only, not membership in
    `godmode_mistakes.FAILURE_CLASSES` - that table lives in a module which
    imports `godmode_chronicle`, and this module stays dependency-free of
    every archive-owning module (see the module docstring above), so a full
    membership check has to live at `record_pattern`'s own layer instead;
    this is the structural half only, the same split `_register_invariants`
    draws between "a state is present" (checked here) and "the state is
    legal for this transition" (checked by the owning module).
    """
    pattern_class = data.get("class")
    if not isinstance(pattern_class, str) or not pattern_class.strip():
        raise ArchiveError(
            "a pattern record must carry a non-empty 'class' - an unclassed "
            "recurring failure cannot be rolled up or matched against a "
            "preflight finding's own class"
        )
    occurrences = data.get("occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        raise ArchiveError(
            "a pattern record must carry at least one entry in "
            "'occurrences' - a pattern with none is a claim with nothing "
            "behind it"
        )
    if any(not isinstance(o, int) or isinstance(o, bool) or o <= 0 for o in occurrences):
        raise ArchiveError(
            "a pattern record's 'occurrences' must be positive sequence numbers"
        )


def _improvement_proposal_invariants(data: dict[str, Any]) -> None:
    """NS-4 (0.3.28 Plan 5 Task 3): an `improvement_proposal` with no target,
    no diff, no citation, or no named actor enforces nothing while claiming
    to propose a change - the same defense-in-depth `_pattern_invariants`
    above applies to a pattern with no occurrence, held here against a raw
    append that bypasses `godmode_bonds.propose`'s own checks.
    """
    target = data.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ArchiveError(
            "an improvement_proposal must carry a non-empty 'target' - a "
            "proposal naming nothing cannot be ratified against anything"
        )
    digest = data.get("diff_hash")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest.lower()
    ):
        raise ArchiveError(
            "an improvement_proposal must carry the sha256 digest of the "
            "diff it proposes; an archived proposal with no valid hash "
            "enforces nothing while claiming to"
        )
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ArchiveError(
            "an improvement_proposal must carry at least one citation in "
            "'evidence' - an unevidenced proposal is a request, not a claim"
        )
    actor = data.get("actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ArchiveError(
            "an improvement_proposal must carry a non-empty 'actor' - "
            "ratify's proposer/checker separateness compares actor "
            "fingerprints, and cannot compare against a missing one"
        )


def _checker_bond_invariants(data: dict[str, Any]) -> None:
    """NS-4: a `checker_bond` with no session, no actor, no target, no
    bad-case hash, or a non-boolean `failed_as_expected` enforces nothing
    while claiming to prove a checker can fail - `ratify` reads
    `failed_as_expected` as a trilean-shaped fact (a rubber stamp reads
    exactly like a missing bond otherwise), so it is checked here, not
    merely at the console seam.

    Fix round 1 (S6): `target` is required too - the file the bond's
    planted bad case actually broke, so `ratify` can bind a bond to the
    SAME file its proposal names, never a throwaway fixture with nothing
    to do with the proposal under review.
    """
    for field in ("actor", "target", "bad_case_hash"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ArchiveError(
                f"a checker_bond must carry a non-empty '{field}' - an "
                "archived bond with a blank field proves nothing while "
                "claiming to"
            )
    if "session" not in data or not isinstance(data.get("session"), str):
        raise ArchiveError(
            "a checker_bond must carry its 'session' (the GODMODE_SESSION "
            "identity it ran under) as a string, even when empty - ratify "
            "matches a bond to a session by this field"
        )
    if not isinstance(data.get("failed_as_expected"), bool):
        raise ArchiveError(
            "a checker_bond's 'failed_as_expected' must be a real boolean - "
            "a truthy non-boolean (e.g. the string \"true\") would let a "
            "rubber-stamped bond read as passing"
        )


def _improvement_verdict_invariants(data: dict[str, Any]) -> None:
    """NS-4: an `improvement_verdict` is valid only chained after a real
    proposal and a real bond - `proposal_seq`/`bond_seq` must be positive
    sequence numbers (never a placeholder like 0 or -1), `actor` must name
    who ratified, and today's only legal `verdict` is "ratified" (a refusal
    never reaches the archive at all - see `godmode_bonds.ratify`).
    """
    actor = data.get("actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ArchiveError(
            "an improvement_verdict must carry a non-empty 'actor'"
        )
    for field in ("proposal_seq", "bond_seq"):
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ArchiveError(
                f"an improvement_verdict's '{field}' must be a positive "
                "sequence number"
            )
    if data.get("verdict") != "ratified":
        raise ArchiveError(
            "an improvement_verdict's 'verdict' must be \"ratified\" - a "
            "refused ratification is never archived (godmode_bonds.ratify "
            "raises instead of writing a record)"
        )


def _lesson_promotion_invariants(data: dict[str, Any]) -> None:
    """NS-2 (0.3.28 Plan 5 Task 2): a `lesson_promotion` with no lesson_seq,
    no actor, no citation, or no rerun_hash enforces nothing while claiming
    to promote a structured lesson - the same defense-in-depth
    `_improvement_proposal_invariants` above applies to a proposal with a
    blank field, held here against a raw append that bypasses
    `godmode_lessons.promote`'s own checks. `law compile`'s chained-approval
    rule (`approval.actor != promotion.actor`, `approval.rerun_hash !=
    promotion.rerun_hash`) cannot compare against a missing field.
    """
    lesson_seq = data.get("lesson_seq")
    if not isinstance(lesson_seq, int) or isinstance(lesson_seq, bool) or lesson_seq <= 0:
        raise ArchiveError(
            "a lesson_promotion's 'lesson_seq' must be a positive sequence number"
        )
    actor = data.get("actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ArchiveError("a lesson_promotion must carry a non-empty 'actor'")
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ArchiveError(
            "a lesson_promotion must carry at least one citation in "
            "'evidence' - an unevidenced promotion is a request, not a claim"
        )
    rerun_hash = data.get("rerun_hash")
    if not isinstance(rerun_hash, str) or not _SHA256_HEX.match(rerun_hash.lower()):
        raise ArchiveError(
            "a lesson_promotion's 'rerun_hash' must be a sha256 hex digest - "
            "the independent re-run's own evidence fingerprint, not a label"
        )


def _lesson_approval_invariants(data: dict[str, Any]) -> None:
    """NS-2: a `lesson_approval` with no promotion_seq, no actor, or no
    rerun_hash enforces nothing while claiming to approve a promotion -
    same defense-in-depth as `_lesson_promotion_invariants` above.
    """
    promotion_seq = data.get("promotion_seq")
    if not isinstance(promotion_seq, int) or isinstance(promotion_seq, bool) or promotion_seq <= 0:
        raise ArchiveError(
            "a lesson_approval's 'promotion_seq' must be a positive sequence number"
        )
    actor = data.get("actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ArchiveError("a lesson_approval must carry a non-empty 'actor'")
    rerun_hash = data.get("rerun_hash")
    if not isinstance(rerun_hash, str) or not _SHA256_HEX.match(rerun_hash.lower()):
        raise ArchiveError(
            "a lesson_approval's 'rerun_hash' must be a sha256 hex digest"
        )


def _lesson_candidate_invariants(data: dict[str, Any]) -> None:
    """NS-2: the candidate shelf note (`godmode_law.
    shelve_oldest_candidates`) - a note with no shelved sequence or no
    reason enforces nothing while claiming one of the live candidates was
    taken out of the live set.
    """
    archived = data.get("archived_seqs")
    if not isinstance(archived, list) or not archived:
        raise ArchiveError(
            "a lesson_candidate note must carry at least one entry in "
            "'archived_seqs'"
        )
    if any(not isinstance(s, int) or isinstance(s, bool) or s <= 0 for s in archived):
        raise ArchiveError(
            "a lesson_candidate note's 'archived_seqs' must be positive "
            "sequence numbers"
        )
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ArchiveError("a lesson_candidate note must carry a non-empty 'reason'")


def _hypothesis_invariants(data: dict[str, Any]) -> None:
    """NS-13f: a `hypothesis` names its cause and a kill experiment, and its
    status agrees with what that experiment did - `killed` only when it ran
    and fired, `survived` only when it ran and did not. Held here as well as
    in `godmode_hypothesis` so a raw append cannot mint a survivor a fix
    could then cite.
    """
    if not isinstance(data.get("cause"), str) or not data["cause"].strip():
        raise ArchiveError("a hypothesis must carry a non-empty 'cause'")
    kills = data.get("kills")
    if not (isinstance(kills, dict) and isinstance(kills.get("command"), str)
            and kills["command"].strip()):
        raise ArchiveError("a hypothesis must carry 'kills' with the experiment's 'command'")
    ran, fired = kills.get("ran"), kills.get("fired")
    if not isinstance(ran, bool) or not isinstance(fired, bool):
        raise ArchiveError("a hypothesis's kills.ran and kills.fired must be booleans")
    status = data.get("status")
    if status not in ("open", "killed", "survived"):
        raise ArchiveError("a hypothesis's 'status' must be open, killed or survived")
    if fired and not ran:
        raise ArchiveError("a kill experiment cannot fire without running")
    # A run leaves a record: `ran` names the runner's attestation and the
    # citation it wrote, and a hypothesis that never ran names none. The
    # reader (`godmode_hypothesis.fix_citation_refusal`) loads that record.
    check_seq, citation = kills.get("check_seq"), kills.get("citation")
    if ran:
        if (not isinstance(check_seq, int) or isinstance(check_seq, bool) or check_seq <= 0
                or not isinstance(citation, str) or not citation.startswith("cmd:")):
            raise ArchiveError(
                "a hypothesis whose kill experiment ran must name the run: kills.check_seq "
                "(the runner's attestation) and kills.citation (its cmd: citation)")
    elif check_seq is not None or citation is not None:
        raise ArchiveError("a kill experiment that has not run names no check_seq or citation")
    expected = "killed" if ran and fired else "survived" if ran else "open"
    if status != expected:
        raise ArchiveError(
            f"a hypothesis whose kill experiment has ran={ran}, fired={fired} is "
            f"{expected}, not {status}")
    confirms = data.get("confirms", [])
    if not isinstance(confirms, list) or any(not isinstance(c, str) for c in confirms):
        raise ArchiveError("a hypothesis's 'confirms' must be a list of citations")


def _skill_impact_invariants(data: dict[str, Any]) -> None:
    """NS-12a + NS-12d (0.3.28 Plan 5 Task 9): a `skill_impact` with no
    target, no valid diff digest, a non-numeric score, or an outcome
    outside {accepted, rejected} enforces nothing while claiming the
    strict-improvement gate ran - the same defense-in-depth every other
    NS-4/NS-12 kind above holds against a raw append bypassing
    `godmode_skillimpact.record_impact`'s own checks.
    """
    target = data.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ArchiveError(
            "a skill_impact must carry a non-empty 'target' - an impact "
            "naming nothing cannot be compared against anything later"
        )
    digest = data.get("diff_hash")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest.lower()
    ):
        raise ArchiveError(
            "a skill_impact must carry the sha256 digest of the change it "
            "scored, in 'diff_hash'"
        )
    for field in ("score_before", "score_after"):
        value = data.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ArchiveError(
                f"a skill_impact's '{field}' must be a real number - the "
                "strict-improvement gate compares these directly"
            )
    if data.get("outcome") not in ("accepted", "rejected"):
        raise ArchiveError(
            "a skill_impact's 'outcome' must be \"accepted\" or \"rejected\" "
            "- NS-12d's gate has no third state (neutral folds into "
            "rejected)"
        )
    patterns = data.get("patterns", [])
    if not isinstance(patterns, list) or any(
        not isinstance(p, int) or isinstance(p, bool) or p <= 0 for p in patterns
    ):
        raise ArchiveError(
            "a skill_impact's 'patterns' must be a list of positive "
            "sequence numbers (it may be empty)"
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


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

# NS-1 (0.3.28 Plan 5 Task 1): the named halt reasons a `loop_halt` record
# may carry. Hand-copied, not imported, from
# `godmode_looprecords.py` - this module stays dependency-free of every
# archive-owning module on purpose (see the module docstring above), the
# same discipline `_PROOF_MAX_TTL_SECONDS`/`_TOOL_ERROR_ACK` above already
# follow for their own owning modules' copies.
# `tests/test_atlas_loop.py` asserts the two sets stay equal.
_LOOP_BUDGET_NAMES = ("steps", "tokens", "wall_time")
_LOOP_HALT_REASON_INTERRUPTED = "operator-interrupted"
_LOOP_HALT_REASON_SIGNATURE_REPEATED = "loop-signature-repeated"
LOOP_HALT_REASONS = frozenset(
    {f"{name}-exhausted" for name in _LOOP_BUDGET_NAMES}
    | {_LOOP_HALT_REASON_INTERRUPTED, _LOOP_HALT_REASON_SIGNATURE_REPEATED}
)


def _loop_step_invariants(data: dict[str, Any]) -> None:
    """NS-1: a `loop_step` record with no task, no positive attempt number,
    no sha256-shaped signature, or a malformed budget enforces nothing
    while claiming to gate a retry - the same defense-in-depth
    `_pattern_invariants` above applies to a pattern with no occurrence,
    held here against a raw append that bypasses
    `godmode_looprecords.advance`'s own checks.
    """
    task = data.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ArchiveError("a loop_step record must carry a non-empty 'task'")
    attempt_n = data.get("attempt_n")
    if not isinstance(attempt_n, int) or isinstance(attempt_n, bool) or attempt_n < 1:
        raise ArchiveError("a loop_step record's 'attempt_n' must be a positive integer")
    signature_hash = data.get("failure_signature_hash")
    if not isinstance(signature_hash, str) or not _SHA256_HEX.match(signature_hash.lower()):
        raise ArchiveError(
            "a loop_step record's 'failure_signature_hash' must be a sha256 hex digest"
        )
    budget = data.get("budget_remaining")
    if not isinstance(budget, dict) or set(budget) != set(_LOOP_BUDGET_NAMES):
        raise ArchiveError(
            "a loop_step record's 'budget_remaining' must carry exactly "
            f"{sorted(_LOOP_BUDGET_NAMES)}"
        )
    for name, value in budget.items():
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ArchiveError(
                f"a loop_step record's budget_remaining.{name} must be a "
                "non-negative integer or null (null means no ceiling declared)"
            )


def _loop_halt_invariants(data: dict[str, Any]) -> None:
    """NS-1: a `loop_halt` record's 'reason' must be one this runtime
    actually names, and its 'signatures' must match what that reason
    implies - three identical sha256 digests for a repeated-signature
    halt (the whole point of the record), none at all for a budget halt
    (no signature was ever computed before a budget exhaustion halts, per
    the checked-before-the-signature-test ordering)."""
    task = data.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ArchiveError("a loop_halt record must carry a non-empty 'task'")
    reason = data.get("reason")
    if not isinstance(reason, str) or reason not in LOOP_HALT_REASONS:
        raise ArchiveError(
            f"a loop_halt record's 'reason' must be one of {sorted(LOOP_HALT_REASONS)}"
        )
    signatures = data.get("signatures")
    if not isinstance(signatures, list) or any(not isinstance(s, str) for s in signatures):
        raise ArchiveError("a loop_halt record's 'signatures' must be a list of strings")
    if reason == _LOOP_HALT_REASON_SIGNATURE_REPEATED:
        if len(signatures) != 3 or len(set(signatures)) != 1:
            raise ArchiveError(
                "a loop-signature-repeated halt must carry exactly three "
                "identical signatures - that repetition is the halt's own evidence"
            )
        if not all(_SHA256_HEX.match(s.lower()) for s in signatures):
            raise ArchiveError("a loop_halt record's signatures must be sha256 hex digests")
    elif signatures:
        raise ArchiveError(
            f"a '{reason}' halt must carry no signatures - none was computed "
            "before a budget/interruption halt fires"
        )


# NS-11e fix round 1 (review B, B4): the closed status vocabulary for a
# `review` record. Kept here, beside the validator that enforces it, and
# re-exported through `godmode_forget` for the pass that writes them;
# `godmode_chronicle.REVIEW_CLOSING_STATUSES` is the subset the
# single-writer close guard treats as a closure.
REVIEW_STATUSES = frozenset({"open", "acknowledged", "dismissed"})


def _review_invariants(data: dict[str, Any]) -> None:
    """NS-11e (0.3.28 Plan 5 Task 7): `godmode forget`'s contradiction pass
    writes a `review` record naming which two (or more) active records on
    one subject disagree - never which one is right, only that both are
    still standing. A `review` with fewer than two sequences, or with a
    named kind that is not itself a real record kind, enforces nothing
    while claiming to flag a contradiction - the same defense-in-depth
    `_pattern_invariants` above applies to a pattern with no occurrence,
    held here against a raw append that bypasses `godmode_forget`'s own
    checks.

    Membership of `kind` against the live `EVENT_KINDS` set is NOT checked
    here - that table lives in `godmode_constants`, which this
    dependency-free module does not import (see the module docstring) -
    the full closed-vocabulary check is `godmode_forget`'s own layer, the
    same split `_pattern_invariants` draws for its own `class` field.

    Fix round 1 (review B, B4): `status` is required, and closed to
    `open` / `acknowledged` / `dismissed`. A flagged contradiction an
    operator has deliberately accepted (`acknowledged`) or judged not to be
    one (`dismissed`) must be able to STAY that way - without a status
    vocabulary there was no way to say so durably, and the next pass simply
    filed the same finding again. The two closing values go through the
    chronicle's single-writer close guard
    (`godmode_chronicle.REVIEW_CLOSING_STATUSES`), so closing a review is
    the deliberate act closing anything else in the archive is.
    """
    sequences = data.get("sequences")
    if not isinstance(sequences, list) or len(sequences) < 2:
        raise ArchiveError(
            "a review record must name at least two conflicting sequences - "
            "one alone is not a contradiction"
        )
    if any(not isinstance(s, int) or isinstance(s, bool) or s <= 0 for s in sequences):
        raise ArchiveError("a review record's 'sequences' must be positive sequence numbers")
    if len(set(sequences)) != len(sequences):
        raise ArchiveError("a review record's 'sequences' must not repeat the same sequence")
    kind = data.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ArchiveError(
            "a review record must carry a non-empty 'kind' - which record "
            "kind the conflicting sequences belong to"
        )
    status = data.get("status")
    if not isinstance(status, str) or status.strip().lower() not in REVIEW_STATUSES:
        raise ArchiveError(
            "a review record's 'status' must be one of "
            f"{', '.join(sorted(REVIEW_STATUSES))} - an unresolved finding is "
            "'open', one the operator accepts is 'acknowledged', one that is "
            "not a real contradiction is 'dismissed'"
        )


# kind -> validator. Every entry here is enforced unconditionally the moment
# godmode_chronicle.py is imported - see KIND_INVARIANTS in that module,
# which is seeded from this dict at chronicle module load, not populated
# lazily by whichever kind-owning module happens to be imported.
KIND_VALIDATORS: dict[str, KindInvariant] = {
    "verdict": _verdict_invariants,
    "decision": _decision_invariants,
    "pin": _pin_invariants,
    "upstream-diff": _upstream_diff_invariants,
    "action": _action_invariants,
    "pattern": _pattern_invariants,
    "loop_step": _loop_step_invariants,
    "loop_halt": _loop_halt_invariants,
    "improvement_proposal": _improvement_proposal_invariants,
    "checker_bond": _checker_bond_invariants,
    "improvement_verdict": _improvement_verdict_invariants,
    "lesson": _lesson_invariants,
    "review": _review_invariants,
    "lesson_promotion": _lesson_promotion_invariants,
    "lesson_approval": _lesson_approval_invariants,
    "lesson_candidate": _lesson_candidate_invariants,
    "skill_impact": _skill_impact_invariants,
    "hypothesis": _hypothesis_invariants,
}
