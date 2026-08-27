# Two-minute terminal demo

Five commands, run in order, each producing a real exit code from a real
record — nothing here is a slide. Every number below is quoted from
`docs/releases/RELEASE_NOTES_v0.2.11.md`; re-run the cited command yourself
to reproduce it rather than trusting the quote.

## 1. Twenty-three attack and failure shapes, caught live

```console
$ godmode scenarios --brief
all-caught | total=23
```

`godmode scenarios` stages a fixed set of known failure and attack shapes —
a claim built on a deleted assertion, a stale fix a refactor silently
reverted, a secret about to land in a commit, an instruction-shaped string
sitting in project text — and checks that the matching detector actually
notices each one. `--brief` collapses the panel to one line: a verdict and
a count. `all-caught` means every staged scenario was caught; anything else
fails the command's own exit code, so a control that regresses shows up
here before it shows up in a real session.

## 2. The regression corpus: 142 real commands, all correct today

`tests/fixtures/gate_corpus.json` holds 142 commands, each one a real
session's command that the pre-v0.2.11 gate denied or stalled on. Every
entry carries the command, what it should resolve to, and a class label.
`tests.test_gate_corpus.GateCorpus.test_every_entry_matches_expected`
replays every entry against the current classifier and fails if even one
regresses:

```console
$ python -m unittest tests.test_gate_corpus -v
```

The release that built the corpus traced its 142 entries back to five
repeatable shapes, not fifty unrelated bugs: argument text convicting the
command it sat inside, an unrecognized command refused for having no known
name, stream tools held to a write-tool standard, category-vocabulary
collisions, and protected-path reads misread as writes (see
`docs/releases/RELEASE_NOTES_v0.2.11.md`, "The evidence"). Fixing the shape
fixed the whole class at once — the corpus is the regression test that
keeps it fixed.

## 3. Measured gate numbers, each one cited

Every number below is quoted verbatim, not recomputed, from
`docs/releases/RELEASE_NOTES_v0.2.11.md` — the basis column names where in
that document to check the quote:

```text
Measurement                                          Value            Basis
Old gate, median latency per gated call               3.9s            50-session window, measured 2026-08-14
Calls that ran past the old 10s cap                   388, ~11.6s ea  same window
Denials of commands that were, on inspection,
  read-only                                            52             harvested into the 142-command corpus
New fast-path allow (`git status`)                    90.3ms median   10 timed runs after warm-up, sorted-sample median
New escalating call (`git push --force`, refused)     468.6ms median  same method
`PreToolUse` timeout                                  10s -> 3s       hooks.json, this release (raised to 8s on 2026-08-28: Grok fails open past its timeout)
Full suite, at that release                           1112 tests, four shards   scripts/dev/run-suite.ps1
```

The last row states what that release measured, not this checkout's
current count — the two drift apart as tests are added, which is exactly
why the row names its source instead of asserting a number this repo
would have to keep re-proving true.

Reproduce the fast-path and escalation numbers directly against
`hooks/godmode_gate_fast.py` rather than trusting the table; the release
notes document the exact method (10 timed runs after warm-up, median of
the sorted sample).

## 4. One verdict walk-through: record a claim, watch it get checked

`godmode verdict record` runs one or more independent checker commands
against a witness and stores what they found — never what the claim's
author asserted. A confirming checker and a refuting checker against the
same witness resolve to different, visibly different, dispositions:

```console
$ godmode verdict record --claim "gate_table.json exists" --value true \
    --witness file:hooks/gate_table.json \
    --checker "python -c \"import sys; sys.exit(0)\""
{
  "acquitted_by": "independent",
  "claim": "gate_table.json exists",
  "disposition": "confirmed",
  "run_state": "terminated",
  "sequence": 552
}

$ godmode verdict record --claim "gate_table.json is missing" --value true \
    --witness file:hooks/gate_table.json \
    --checker "python -c \"import sys; sys.exit(1)\""
{
  "acquitted_by": "independent",
  "claim": "gate_table.json is missing",
  "disposition": "refuted",
  "run_state": "terminated",
  "sequence": 553
}
```

(`sequence` is a position in your own archive, not this one - it will
differ on any other run.) A `confirmed` disposition is what a `verdict:`
citation is allowed to resolve against — `refuted` and `contested` never
do. Passing `--checker` more than once runs an independent panel over the
same witness: any one refuting checker downgrades the fold to
`contested`, never averaged away.

## 5. Bootstrap a starter charter from what the repo already proves

```console
$ godmode init --detect
```

On a repo with no charter yet, `--detect` reads manifests, CI workflow
lines, lint configs, and the default branch — stdlib only, capped and the
cap reported — and writes a starter `GODMODE.md` with one line per
detected fact, each carrying its own evidence inline, for example:

```
- run tests with `npm test` (detected: package.json scripts.test) [SOFT - detected, promote after review]
```

Every detected line ships `SOFT`: a wrong guess must not become a blocking
rule uninspected, so promotion to a binding rule stays an explicit,
separate operator step. Run against a repo that already has a charter,
`--detect` never overwrites it — it emits a report of undeclared
candidates instead.

## What this demo does not claim

Sections 1, 2, and 4 show a detector or checker recording what it found;
section 3 shows what a specific measurement recorded, with its method
named so it can be rechecked. Read each step as a record of what happened
during the run shown, not as a statement about what would have happened
otherwise. Real sessions produced the regression corpus and the release's
measurement window; nothing about those sessions beyond that neutral fact
is disclosed here.
