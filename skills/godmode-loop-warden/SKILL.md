---
name: godmode-loop-warden
description: "Bound an iterative fix-and-retry cycle before it starts and stop it when it stops making progress: audit the loop contract, declare the iteration cap and stop conditions, tick every iteration with its evidence, read the host transcript for repeating error signatures and overlapping hunks, check whether blaming the model is supported, and close the loop as finished or cut off. Use when the same failing test is being retried, edits keep landing on the same lines, or an agent has looped past its budget without noticing. Not for root-causing the failure itself, and not for open asks that repeat across sessions."
---

# Godmode Loop Warden

## Outcome

Every retry cycle runs under a declared cap with named stop conditions, each
iteration leaves a tick with its evidence, a stalled cycle is stopped at the
cap rather than at exhaustion, and the close says finished or cut off with
the evidence that decides which.

## Use

- The same failing test or build error is being retried with small edits.
- Edits keep landing on the same lines or hunks with nothing new asserted.
- An agent has run more iterations than the task warranted and cannot see it.
- A loop is about to start and its stop contract has not been written down.

## Do Not Use

- Root-causing the failure the loop is retrying - that is `godmode-investigation`.
- Open operator asks that repeat across sessions - that is `godmode-triage`.
- Re-pitching an answer the operator did not follow - that is `godmode-repair`.

## Deterministic Execution Flow

1. **Audit readiness before cycle one.** `godmode loop --preflight` - the loop file's stop contract, budget, verdict path and escalation thresholds; a missing piece is named before any iteration runs.
2. **Declare the cap and the stop conditions.** `godmode loop declare <name> --max-iterations 5 --stop-when "the failing test passes"` - the cap is fixed at declaration; a loop with no cap is refused.
3. **Tick every iteration with its evidence.** `godmode loop tick <name> --evidence seq:<the attestation of this iteration's check>`; an iteration that changed nothing is `godmode loop tick <name> --empty` - the empty ticks are what escalate.
4. **Read the transcript for repetition the agent cannot see.** `godmode loop --transcript <host transcript path> --episodes` - repeating error signatures, overlapping hunks, no new files, no new assertion, with the backtrack context for each episode.
5. **Check the blame before changing the model.** `godmode loop --blame --session <session id>` - whether blaming the model is supported by a non-model control; a loop with no such control is a contract gap, not a model fault.
6. **Close with the outcome the evidence supports.** `godmode loop close <name> --outcome finished --evidence seq:<the passing check>`, or `godmode loop close <name> --outcome cut-off --evidence seq:<the last tick>` when the cap was reached.
   - Fallback: a close that names no evidence is refused; cite the tick or the attestation, never a description of it.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never raise the iteration cap mid-loop; instead close it cut off and declare a new loop with its reason.
- Never close a loop as finished without the passing check's evidence; instead close it cut off.
- Never blame the model before `loop --blame` names a non-model control that supports it; instead record the contract gap the check found.
- Never tick an iteration as progress when the diff touched the same hunk with no new assertion; instead tick it empty.
- Never run the retried check on the live archive of another session; instead name the session on every verb.

## Acceptance

- Every loop on the record has a declaration, at least one tick, and a close.
- No loop closed as finished cites nothing.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
