# Purpose

This skill exists so a protected engineering action is classified and previewed
before it runs, instead of being executed on the strength of reading discipline
alone.

## Gap evidence

- seq:4562 — a correction cluster established that any multi-file removal,
  untracking, or destructive filesystem change needs a preview first; reading the
  files involved was not, by itself, a safety net.
- seq:12197 — the operation classifier over-refused a safe, index-only restore form
  by conflating it with the genuinely destructive one; a preview must distinguish
  the two, not just flag the command name.
- seq:12342 — a standing operator constraint was recorded but nothing checked a
  proposed action against it before that action was recommended and left stored
  and inert.

## Promise

A requested protected action is classified, checked against any recorded operator
constraint, and previewed as an explicit contract before anything runs.

Future edits to this skill append their own seq: citation above.
