---
name: godmode-spec-lifecycle
description: Move a specification and its plan through specify, approve, implement, review, and status as one linked, resumable record instead of separate hand-authored drafts that drift apart. Use when a task needs its spec written, a plan approved before mutation, work bound back to that plan, and its status checked or reverted. Not for authoring a standalone document with no tracked contract, and never as a way to approve a plan against yourself.
---

# Godmode Spec Lifecycle

## Outcome

A task's what/why, its plan's how, its approval, its bound implementation, and its status are one linked chain a later session can resume from `planmode check` - not a set of prose drafts that drift and get reconciled by hand, after the fact, in a checkpoint note.

## Use

- A task needs a spec (`objective`, `outcome`, `acceptance`, `non_goals`) recorded before any plan names a how.
- A plan's contract is complete and needs approval before the first edit, or its current gap list needs reading.
- Work already done needs binding back to its approved plan, so drift outside the declared scope is named rather than silently allowed.
- Two divergent drafts of the same spec or plan need reconciling into one linked record instead of a superseding claim added by hand later.
- A stalled or abandoned plan needs its status read, or the project needs reverting to a prior verified point.

## Do Not Use

- Writing a one-off prose document (a README section, a design write-up) with no plan or mutation behind it - that is ordinary authoring, not this flow.
- Approving a plan you just drafted in the same pass, as the same actor, with no independent check in between - see Must Not.
- Hand-editing `GODMODE-CODE-OF-LAW.md` to add a rule a spec turned out to need - route that through `atlas law`.

## Deterministic Execution Flow

1. **Read where things stand before writing anything.** `godmode precheck --about "<the task, in your own words>"` - a bounded read of the project's current state against the stated task; run it before drafting a spec so the spec is written against reality, not memory.
2. **Record the what/why.** `godmode planmode specify --title "<title>" --objective "<objective>" --outcome "<outcome>" --acceptance "<acceptance>" --non-goals "<non-goals>"` - refused when any of the four fields is empty; a plan without a spec is refused later at step 3.
3. **Record the how.** `godmode planmode start --title "<title>" --objective "<objective>" --acceptance "<acceptance>" --accept "cmd:<command that proves done>" --scope "<paths>" --out-of-scope "<paths>" --current-state "<state>" --assumptions "<assumptions>" --parity "<parity>" --steps "<steps>" --risk "<risk>" --rollback "<rollback>" --verification "<verification>" --points "<points>"` - exits 1 and names every missing contract field in `gaps` rather than starting incomplete.
   - Fallback: a missing field is filled and the command re-run; the contract is never approved with a gap waived.
4. **Check before approving.** `godmode planmode check` - reports `allowed: false` with the plan's current `missing` fields until the plan is approved; read this rather than assuming the contract from step 3 is already complete.
5. **Approve, from an independent check.** `godmode planmode approve` - approves a complete contract; refuses with the exact missing fields if the contract still has gaps.
   - This is where the must-not below applies: approval is a genuine second read of the completed contract, not an automatic next line after `start`.
6. **Implement inside the approved plan's scope.** Ordinary edits proceed once `planmode check` reports `allowed: true`. `godmode planmode bind --summary "<summary>" --file <path> [--file <path> ...]` records the work against the plan and names any file outside the declared `scope` as drift, rather than allowing it silently.
7. **Reconcile a divergent draft as a new proposal, not a silent overwrite.** When implementation reveals the spec or plan needs a rule the project does not yet enforce, `godmode atlas law propose --target <path> --diff <file> --cite <evidence>` records the proposed change with its evidence; it is ratified only after a fresh bond test in the reviewing session (`godmode atlas law bond-test <name> --command "<checker>" --file <path>` then `godmode atlas law ratify <proposal_seq>`), never applied by editing the compiled law file directly.
8. **Track and resume status.** `godmode status remaining` or `godmode status render` shows what is still open against the plan; a later session resumes from this plus `planmode check`, not from re-reading prose.
9. **Revert a plan that must not proceed.** `godmode rewind --to <seq>` previews returning to a prior verified record, through the same governance preview any protected operation requires - never a bare `git reset`/`git checkout --` over shared history.
10. **Close the loop.** `godmode checkpoint --summary "<summary>" --status "<status>" --next "<next action>" --evidence "<evidence>"` records the resumable handoff: the next session reads this plus `planmode check` instead of re-deriving intent from the conversation.

Read [PURPOSE.md](PURPOSE.md) for the archive evidence this skill exists to close.

## Must Not

- Never approve its own plan: `planmode approve` must not be the very next command after `planmode start` in the same drafting pass with no independent read in between - run `planmode check` first, and let a separate reviewing pass (or the operator) run `approve` once the contract's gaps are actually inspected, not assumed complete.
- Never treat an approval that skipped step 4 (`planmode check`) as valid; an approval with unread gaps is a rubber stamp, not a check.
- Never edit `GODMODE-CODE-OF-LAW.md` by hand to add a rule a spec needs; propose it (`atlas law propose`), prove the checker can fail it (`atlas law bond-test`), and only then ratify it.
- Never resolve two divergent drafts of the same spec or plan by silently overwriting one; record the newer draft's figures as superseding the earlier ones with a cited reason, or route the change through `atlas law propose` when it changes an enforced rule.
- Never use `rewind` as a substitute for `git reset --hard` or `git checkout --` over shared history; a destructive git operation on tracked history goes through `godmode-governance`, not this skill.

## Acceptance

- `godmode planmode check` reports `allowed: false` with the exact missing contract fields until a complete plan is approved by a pass distinct from the one that drafted it.
- `godmode planmode bind` names every file outside a plan's declared scope as drift rather than allowing it silently.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
