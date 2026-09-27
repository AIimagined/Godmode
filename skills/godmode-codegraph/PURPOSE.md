# Purpose

This skill exists so a blast-radius question - who calls this, who imports
this, what would need retesting - is answered from a saved, on-demand graph
instead of a raw full-file read repeated for every changed path.

## Gap evidence

- The graph, closure, and retest machinery this skill routes to already
  existed, but nothing turned "read the graph before a raw file read" into
  one flow a session actually follows.
- A standing instruction to consult the dependency graph before a raw
  full-file read was given more than once, but nothing recorded its exact
  wording each time — only that it recurred, inferred from a shared keyword
  rather than from two independent statements of the same instruction.

## Promise

Before a change is made, this skill rebuilds or verifies the on-demand graph
against the archive that derived it, answers who depends on the affected
node and what must be retested, and only falls back to a raw full-file read
for what the graph has no edges for.

Future edits to this skill append their own plain-language evidence above.
