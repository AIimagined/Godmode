# Godmode v0.2.7

The gate, corrected against the commands this project actually ran.

Two releases went into making the agent's own tooling checkable — source that
arrives damaged, evidence that cannot be traced to a run, obligations nobody
retires. This release turns the same treatment on the oldest component: the
action gate that decides which operations get refused.

Its allowances had been wrong five times before. Each time the defect was found
the same way — a human hit a refusal in the middle of real work and said so.
That oracle is slow, and it only ever surfaces the one refusal somebody
happened to meet.

## The corpus was captured, not written

Every Bash, PowerShell and file-edit call this project has made was recovered
from its own transcripts and classified in bulk: **1,419 distinct commands**.

The gate refused **506**. **74** of those named no mutation of any kind.

Twelve defects were behind that number, and they had been sitting in a
classifier with a passing test suite, a falsification harness, and its own
self-check. Nothing found them because nothing had ever run real commands
through it.

## One of the twelve ran the other way

```
echo pwned > ~/.bashrc          →  permitted
```

`~` is not a path this process expands. The target had no leading slash and no
drive letter, so it was joined to the project root, passed containment, and the
gate approved a write to the user's shell profile **on the grounds that it was
inside the working tree**.

An unexpanded path is no longer treated as a path. It cannot be resolved here
without reproducing the host's environment, and guessing is precisely what
opened the hole — so `~`, `$VAR` and `%VAR%` targets are not contained, and a
literal path still is.

Checking when this appeared is itself worth reporting: it was refused in v0.2.3
and v0.2.4 and permitted from v0.2.5. Nobody weakened it. The earlier releases
refused *every* redirect, so the hole was covered by accident, and the v0.2.5
fix that made ordinary file writing usable is what exposed the containment
check underneath it.

## A word boundary that falls inside a hyphen

`git commit-tree` writes an object into the store. It was admitted by the
allowance for ordinary committing, because the boundary after `commit` sits in
the hyphen.

The same shape read `merge-base` as `merge` and refused it — a read reported as
history mutation. That harmless half is what made the pair visible at all: the
false positive was noticed, and the false negative was hiding behind the same
line.

## The refusals

Nine more, each a command real work needed and the gate would not run:

- `git -C path <read>` and the other global options. Every git rule looked for
  a subcommand at a fixed position, so a global option in front meant no rule
  matched. They are stripped once now, shared by classification and tiering.
- Fourteen git read subcommands the list had never heard of — `rev-list`,
  `ls-files`, `ls-remote`, `describe`, `blame`, `cat-file`, `shortlog`,
  `for-each-ref`, `merge-base` and more.
- `> /dev/null`, treated as a write to a file outside the tree. Silencing a
  command's output was a protected operation.
- `--help` and `--version`, classified as the operation they describe.
  `release --help` was refused at R4 — the gate at its least credible, blocking
  the one call whose entire purpose is to explain itself.
- `gh` reads, including `gh auth status`. `gh api` is judged on its flags
  rather than its noun, because it becomes a write through `-X POST` or `-f`,
  never through a word.
- PowerShell literal assignments. `$d = "C:\docs"` was an unknown mutation, so
  every PowerShell script was refused from its first line.
- `export` and `unset` of names that do not decide what runs. `PATH`,
  `LD_PRELOAD`, `PYTHONPATH`, `BASH_ENV` and their relatives stay closed: an
  environment variable that changes which binary a later `git` is, is not
  bookkeeping.
- A segmenter that split inside an escaped quote, so
  `grep -nE "a|\"b\":|c" file` was refused — a search reported as a mutation
  because its pattern contained a quote. It now follows the shell's own rule,
  which also means `ls \; rm -rf /` is read the way the shell reads it.

## Two the tests found, not the corpus

The R5 escalation searched the text before global options were stripped, so
`git -C repo push --force` came out as an ordinary unknown at R3: the category
and the tier had been decided on two different strings. And `commit-tree`
above, which no corpus command contained.

Both were introduced by fixing the other ten, and both were caught by tests
written to prove the ten fixes worked. A fix for a false positive created a
false negative one function away.

## What is still refused, on purpose

Unknown binaries, PowerShell script blocks that can carry any command, and
plumbing that writes are asserted as deliberate refusals rather than left
unmentioned. A later widening now has to argue with a test instead of with
somebody's memory.

## The refusal that denied its own remedy

Every refusal ended with the same sentence: no capability can be attached to a
host tool call, so there is no in-session approval — run it yourself, rephrase
it, **or disable the plugin for this session**.

Twenty lines above that sentence, in the same function, a staged capability is
consumed and the call proceeds. `authorize stage` shipped in v0.2.6 to answer
exactly this refusal. The message was written when the broker really was
unreachable and was never revisited when the answer arrived.

So the guard's own error text denied the existence of its remedy, and the
advice most likely to be taken was the one that removes the guard. It now names
the staged-capability path and quotes the exact operation to authorise.

Found by hitting it: a push was refused, and checking whether the hook honours
staging — rather than trusting the message — showed that it does.

## Scope, restated

This gate answers "does this name a protected operation" and fails closed on
anything mutation-shaped it does not recognise. It is not a sandbox. Running an
interpreter is local compute, so a protected operation written into a `.py`
file will run — gating every interpreter call was tried, denied `ls`, and
stopped all work. The gate raises the cost of a mistake; it does not make one
impossible.

## Also in this release

A changelog correction found while cutting it: two entries describing work
shipped in v0.1.0 had sat under **Unreleased** through eight releases. The
version reconciler agreed across all nine surfaces the whole time, because it
compares version *numbers* and nothing checked whether a section labelled
unreleased had in fact been released.

## Upgrading

No migration. Every change is to classification: commands previously refused
now run, and two that previously ran are now refused. If a workflow depended on
`> ~/.bashrc` or `git commit-tree` being permitted, it was depending on a
defect.

## Verifying

```
python -m unittest discover -s tests            # 660 tests
python -m unittest tests.test_gate_corpus       # the twelve, both directions
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . integrity
```

Every widened allowance in `tests/test_gate_corpus.py` ships beside the
mutation it must still refuse, because an allowance tested only in the
direction it was widened proves nothing about what it let through.
