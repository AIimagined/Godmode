# Compaction and the ledger

Compaction is a cache eviction. What lives in the chat dies at the same rate
as a debug log; what lives in the record survives. This page maps the
operator playbook of 2026-09-10 onto the commands that carry each line.

## What godmode rebuilds after a compact

The session-start hook runs on the `compact` matcher as well as on a fresh
session. The brief it emits carries a `ledger` block built from records,
never from the summary:

| Ledger field | Source record | Written by |
|---|---|---|
| goal | the active plan's subject | `godmode plan` / `planmode start` |
| invariants | `invariant` records | `godmode remember --kind invariant` |
| acceptance | plan `accept:` commands, `criterion` records | `godmode criterion` |
| files in play | the last five `change` records | `godmode checkpoint`, post-edit hook |
| failed approaches | `checkpoint --status failed` hypotheses | `godmode checkpoint --status failed --hypothesis` |
| last green | the last `ran` attestation | `godmode verify`, `godmode perimeter run` |
| open obligations | `obligation` records not closed | `godmode remember --kind obligation` |
| current step | the first pending plan step | the plan |

`godmode status remaining --digest --transcript <path>` prints the same
block on demand, with the loop episodes and the measured spend beside it.

## The context tripwire

`ceilings` carries a `context_window` entry (default 200,000). At Stop the
hook reads the last assistant usage from the transcript (input plus cache
creation plus cache read) and names the window at or above 70 percent of
that ceiling, with the numbers. Set the ceiling to the model's real window
in the project's ceilings file; the default is the practical tripwire the
field settled on, not a claim about any model.

## Rules that must survive

A rule past line 200 of an instruction file is summarised like everything
else. `session open` lists every instruction document with its line count
under `authority.long_documents`, and names a conflict between a document
that forbids editing tests and a plan step that edits one. A rule that must
hold belongs in the policy file as a deny category or in a hook, not in
prose; `godmode charter` compiles the ones that are directives.

## Perimeter checks

`godmode perimeter add "<command>"` declares a check a green unit suite
never performs: a boot, an import walk, one typed HTTP route. `godmode
perimeter run` executes every active one and attests the exit code.
`session close` refuses while any active perimeter check has no `ran`
attestation in the current session. `perimeter retire "<command>"` records
the retirement.

## Frozen tests

`godmode protect --pin <path>` on a test path makes an edit to it
`pinned-evaluator-mutation` at the gate. The integrity monitors name an assertion removed, a literal
moved, a skip added, a harness node dropped, and a new test never observed
red, in the diff since the last green.

## Verifying

- `python -m unittest tests.test_sweep_0_3_24` covers the ledger block, the
  context notice, the perimeter refusal, and the long-document advisory.
- `godmode scenarios` stages the six oracle and loop shapes and reports
  whether each was caught.
