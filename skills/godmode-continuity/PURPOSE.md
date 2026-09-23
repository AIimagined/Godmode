# Purpose

This skill exists so a session can reconstruct what is actually true about a project
right now, from evidence it can check, instead of trusting whatever context happened
to survive between sessions.

## Gap evidence

- seq:3683 — a session brief presented a checkpoint days older than the project's own
  state file without saying it was stale.
- seq:9036 — a status query returned hundreds of items dominated by months-old
  entries with no age split, unusable for answering "what is left now".
- seq:8708 — a prescribed closure was invisible to two of three components meant to
  read it, because each rebuilt its own view of the same state instead of sharing one.

## Promise

A continuity pass states current project identity, branch, and drift from checked
evidence, marks anything it cannot verify as unverified rather than assumed, and
leaves a recovery point outside the working tree for the next session.

Future edits to this skill append their own seq: citation above.
