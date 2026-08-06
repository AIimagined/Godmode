---
name: godmode-continuity
description: Reconstruct and preserve private project continuity from local evidence. Use when resuming work, changing branches or worktrees, detecting drift, recording handoffs, or explaining why context is missing or stale.
---

# Godmode Continuity

## Outcome

Produce a bounded context brief whose claims can be traced to current inspection or a
validated local record, then preserve the next recovery point outside the working tree.

## Reconstruct current reality

1. Resolve project, Git-common-directory, worktree, branch, HEAD, and hashed-remote
   identity before trusting prior state.
2. Run `context status`; add `--scan` when filesystem drift matters.
3. Run `inventory diff` to distinguish added, changed, and removed paths from the last
   baseline. Do not infer file content from hashes.
4. Run `resume` after a valid baseline or `resume --refresh` when evidence is stale.
5. Classify each brief item as observed fact, declared intent, assumption, conflict,
   invariant, decision, incident, open check, or obligation.

Treat identity drift, contradictory invariants, phantom file references, undocumented
changes, unproven completion, and capacity overflow as findings—not as facts to hide.

## Preserve continuity

Use the narrow record type:

- `remember --kind decision|invariant|lesson|obligation` for durable knowledge.
- `checklist update` for cumulative checks.
- `checkpoint` for a recoverable state, next actions, active hypothesis, and evidence.
- `branches --record`, `version`, `db`, `sprint`, or `docs` for domain state.

Record relative paths, statuses, hashes, and evidence references. Never record raw
prompts, conversations, tool transcripts, source bodies, secrets, or environment dumps.
A lesson may describe a failure and generalized guard, but should not preserve sensitive
failure payloads.

## Completion gate

Before ending or compacting a session, record what changed, what was verified, what is
still uncertain, and the next executable action. A `complete`, `fixed`, or `done` status
requires fresh evidence. Run `doctor` after a material continuity change.

Godmode cannot guarantee perfect memory. If no valid baseline or adapter exists, say so
and give the exact rebuild action.

Status truth lives in one writable store: `status set|survey|remaining|render|handover`
(pending items are existence-checked; phantoms close with evidence). `context why
--about X` answers with the recorded decisions, fixes, dependencies, and
invariants touching a surface; `slice` reads bounded file ranges that declare
their own truncation; `absorb --path X` proves a synced file is truly absorbed.

Read [godmode-continuity-schema.md](references/godmode-continuity-schema.md) when choosing
record types or interpreting detector output.
