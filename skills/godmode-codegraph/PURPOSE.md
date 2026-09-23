# Purpose

This skill exists so a blast-radius question - who calls this, who imports
this, what would need retesting - is answered from a saved, on-demand graph
instead of a raw full-file read repeated for every changed path.

## Gap evidence

- seq:17482 - "Plan 4 Task 5 landed on sprint as ee25ef6 + 79c9bab;
  graph/closure/retest/reference-drift/verb-coverage modules green" built the
  graph, closure, and retest machinery this skill routes to, but nothing had
  yet turned "read the graph before a raw file read" into one flow a session
  actually follows.
- seq:9680 (recorded 2026-09-05) and seq:17539 (recorded 2026-09-17) are two
  `instruction`-origin lessons, 12 days apart, whose mined keyword digests
  both include `atlas`. Neither record retains the instruction's own text -
  each `value` field is the mining pipeline's fixed boilerplate ("operator
  stated a standing instruction (counts only); draft a guard at review") -
  so the recurrence this skill's `repeated_uses` rule requires is inferred
  from the shared keyword alone, not read from two independent statements of
  the same instruction.

## Promise

Before a change is made, this skill rebuilds or verifies the on-demand graph
against the archive that derived it, answers who depends on the affected
node and what must be retested, and only falls back to a raw full-file read
for what the graph has no edges for.

Future edits to this skill append their own seq: citation above.
