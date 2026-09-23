"""NS-4 (0.3.28 Plan 5 Task 3): falsification bonds gate `atlas law ratify`.

The falsification bond: a checker's pass counts only after it has, in the
SAME session, correctly failed on an injected guaranteed-bad artifact.
`plant` already proves a guard fails when broken (green -> red -> green);
this module reuses that exact machinery (`godmode_attest.plant_and_observe`)
rather than re-implementing it, and generalises the proof from "a guard can
fail" to "the checker running right now can fail".

Three record kinds, three verbs:

- `atlas law propose --target <path> --diff <file> --cite ...` writes an
  `improvement_proposal` naming what changed, a hash of the diff, and the
  proposer's own actor fingerprint (`godmode_constants.agent_id()` - the
  SAME identity `Chronicle.append` stamps as `record["agent"]["agent_id"]`
  and the single-writer guard already compares by). Capped at
  `MAX_PROPOSALS_PER_SPRINT` OPEN proposals - a quality filter (cite your
  evidence, don't spam proposals), never a truncation of any proposal's own
  text. Only `ratify` frees a slot; nothing withdraws a proposal today.
- `atlas law bond-test` plants a synthetic bad case (the exact `--command`
  /`--file`/`--replace`|`--append` shape `plant` already takes) and records
  a `checker_bond`: `failed_as_expected` is true only when the planted
  violation was actually observed failing (the full green -> red -> green
  sequence `plant_and_observe` proves, never a bare "command exited
  nonzero" that a permanently-broken check would also produce).
- `atlas law ratify <proposal-seq>` is refused (never silently downgraded)
  when: the caller's own current session is not an operator-granted
  `checker` session belonging to the caller's own `agent_id()` (fix round
  1, B1 - `Chronicle.chronicled_session_role()`, a public wrapper over
  `_chronicled_session_role`, the SAME derivation `Chronicle.append` uses
  for `writer`, never reimplemented here); no bond in that exact session
  was itself both written by that same actor and sealed `writer ==
  "checker"`; the bond that did run targeted a different file than the
  proposal (fix round 1, S6); the bond that did run did not fail as
  expected (a rubber stamp); every bond that did fail as expected there
  already ratified a different proposal (fix round 1, S4 - one bond, one
  verdict); the proposal already has a verdict (fix round 1, N5); or the
  proposal's own `actor` equals the ratifying caller's own `agent_id()` -
  compared as FINGERPRINTS, never as role labels, so a proposer who also
  holds an operator-granted checker session still cannot ratify their own
  proposal.

Session identity for all of this is `GODMODE_SESSION` read directly (never
`godmode_console._session`'s `latest_session()` fallback, which answers a
different question - "which session's records should this label carry" -
and could name a session this process never actually opened). This is the
one env var `Chronicle._chronicled_session_role` itself trusts. A bond's
stored `session` string alone is not enough to borrow it, though (fix
round 1, B1): the bond's own `actor` must also equal the ratifying
caller's `agent_id()`, so naming a session id someone else's grant opened -
the id is not a secret and the grant never expires, per
`_chronicled_session_role`'s own docstring - no longer lets a third party
ratify with it.

With `GODMODE_AGENT_ID` undeclared, every process in the project shares one
default fingerprint (`godmode_constants.agent_id()`), so `proposal.actor ==
agent_id()` is trivially true for every caller and `ratify` can never
succeed until distinct per-agent ids are declared - the same condition
Task 5's own checker-session grant is inert under.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .godmode_attest import plant_and_observe
from .godmode_chronicle import Chronicle, record_writer
from .godmode_constants import agent_id
from .godmode_errors import ArchiveError
from .godmode_skillimpact import (
    apply_skill_diff,
    canonical_skill_target,
    diff_hash_of,
    refuse_if_diff_previously_rejected,
    skill_name_from_target,
)

# A fixed bullet cap of 12 is a quality filter here, never a truncation:
# the 13th proposal is refused outright, not accepted with its text cut
# short.
MAX_PROPOSALS_PER_SPRINT = 12


def proposals_this_sprint(archive: Chronicle) -> int:
    """How many `improvement_proposal` records count against the running
    cap: proposals still OPEN, i.e. with no `improvement_verdict` citing
    their own sequence as `proposal_seq` (fix round 1, B2).

    NOT scoped by the `sprint` kind - that kind is `godmode sprint`'s and
    `godmode status set`'s shared per-work-item state record, not a sprint
    boundary; every ordinary `status set` write appends one, so counting
    proposals "since the last `sprint` record" reset on every unrelated
    status change and the cap never accumulated in practice. Counting open
    proposals instead is what the cap's own refusal message now promises,
    and only that: a ratified proposal frees the slot it held, and nothing
    else does. There is no "rejected" verdict value
    (`_improvement_verdict_invariants` accepts only "ratified") and no verb
    that withdraws or retires an open proposal, so "unratified" and "open"
    coincide, and a project that fills the cap without a second agent to
    ratify has no way back under the cap. Adding a withdrawal path is a
    later design call, not a wording one - until it exists, the refusal
    says only what is true.
    """
    ratified_seqs = {
        (record.get("data") or {}).get("proposal_seq")
        for record in archive.read_events(verify=False)
        if record.get("kind") == "improvement_verdict"
    }
    return sum(
        1
        for record in archive.read_events(verify=False)
        if record.get("kind") == "improvement_proposal"
        and record["sequence"] not in ratified_seqs
    )


def _current_session() -> str:
    session = os.environ.get("GODMODE_SESSION", "").strip()
    if not session:
        raise ArchiveError(
            "No open session named by GODMODE_SESSION; run `session open` "
            "first (a checker verb needs `session open --role checker "
            "--as-operator` specifically)."
        )
    return session


def _record_by_sequence(archive: Chronicle, kind: str, sequence: int) -> dict[str, Any] | None:
    """Fix round 1, S5: `archive.select(kind=..., limit=2000)` reads as "scan
    everything" but `Chronicle.select` silently clamps any limit to 500
    (`godmode_chronicle.py`), so a proposal older than the most recent 500
    records of its kind resolved as "No improvement_proposal at sequence N"
    - a false refusal with a misleading message. `read_events` has no such
    clamp."""
    for record in archive.read_events(verify=False):
        if record.get("kind") == kind and record["sequence"] == sequence:
            return record
    return None


def propose(
    archive: Chronicle,
    target: str,
    diff_path: str | Path,
    cite: list[str],
    project: Path | None = None,
) -> dict[str, Any]:
    """`atlas law propose`: write an `improvement_proposal`.

    Refused (never truncated) at the sprint cap, and refused when no
    citation is given - an unevidenced proposal is a request, not a claim,
    the same bar `_register_invariants` already holds decisions to.
    """
    count = proposals_this_sprint(archive)
    if count >= MAX_PROPOSALS_PER_SPRINT:
        raise ArchiveError(
            f"{count}/{MAX_PROPOSALS_PER_SPRINT} improvement proposals are still "
            f"open (MAX_PROPOSALS_PER_SPRINT={MAX_PROPOSALS_PER_SPRINT}); this is a "
            "quality filter, not a truncation - the one thing that frees a slot "
            "today is `atlas law ratify <proposal-seq>`, which needs a second "
            "agent holding an operator-granted checker session and a bond for "
            "that proposal's own target. No verb withdraws an open proposal."
        )
    cite_list = list(cite or [])
    if not cite_list:
        raise ArchiveError(
            "`atlas law propose` needs at least one --cite; an unevidenced "
            "proposal is a request, not a claim"
        )
    diff_hash = diff_hash_of(diff_path)
    # NS-12a keys its refusal on `(diff_hash, target)`, and `ratify` keys
    # the record it writes on the CANONICAL spelling of the same target -
    # the one `_contained_skill_path` derives from the write itself. A
    # target stored here in whatever spelling the proposer typed would put
    # the two sides on different keys, which is all it takes to launder a
    # rejection: `skills\demo\x.py` and `skills/demo/x.py` are one file and
    # must be one key. With a project root in reach (the console always has
    # one) the fold is the full one the write itself uses, filename case
    # included; without one it is the string-only half - separators, `.`
    # components, doubled and trailing separators.
    target = canonical_skill_target(target, project)
    # A diff already tried and rejected (recorded as a `skill_impact` by a
    # prior `atlas law ratify` or `skill forge`) is refused here, at the
    # moment a re-proposal would otherwise re-litigate it - naming the
    # prior seq is `refuse_if_diff_previously_rejected`'s own contract.
    refuse_if_diff_previously_rejected(archive, diff_hash, target)
    actor = agent_id()
    data = {
        "target": target,
        "diff_hash": diff_hash,
        "evidence": cite_list,
        "actor": actor,
    }
    record = archive.append("improvement_proposal", target, data, evidence=cite_list)
    return {
        "sequence": record["sequence"],
        "target": target,
        "diff_hash": diff_hash,
        "actor": actor,
        "proposals_this_sprint": count + 1,
        "cap": MAX_PROPOSALS_PER_SPRINT,
    }


def bond_test(
    archive: Chronicle,
    project: Path,
    name: str,
    command: list[str],
    target: str,
    replace: str | None = None,
    with_text: str = "",
    append: str | None = None,
    rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    """`atlas law bond-test`: prove THIS session's checker can fail, by
    reusing `plant`'s own green -> red -> green machinery against a
    synthetic bad case, then recording the outcome as a `checker_bond`.

    Whether the resulting bond counts toward a ratification is decided
    entirely by `Chronicle.append`'s own writer derivation (`writer ==
    "checker"` only from a session `session open --role checker` actually
    granted, operator-verified, to THIS process's own agent id) - this
    function does not gate on role itself, so its outcome is honest even
    when run outside a checker session (it simply will not qualify).
    """
    session = _current_session()
    outcome = plant_and_observe(
        archive, session, project, name, command, target,
        replace=replace, with_text=with_text, append=append, rule_ids=rule_ids,
    )
    # Fix round 1, S6: the command is folded in too - two bonds proving
    # entirely different checkers must not hash identically - and `target`
    # is also carried as its own field (not just inside the hash) so
    # `ratify` can bind a bond to the SAME file the proposal names, never a
    # throwaway fixture with nothing to do with the proposal under review.
    bad_case_hash = hashlib.sha256(
        "|".join([" ".join(command), target, replace or "", with_text, append or ""]).encode("utf-8")
    ).hexdigest()
    actor = agent_id()
    record = archive.append(
        "checker_bond",
        f"bond:{name}",
        {
            "session": session,
            "actor": actor,
            "target": target,
            "bad_case_hash": bad_case_hash,
            "failed_as_expected": bool(outcome["observed_failing"]),
        },
        evidence=[f"seq:{outcome['record']}"],
    )
    return {
        "sequence": record["sequence"],
        "session": session,
        "actor": actor,
        "target": target,
        "bad_case_hash": bad_case_hash,
        "failed_as_expected": bool(outcome["observed_failing"]),
        "writer": record["writer"],
        "detail": outcome["detail"],
    }


def ratify(
    archive: Chronicle,
    proposal_seq: int,
    project: Path | None = None,
    diff_path: str | Path | None = None,
    patterns: list[int] | None = None,
) -> dict[str, Any]:
    """`atlas law ratify <proposal-seq>`: refused (never a downgrade) when
    the proposal already has a verdict; the caller's own current session is
    not an operator-granted checker session belonging to the caller
    (fix round 1, B1); no bond in that session was written by that same
    caller and sealed `writer == "checker"`; none of those bonds targeted
    the proposal's own file (fix round 1, S6); none that did failed as
    expected (rubber stamp); every bond that did fail as expected here has
    already ratified a different proposal (fix round 1, S4 - one bond, one
    verdict); or the proposer and the checker are the same actor.

    NS-12d (Task 9): when the proposal's own `target` is a
    `skills/<name>/...` path, ratifying it ALSO requires `project` and
    `diff_path` (the same diff `propose` hashed, re-verified against the
    proposal's own `diff_hash`) so the change can be applied and scored
    before the verdict is written. A change that does not strictly improve
    over the best recorded score for this target is refused: the target is
    restored to its pre-change bytes (`godmode_skillimpact.apply_skill_diff`
    - never the operator's own `git checkout`) and a `skill_impact` record
    stays with `outcome: "rejected"`; no `improvement_verdict` is written
    for it, the same "a refusal is never archived" contract every other
    ratify refusal here already keeps. A non-skill target (a law or guard
    proposal) is unaffected - the gate applies only when `target` resolves
    to a skill.
    """
    proposal = _record_by_sequence(archive, "improvement_proposal", proposal_seq)
    if proposal is None:
        raise ArchiveError(f"No improvement_proposal at sequence {proposal_seq}")
    proposal_target = (proposal.get("data") or {}).get("target")

    verdicts = [
        record for record in archive.read_events(verify=False)
        if record.get("kind") == "improvement_verdict"
    ]
    if any((v.get("data") or {}).get("proposal_seq") == proposal["sequence"] for v in verdicts):
        raise ArchiveError(
            f"Proposal {proposal_seq} already has an improvement_verdict; "
            "ratify is one verdict per proposal - propose a new change "
            "instead of ratifying the same proposal twice."
        )
    # Fix round 1, S4: a bond already cited by an earlier verdict's own
    # `bond_seq` cannot ratify a second time - "fresh" (the CLI's own help
    # text, `atlas law ratify`) means once per verdict, not once per
    # session.
    consumed_bond_seqs = {(v.get("data") or {}).get("bond_seq") for v in verdicts}

    session = _current_session()
    checker_actor = agent_id()
    # Fix round 1, B1: the caller must ITSELF currently hold an
    # operator-granted checker session under its own agent id - the exact
    # derivation `Chronicle.append` uses for `writer`, reused (never
    # reimplemented) through the public wrapper `chronicled_session_role`.
    if archive.chronicled_session_role() != "checker":
        raise ArchiveError(
            f"Session {session} is not an operator-granted checker session "
            f"for {checker_actor}: run `session open --role checker "
            "--as-operator` as this same agent (declare a distinct "
            "GODMODE_AGENT_ID per agent - with none declared, every process "
            "shares one fingerprint and ratify can never succeed) before "
            "`atlas law ratify`."
        )
    bonds = [
        record
        for record in archive.read_events(verify=False)
        if record.get("kind") == "checker_bond"
        and (record.get("data") or {}).get("session") == session
        # Fix round 1, B1: the bond's own `actor` must equal the ratifying
        # caller's own agent id - a session id alone is not a secret
        # (`godmode history --kind session --json` prints it, and the
        # grant never expires), so matching only the session string let a
        # third party who merely learned it borrow someone else's bond.
        and (record.get("data") or {}).get("actor") == checker_actor
        # Trust, not role label: a bond `session open --role checker`
        # never actually granted (no operator verification, or granted to
        # a different agent id) writes as `agent`/`hook` and cannot count -
        # exactly the same derivation `ratify`'s own separateness check
        # below relies on for "proposer == checker".
        and record_writer(record) == "checker"
    ]
    if not bonds:
        raise ArchiveError(
            f"No checker bond ran in session {session} by {checker_actor}; "
            "run `atlas law bond-test` first, from a session opened with "
            "`session open --role checker --as-operator` as this same "
            "agent (a bond from any other session or actor, or from a "
            "session without an operator-granted checker role, does not "
            "count)."
        )
    target_bonds = [
        bond for bond in bonds
        if (bond.get("data") or {}).get("target") == proposal_target
    ]
    if not target_bonds:
        raise ArchiveError(
            f"The checker bond(s) run in session {session} target a "
            f"different file than proposal {proposal_seq} names "
            f"({proposal_target!r}); run `atlas law bond-test` again with "
            "--file matching the proposal's own --target."
        )
    passing = [
        bond for bond in target_bonds
        if (bond.get("data") or {}).get("failed_as_expected") is True
    ]
    if not passing:
        raise ArchiveError(
            f"The checker bond(s) run in session {session} did not fail as "
            "expected (rubber stamp): a checker that cannot fail a planted "
            "bad case proves nothing about a real one. Fix the check, then "
            "run `atlas law bond-test` again in this session."
        )
    fresh = [bond for bond in passing if bond["sequence"] not in consumed_bond_seqs]
    if not fresh:
        raise ArchiveError(
            f"No fresh, passing checker bond in session {session}: every "
            "bond here that failed as expected has already ratified a "
            "different proposal - one bond consumes on one verdict; run "
            "`atlas law bond-test` again in this session."
        )
    bond = fresh[-1]
    proposer_actor = (proposal.get("data") or {}).get("actor")
    if proposer_actor == checker_actor:
        raise ArchiveError(
            f"Refusing to ratify proposal {proposal_seq}: the proposer and "
            f"the checker are the same actor ({checker_actor}), compared by "
            "fingerprint, not by role label - an operator-granted checker "
            "session does not let a proposal ratify itself. Declare a "
            "distinct GODMODE_AGENT_ID per agent: with none declared every "
            "process on this project shares one fingerprint, so proposer and "
            "checker always compare equal and ratify can never succeed."
        )

    # NS-12d: a skill target is gated on strict improvement before any
    # verdict is written - see this function's own docstring above.
    impact: dict[str, Any] | None = None
    skill = skill_name_from_target(proposal_target) if proposal_target else None
    if skill is not None:
        if project is None or diff_path is None:
            raise ArchiveError(
                f"Proposal {proposal_seq} targets a skill ({proposal_target}); "
                "`atlas law ratify` needs --diff <file> to apply and score "
                "the change before it can be ratified."
            )
        diff_path = Path(diff_path)
        given_hash = diff_hash_of(diff_path)
        proposal_diff_hash = (proposal.get("data") or {}).get("diff_hash")
        if given_hash != proposal_diff_hash:
            raise ArchiveError(
                f"--diff does not match proposal {proposal_seq}'s own "
                f"diff_hash ({proposal_diff_hash}); ratify must apply the "
                "SAME diff the proposal named, not a substitute."
            )
        impact = apply_skill_diff(archive, project, proposal_target, diff_path, patterns)
        if impact["outcome"] != "accepted":
            raise ArchiveError(
                f"Proposal {proposal_seq}'s change to {proposal_target} did "
                f"not strictly improve ({impact['score_before']} -> "
                f"{impact['score_after']}, best recorded so far "
                f"{impact['best_recorded']}): the skill file was restored "
                "to its pre-change bytes (never the operator's own git "
                f"checkout) and this stays an open proposal with a "
                f"rejected skill_impact at seq:{impact['sequence']}."
            )

    verdict_data = {
        "proposal_seq": proposal["sequence"],
        "actor": checker_actor,
        "verdict": "ratified",
        "bond_seq": bond["sequence"],
    }
    record = archive.append(
        "improvement_verdict", f"ratify:{proposal['sequence']}", verdict_data,
        evidence=[f"seq:{bond['sequence']}", f"seq:{proposal['sequence']}"],
    )
    result = {
        "sequence": record["sequence"],
        "proposal_seq": proposal["sequence"],
        "bond_seq": bond["sequence"],
        "actor": checker_actor,
        "verdict": "ratified",
    }
    if impact is not None:
        result["skill_impact"] = impact
    return result
