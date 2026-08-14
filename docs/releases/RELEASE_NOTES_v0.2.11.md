# Godmode v0.2.11

A gate that judges structure, not vocabulary.

The pre-tool gate used to ask one question of a whole line of text: does any
word in it look dangerous. That question convicts an argument for the
command's sin and acquits a command for having no known name at all — two
ways of answering "what does this word suggest" when the only question that
matters is "what does this command's own structure do." This release rebuilds
the gate to ask that second question, on evidence pulled from real sessions
rather than imagined ones, and gives the common case a path that costs almost
nothing to walk.

## The evidence

A 50-session window (measured 2026-08-14) put a number on what the old gate
actually cost: a **3.9s** median latency on every gated call, **388** calls
that ran past the then-10s cap and blocked for roughly **11.6s** each, and
**52** denials of commands that were, on inspection, read-only. Those 52
denials were harvested into a 142-command regression corpus — real commands
a real session issued and the old gate refused or stalled on — and every
false-positive in it traces to one of five shapes, not fifty different bugs:

- **Argument text convicting the command.** A `>` inside a quoted JavaScript
  argument read as a shell redirect; a file path containing a vocabulary word
  (`docs/RELEASE-CHECKLIST.md`) read as if the word were the verb.
- **An unrecognized command refused as a mutation.** `rev`, a bare `sed`/`tr`
  in a pipeline, a `curl` status probe — no known write behavior, refused
  anyway, for the sole reason that nothing named them safe.
- **Stream tools misread.** The same class as above, narrowed: tools that
  only ever transform stdin to stdout, held to the standard meant for tools
  that write files.
- **Category vocabulary collisions.** A word chosen for one category's
  detection matched a command that belonged to a different, harmless one.
- **Protected-path reads blocked.** Reading a file inside this project's own
  runtime directory was refused as if reading were writing.

## What changed

| Surface | What it does now |
|---|---|
| `hooks/godmode_gate_fast.py` | stdlib-only, zero-import table lookup answers most calls before the full runtime is paid for |
| `hooks/gate_table.json` | generated from the classifier's own vocabulary tables, not hand-typed, and freshness-tested against it |
| `classify_action` segment scan | reads each segment's own command-position words, never the raw line |
| unrecognized commands | read at R0 on no evidence of mutation, instead of refusing for ignorance |
| `git add` / `git commit` | ask instead of running silently |
| `git checkout -b` | no longer asks — creates a local branch, same tier as `git branch` |
| `godmode init --detect` | writes a starter charter from what the repo already proves about itself |

The fast gate answers exactly one question — is this command's head on a
vetted, host-parity, read-only floor, with no redirect and no destructive
flag — and returns only `allow` (the full runtime never runs) or `escalate`
(the full runtime runs, unchanged, its answer mirrored verbatim). It never
itself decides `ask` or `refuse`; every path it cannot resolve escalates.
Measured directly against `godmode_gate_fast.py` (2026-08-14, 10 timed runs
after warm-up, median of the sorted sample): a fast-path allow (`git status`)
resolves in **90.3ms**; an escalating call (`git push --force`, refused) in
**468.6ms**. `hooks.json`'s `PreToolUse` timeout drops from 10s to **3s** —
the old cap was sized for a runtime that no longer sits in the common path.

`gate_table.json` is no longer a hand-built fixture. `scripts/dev/build_decision_table.py`
reads the classifier's own vocabulary — its mutation-flag set, its write-flag
table, its database-client list — and re-verifies every floor entry, every
git-ask and git-refuse candidate, and every mutation head against
`classify_action` at generation time, so a classifier change that moves one
of them breaks the build instead of shipping a table that quietly disagrees
with the code it was drawn from. The table can never allow more than the full
runtime already would: that equivalence is one-directional by construction,
checked continuously, never assumed.

`git add` and `git commit` now ask rather than running silently — the one
git rule the classifier had not yet been given, once asking (an in-session
approval) became a real option instead of only refusing outright. `git
checkout -b` moved the other way: creating a local branch discards nothing
and leaves a repository no differently than `git branch <name>` already does,
so it sits at the same tier ordinary local computation sits at. Push and
history-rewriting forms are unchanged by this release: they continue to
refuse outright without a capability, because reversibility is exactly the
line this release drew everywhere else.

New this release, beyond the gate itself: write-capable-flag evidence
(`--output`, `sort -o`) is read as the write it performs even with no shell
redirect in sight; a command substitution escalates rather than reading only
the substitution's own surface behavior; the remote-execution family
(`ssh`/`scp`/`rsync`/`sftp`/`nc`, …) is never read-only regardless of how a
specific invocation looks; and `godmode init --detect` writes a SOFT starter
charter from manifests, CI workflow lines, and lint configs already in the
repository — it names its own evidence inline and never overwrites what a
project already has.

## Fixed

Each of the five false-positive classes above is fixed at the level the
regression corpus proved it, not patched at the level of one failing example:
redirect and vocabulary detection now run on quote-aware, command-position
text per segment rather than the raw line (`split_segments`, a new public
interface later gate work builds on directly); the fail-closed
`unclassified-mutation` bucket now requires actual evidence of mutation, not
merely an unfamiliar name, while `bash -c`/`eval`/`ForEach-Object` blocks and
database-client invocations keep asking regardless of how harmless a specific
instance looks; and protected-path reads are pinned by regression test
against the corpus that already showed zero surviving instances of the
failure.

Ten new detectors round out the evidence-discipline surface this release
also carries: a verdict-bearing command piped through a truncating filter is
named before it destroys its own evidence; guard-erosion monitors join the
integrity pass; four new mistake detectors cover a pending claim carried as
evidence, a fix built on an unconfirmed root, an absence claim with no
control probe, and a single-file diff claiming every caller; a push names the
workflows it would trigger, and an overwrite names the file it replaces
instead of implying a blank slate.

## Deliberately not built

The fast gate never learns a new allow on its own. Every entry on its floor
traces to a generated table checked against the classifier at build time;
widening what resolves in the fast path is a change to that generation step,
reviewed like any other classifier change, never an inference the table
makes at runtime from what it has seen before.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_gate_corpus -v      # the 142-command regression corpus
python -m unittest tests.test_gate_fast            # the fast-path table lookup
python -m unittest tests.test_gate_parity           # generated table matches the classifier
python scripts/godmode.py --project . version --reconcile
python scripts/godmode.py --project . doctor
```

The regression corpus (142 commands, every one harvested from a real
session's denial) is fully green: `tests.test_gate_corpus.GateCorpus
.test_every_entry_matches_expected` reproduces cleanly against current HEAD.
The full suite passed at 1112 tests across four shards the last time this
work measured it end to end; run `scripts/dev/run-suite.ps1` for a fresh
sharded run.
