# Godmode v0.3.6

The record learns how much to trust itself.

Every release so far made the record harder to fool. This one makes it
measurable: a claim can say how sure it was, meet its outcome on the
record, and leave a score behind - so "how well does this project's
confidence track reality" stops being a feeling and becomes a number
the doctor reads back.

## The calibration ledger

`godmode claim --confidence 0.9 ...` declares how sure; `claim
--resolve SEQ --outcome held|failed --cite <evidence>` closes the loop.
The pair scores as 1 - (confidence - outcome)^2 on the resolution
record. `doctor` reports the ledger: mean score, error rate per
confidence band, the standing debt of scored claims nothing resolved,
and - advisory, from resolved records only - a warning when recent
confidence stops tracking outcomes. A resolution needs evidence, lands
at most once, and is never itself resolvable.

## Shown or said, never both as one word

Status renders carry evidence tiers from one table: `verified` only
for a verified state with cited evidence; a completion nothing was
cited for renders `declared`; open items read `likely` or `unproven`.
The handover splits verified_completed from declared_completed, so a
reader always knows which completions rest on a statement.

## The ready set is derived

`status remaining` splits open items into ready and blocked - blocked
by a `--blocked-by` note or by any dependency not yet terminal. Phantom
dependencies are refused with the fix named; the write that would close
a dependency cycle is the one that fails.

## An all-clear must cite the run

A verified claim whose text is a review's pass verdict downgrades
unless a `cmd:` citation shows the checks were run, not read. And the
doctor gains the dissent check: a record window where no check ever
failed, past a sample floor, is reported as evidence about the checks
rather than the work.

## The record teaches while it is fresh

precheck surfaces guarded lessons the compiled law file does not carry
yet, marked fresh-uncompiled, and carries recurring incident patterns
forward before the action - once per session per pattern, counted over
the whole archive, never a window that forgets. A checkpoint written
while the newest incident postdates the newest lesson says so. `law
hygiene` names laws with no recorded origin, contradictory pairs, and
guards a recorded check now enforces mechanically. Incidents can carry
one of nine closed failure classes and a cited turning point, and the
third-strike wire names the class.

## Quality surfaces that name their own limits

`skill lint` reads scope, delivery, and safety facets and labels its
verdict structural - never a deployment-value claim. The docs linter
learns two pointer rules, and the shipped docs were rewritten to obey
them. `metrics` gains verified-result economics and opt-in
`--complexity` (per-function branch counts from the ast). `docs
--emit-agentsmd` serves hosts that read AGENTS.md and wire no hooks,
generated from the registered verbs so it cannot drift. `precheck
--preflight` validates HEAD in a disposable worktree - banned-term scan
plus a designated suite, findings triaged mechanical versus judgment -
and feeds the password gate, never bypasses it.

## Also

The day-one face and first-week guide (queued from the previous cycle),
the grok marketplace entry version drift fixed, and strike counters
moved from a bounded window to the full append-only record.

Eleven fragments folded; full suite green in four sequential chunks
before the tag.

## Verifying

- `python -m unittest discover -s tests` - run in shards
  (`scripts/dev/run_with_flaky_retry.py` retries only registered flakes);
  2954 tests green across the four chunks at tag time.
- `godmode evals --brief` - exit 0.
- `godmode doctor` - the calibration block renders (honestly empty on a
  fresh archive).
- `godmode changelog check` - fragments folded at release time.
- `godmode version --reconcile` - every surface answers 0.3.6.
