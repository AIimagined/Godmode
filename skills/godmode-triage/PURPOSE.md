# Purpose

This skill exists so the open-asks queue ends in dispositions on the record
- closed, promoted, mapped or parked - instead of growing until rules
misfiled as asks and phantom asks crowd out the ones still owed.

## Gap evidence

- seq:14268 - "Of the 62 open asks, only 5 are pure conversational control
  once deduplicated to the latest record per subject": sixty-two asks open
  at once, most of them never disposed of, some of them standing rules
  filed as requests.
- seq:16531 - "Plan 3 Task 2: one reader and one window for open asks across
  the stop hook, status, preflight and history (e379a0f + hunks in
  d773a2b)": the record that introduced the single open-ask reader behind
  `godmode history --kind request` and the closure refusal that names the
  open list, which this skill's steps 2 and 5 front.
- seq:16515 - "Plan 3 Task 5: falsifiers age into a preflight finding after
  two days; verify --falsifiers runs the due ones (d773a2b)": the record that
  introduced `godmode verify --falsifiers`, which this skill's steps 4 and 6
  front.

## Promise

Every open ask is read in full and disposed of by its exact id: a rule
becomes an invariant, work maps to a task, noise is closed, and anything
left is parked with a reason - with the count proven before and after.

Future edits to this skill append their own seq: citation above.
