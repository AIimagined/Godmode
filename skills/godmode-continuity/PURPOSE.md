# Purpose

This skill exists so a session can reconstruct what is actually true about a project
right now, from evidence it can check, instead of trusting whatever context happened
to survive between sessions.

## Gap evidence

- A session brief once presented a checkpoint days older than the project's
  own state file, with nothing flagging it as stale.
- A status query returned hundreds of items dominated by months-old entries
  with no age split, making "what is left now" unanswerable.
- A required closure step was invisible to most of the components meant to
  read it, because each one rebuilt its own view of the same state instead
  of sharing one.

## Promise

A continuity pass states current project identity, branch, and drift from checked
evidence, marks anything it cannot verify as unverified rather than assumed, and
leaves a recovery point outside the working tree for the next session.

Future edits to this skill append their own plain-language evidence above.
