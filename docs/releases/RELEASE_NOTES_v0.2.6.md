# Godmode v0.2.6

The mechanisms that only ran when someone remembered them.

Every check in this product that runs by itself has been catching real defects.
Every check that had to be invoked caught nothing: `claim`, `attest`,
`experiment` and `lessons` each held **zero records across the project's entire
life**. Not because they were broken — using them was a decision nobody made.

This release closes that gap where it can be closed, and measures what could not
previously be measured.

## A fix that keeps being needed is not a fix

`loop` now reports a file repaired by `fix:` commits across three or more
releases.

Inferring a stalled attempt from the records was tried first and abandoned after
testing it: every checkpoint in the archive is green and no subjects cluster, so
the failure signal is simply not in the record. It is in history, which is
written by the act of committing rather than by anyone choosing to admit being
stuck.

Run against this repository it names the action gate — repaired across four
releases while the real cause was structural.

## Finishing a task records the claim

`claim` grades an assertion against citations that must resolve, and it is the
first thing this product's documentation demonstrates. It had never been used,
because it is a command somebody has to decide to run and an agent finishing a
task is reaching for the finish rather than for a subsystem.

Saying the work is done is the same assertion, made at the moment it is actually
made. `report --record-claims` puts it through the same grading. The first real
run downgraded to hypothesis for want of a citation — the feature working, not
failing.

## A refusal an operator can answer

The gate's refusal named a remedy that did not exist. No host tool call carries a
field a capability could travel in, so the broker was unreachable and the only
response to a false positive was switching the guard off entirely.

The broker was never the missing part: its token is password-issued, bound to one
exact operation, expiring, and spent once. What was missing was a place the hook
could read it from. `authorize stage` puts it in the archive's state directory,
under the git metadata rather than in the working tree, so a cloned repository
cannot carry one. The token is never printed — a capability on a terminal is a
capability in a scrollback buffer.

## Measuring, without collecting anything

The host already writes a session transcript to disk and hands its path to every
hook. Nothing here read it.

`godmode_usage` reads counts and keeps counts. The file is streamed rather than
loaded, only numeric usage fields are touched, the transcript's own path is not
returned, and measuring writes nothing anywhere. Those properties are asserted
against a transcript seeded with distinctive strings, so the privacy contract is
checked rather than promised. A missing transcript reports insufficient data,
never zero.

## Benchmarks that can report bad news

`benchmarks/` holds four tasks checking that each mechanism fires. Every binary
task ships a control run with the fault absent that must produce the opposite
result, because a task whose control also fires measures nothing.

`ab_resume.py` does the same work twice — the brief against deriving the same
facts by hand — and **publishes no ratio**. The arms recover different numbers of
facts, so a normalised figure would compare unlike things. It reports dominance
instead, in whichever direction the measurement points.

## The product audits itself

`capabilities --usage` reports which declared surfaces this project has never
used. Establishing that manually is what began everything above.

`docs --lint` gains a stale-figure check: a number in public prose the runtime
can count for itself is compared against the real count. Historical records are
exempt, since a changelog states what was true when written. The badge that
motivated the check was fixed by **removing** the count — a document stating how
many tests exist goes stale on the next commit that adds one.

The surfaces a host feeds are enumerated, each with a test crossing its real
boundary or a stated reason for having none.

## Two faults this release found in itself

A test asserted a fact about repository history that a shallow checkout cannot
see, and went red on all six CI jobs. The detector was right; the test assumed
history the runner does not have. Both worlds are asserted now, and neither is
skipped.

Reproducing that turned up a second fault it had nothing to do with: **a project
checked out under the system temporary directory had lost its containment rule
entirely.** Every path near it was also under temp, so the scratch allowance
swallowed containment and every write outside the tree was permitted. That covers
CI workspaces, sandboxes, and any build under `/tmp`. Where the two rules
overlap, containment now governs alone.

## Upgrading

No migration. `report --record-claims`, `capabilities --usage` and
`authorize stage` are new; nothing existing changed shape.

## Verifying

```
python -m unittest discover -s tests            # 562 tests
python benchmarks/benchmark.py                  # every mechanism fires
python benchmarks/ab_resume.py                  # the same work, done twice
python scripts/godmode.py --project . capabilities --usage
python scripts/godmode.py --project . loop
```

The suite is verified in a tagless clone as well as a full one, because a check
that passes only where it was written is the defect this release spent its last
two commits removing.
