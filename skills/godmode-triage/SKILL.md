---
name: godmode-triage
description: "Work the open-asks queue down to zero-or-mapped: list open operator asks and aging obligations, promote rule-shaped asks to invariants, map work asks to plan tasks, close answered or control-noise asks by their exact ask id, park the rest with a reason, and run falsifiers that aged unrun. Use when open asks or obligations pile up, phantom asks nag at every stop, or rules sit misfiled as asks. Not for pruning duplicate lessons, and not for re-explaining an answer that did not land."
---

# Godmode Triage

## Outcome

Every open ask ends in exactly one disposition on the record - closed with
its answer, promoted to an invariant, mapped to a plan task, or parked with
a reason - so the stop hook stops nagging about asks nobody is working and
no rule lives only as an open request.

## Use

- Open operator asks have piled up and the stop hook names them at every turn.
- Some open asks are really standing rules ("never do X") filed as requests.
- Obligations or falsifiers have aged unread for days.
- Asks repeat across sessions and should be recognised as one.

## Do Not Use

- Pruning duplicate lessons or previewing archive expiry at session close - that is `godmode-memory-gardener`.
- Writing a spec and getting a plan approved for a new task - that is `godmode-spec-lifecycle`.
- Re-explaining an answer the operator did not follow - that is `godmode-repair`.

## Deterministic Execution Flow

1. **Count before touching anything.** `godmode checkpoint --review` - its `requests` block lists every open ask as `ask:<hex> - <keywords>` with a `request-open` finding each, beside the carried obligations a later handoff made moot; it reports and closes nothing. `godmode status remaining --digest` - open obligations with their age split; it exits 1 with `verdict: work-outstanding` while any is open.
2. **Read every open ask in full.** `godmode history --kind request --limit 400` - each ask's subject (`ask:<hex>`, the first twelve characters of its digest) and its record.
3. **Find the repeats and the duplicates.** `godmode recurring --threshold 3` - asks repeated across three or more sessions (proposals only, nothing written); `godmode hygiene --cap 80` - near-duplicate and contradicting decisions and lessons.
4. **Surface what aged.** `godmode verify --falsifiers --dry-run` - falsifiers past due and never run.
5. **Dispose each ask, one of four ways.**
   - Rule-shaped: `godmode remember --kind invariant --subject "<the rule>" --value "<the rule, stated once>" --evidence seq:<the ask's seq>`, then close the ask citing it: `godmode remember --kind request --subject "ask:<hex>" --status superseded --evidence seq:<the invariant's seq>`.
   - Work-shaped: `godmode remember --kind obligation --subject "<plan task id>" --value "maps ask:<hex>"`; the ask stays open until that task's acceptance claim exists, then `godmode remember --kind request --subject "ask:<hex>" --status done --evidence seq:<the acceptance claim>`.
   - Answered or control noise: `godmode remember --kind request --subject "ask:<hex>" --status answered`.
   - Parked: the ask stays open and the reason is recorded beside it - `godmode remember --kind decision --subject "parked:ask:<hex>" --value "<why, and when to revisit>"`.
   - Fallback: a closure naming no open ask is refused with the open list, paste-ready; copy the id from that list, never retype the ask's words as the subject.
6. **Run the aged falsifiers.** `godmode verify --falsifiers` - each due falsifier runs and attests on its own.
7. **Prove the queue moved.** `godmode checkpoint --review` again - every ask its `requests` block still lists is either mapped (an obligation names it) or parked (a decision names it).

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never close an ask by retyping its words as the subject; close it by the exact `ask:<hex>` subject `history` lists.
- Never close a rule-shaped ask before its invariant is recorded; the invariant's seq is the closure's evidence.
- Never close a mapped ask before its task's acceptance claim exists; instead leave it mapped and close it when that claim is recorded.
- Never close an ask as answered when the operator's request was not actually met; park it with a reason instead.
- Never close an ask with `--as-operator` on the operator's behalf; instead park it with a reason and let the operator close it.

## Acceptance

- `godmode checkpoint --review` lists no open ask that is neither mapped nor parked.
- Every rule-shaped ask closed as superseded cites an invariant's seq.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
