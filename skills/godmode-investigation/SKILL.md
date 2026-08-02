---
name: godmode-investigation
description: Diagnose technical failures with reproducible evidence and bounded hypotheses. Use when a bug, regression, test failure, build failure, performance problem, or repeated unsuccessful fix needs root-cause investigation.
---

# Godmode Investigation

## Outcome

Locate the earliest evidence-supported cause, test one discriminating hypothesis, and
either verify a focused remedy or state exactly what remains unknown.

## Evidence cycle

1. Restate the observed failure without proposing a fix.
2. Reproduce it with the smallest reliable command or artifact. Record the environment
   dimension only when it materially changes the result; never dump the environment.
3. Trace the failing value or state backward across each relevant boundary. Capture
   inputs, outputs, status, and timestamps with secrets redacted.
4. Compare with a working path in the same codebase and list every meaningful delta.
5. Form one hypothesis: cause, supporting evidence, and a result that would falsify it.
6. Run the smallest discriminating experiment. Change one variable.
7. If confirmed and the user requested a fix, create a regression check, implement one
   coherent remedy at the origin, and run the full relevant verification.

Do not implement when the user asked only for diagnosis. Do not weaken, delete, skip, or
rewrite a valid test to manufacture a pass. A mock must preserve the contract being
tested and cannot replace the behavior under investigation.

## Loop control

Record failed attempts with `checkpoint --status failed --hypothesis ... --outcome ...`.
Do not repeat a failed hypothesis without new evidence. On the third failure of the same
hypothesis, stop changing code and revisit the architecture, boundary assumptions, or
test validity with the user. A different edit with the same causal claim is still the
same attempt.

## Evidence quality

Prefer fresh command output, a minimal reproduction, traceable file/line references,
content hashes, database migration state, and Git history over recollection. Treat agent
reports, comments, and stale docs as leads until verified. Distinguish correlation,
inference, and direct observation.

## Handoff

Record the symptom, reproduction, confirmed or rejected hypothesis, evidence, attempted
change, outcome, and next discriminating action. Generalize a private lesson only after
the mechanism is understood. Report no broader success than fresh verification proves.

Read [godmode-evidence-cycle.md](references/godmode-evidence-cycle.md) for the attempt
record and completion checklist.
