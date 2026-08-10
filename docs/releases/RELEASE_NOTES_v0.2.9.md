# Godmode v0.2.9

The gate refused where it should have asked.

Every previous release tightened this gate. This one loosens it, on evidence
that the tightening was built on a false premise.

## The premise

Every protected operation returned `deny`, and the refusal explained why:

> No capability can be attached to a host tool call, so there is no in-session
> approval.

The first clause is true. The conclusion does not follow, and the host's own
documentation says so in one line:

> `"ask"`: show the permission prompt to the user as normal

A capability cannot ride along on a tool call. The host has a confirmation
channel, and this gate never reached for it — through five releases of
tightening, and two rewrites of that exact sentence.

## What it cost

Reported, not theorised. Sessions in other projects hit `rm probe-tmp.mjs` on a
scratch file they had just written, `git checkout -- out/`, `taskkill` on a dev
server they had started, `npx tsc`, a Python heredoc, and `git commit --amend`
to fix a typo in a subject line. Each was a hard stop. Each became a command
typed by hand, or a workaround — one session rewrote its commands as
`node ./node_modules/.bin/…` to get past the gate, and another recommended its
operator remove the guard entirely.

A gate with one way to be careful spends the operator's patience on every false
positive, and a guard nobody keeps switched on protects nothing.

## What changed

| Tier | Before | Now |
| --- | --- | --- |
| R0–R2 | allow | allow |
| R3, R4 | deny | **ask** |
| R5 | deny | deny, or a staged capability |
| governance block | deny | deny, whatever the tier |

An exceeded ceiling and a run of skipped mandated steps carry no risk tier. The
first version of this turned both into confirmations — asking a session that
has stopped being trustworthy to approve itself, which is the failure those
signals exist to interrupt.

## Loosening exposed what refusing had hidden

Every delete scored R4 — a scratch file and `rm -rf /` alike. Identical
outcomes while everything refused; one keypress apart once R4 began asking. A
recursive delete aimed at a filesystem root or a home directory now refuses
outright, twelve forms of it, and an ordinary delete asks.

That is the general shape: **loosening a control converts every latent
misclassification underneath it into a live one.** The tiers had never been
tested, because nothing depended on them.

## Classification, corrected against real use

- `git restore` was a **database mutation** — the rule matched `drop`,
  `migrate`, `rollback` and `restore` as bare words anywhere they appeared, so
  `cat docs/migrate-notes.md` and `grep -rn rollback src/` were schema changes,
  while `psql -c 'DROP TABLE orders'` escaped because its SQL is quoted. It
  refused prose and missed the statement. Anchored now; `git restore` is
  `worktree-discard`.
- Ending a process was `unclassified-mutation`; `kill`, `pkill`, `taskkill`,
  `Stop-Process` and `systemctl stop` are `process-control`.
- `npx`, `npm ci` and `npm install` are local compute.
- Heredoc bodies are data. A newline ends a segment, so `import json` inside a
  Python heredoc was an unknown mutation. A command after the delimiter is
  still a command, and a substitution inside a body is still classified.

## Secrets, said aloud

The scan required a `:` or `=` and eight characters — right for a machine
token, wrong for every human phrasing. `password: 555345`, `my password
555345` and `the db password is hunter2` all returned no findings, and the
request ledger shipped in v0.2.8 records every prompt through that scan. A
credential typed into a conversation would have been written to the archive
verbatim.

Length is replaced by the shape of the value: a digit, or quotes. That keeps
`password manager` out, which matters because the hook swallows a refusal — so
each false positive would be a request silently not recorded.

## Checks that reported less than their names promised

- `config check` iterated a schema table rather than the tree, so
  `.godmode-docslint.json` — which governs this repository's own docs linter —
  was never validated. Discovery is by glob now.
- `config check` and `atlas diagnose` had carried "no breaking mutation written
  yet" in the falsification harness. Both have mutations; **no gate is
  unproven**. Writing the second is what exposed the first defect above.
- `recurrences` returned `{"checked": 0, "verdict": "no-recurrence"}` — a green
  answer from a scan that examined nothing. It says `insufficient-data`.
- Closing a request was unreachable from the command line: closure matched a
  digest the runtime writes and a person cannot supply.
- The census declared four kinds fewer than the archive holds.

## The prompt hook

`record_request` read every record on every prompt to reject a repeat: 1.1s
against 65 events, growing linearly, inside a hook the host kills at its
timeout. Deduplication moved to review, where it already happened.

Measured attribution for what remains, because it is worth knowing: bare
interpreter 299ms, runtime imports 440ms, resolving the project anchor **2.7s**
in git subprocesses. The anchor dominates, and the pre-tool gate pays it on
every tool call. On the machine measured, the cause is a virus scanner reading
a large binary on each spawn — so the largest available improvement is an
exclusion for `git.exe`, not a change here.

## Upgrading

Behaviour changes. Operations that stopped dead now prompt; two catastrophic
delete forms that were only refused because *everything* was refused are now
refused deliberately. If a workflow depended on the gate being a wall rather
than a question, it will feel different.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_field_reports     # every refusal reported by a user
python -m unittest tests.test_gate_falsifiability
python scripts/godmode.py --project . recurrences
python scripts/godmode.py --project . loop
```

That last command reports that `godmode_sentinel.py` has been repaired in six
releases and calls the cause structural rather than the next special case. This
release makes it seven. Every defect it fixes is a word the classifier matched
or missed — `restore`, `migrate`, `kill`, `npx`, a heredoc line, a password in
prose. The detector is right, and shipping this while saying so is better than
shipping it quietly.

## The scope a change declares

Everything this runtime did about blast radius answered the question after the
edit. `atlas affected` reports what breaks once a symbol is chosen. `inventory
diff` reports what moved once it has moved. `integrity` reads a diff that
already exists. All detection, and detection arrives too late to be the answer
to what an operator actually asks when they hand over one section of a
codebase: that nothing else move.

A plan may now declare `editable` — globs it is allowed to touch — and a
`Write`, `Edit` or `NotebookEdit` outside them is refused at the pre-tool
boundary. The declaration belongs to the change and expires with the plan.
Undeclared fences nothing, because a fence nobody wrote should fence nothing
rather than everything, and every project predating this keeps working
untouched. It asks rather than refuses: discovering that a change touches one
more file than expected is ordinary, and a scope that could only be widened by
rewriting a plan would be abandoned the first time it was wrong.

A **design boundary** is the opposite shape — it outlives every plan, and what
it protects is a decision somebody made rather than a correctness property. It
lives in `.godmode-boundaries.json`, it denies rather than asks, and it moves
only by staged capability, because a one-key confirmation in the middle of a
long run is the same keystroke as every other confirmation that session.

Declared globs enforce. `godmode boundaries propose-ui` reads the tree and
prints candidates for a human to accept or discard; it never writes the config.
Auto-detection as the *enforcer* fails three ways that matter: it freezes a
`.tsx` file that is pure server-side data loading, it misses a UI change made in
a plain route file, and its scope moves on its own when somebody adds an import.
A gate whose scope moves by itself cannot be audited.

The same declaration is asked of the result. `fence audit` checks every changed
file against what the plan said it would touch — covering what the boundary
cannot see: a shell command that rewrites a file in passing, an edit made before
approval, and everything done in a session where this plugin was switched off.
`fence acceptance` reports completions citing no evidence, quoting the
acceptance the plan declared, because `acceptance` had always been a field that
got filled in and read by nobody.

## Which build is enforcing

Every version surface here reads the tree — eight of them, the latest tag, the
tree a tag points at. None read the copy that is installed and actually refusing
tool calls, so there was no answer anywhere to the question that decides whether
any of this is in effect: which build is guarding me.

The version being developed and the version enforcing are different facts, and
only the first had checks. An installed plugin leaves no trace in the repository
it guards, so a gap between them is silent by construction.

The context brief now opens with the version and filesystem root of the runtime
that produced it. The root is there because a version cannot tell two installs
of the same number apart. It sits outside `records`, so the degradation ladder
cannot drop the one line explaining why every other line might be describing a
different build.

Reporting, not detection. What a drift check would compare against depends on
the project; naming the number is what was missing.

## Asked before the work, not after

`godmode precheck --about "<task>"` answers two questions the archive could
always answer and nothing ever asked: has this already been built, and was it
already refused. Both were answered wrong while this release was being written —
a sentinel allowlist came one command from being rebuilt after two shipped
releases had fixed it.

It reports where it looked and how much it examined, because an absence claim
needs the search that would have disproved it, and `nothing found` from a check
that examined nothing reads as clearance. Findings, never closures: prior work
is a reason to look, not grounds to decline.

Closures now say which they were. `already-built` and `refused` join the closed
statuses, because a plain `closed` covered both outcomes and the reasoning
behind every closure was being discarded. Existing closures stay closed and read
`unspecified`.

`atlas closure` names the dependents a change left untouched, bucketed so a
stale test and a stale caller are not one flat list. `atlas seams` reports
modules used by exactly one consumer — one adapter is a hypothetical seam, two
is a real one. The deletion test that accompanies that rule is not computable
from an import graph, so it is asked rather than pretended at.

## An ask the agent supplied

Requests now carry `source`. The prompt hook only ever writes `stated`;
`inferred` is for an ask the agent records on the operator's behalf. A detector
reports an inferred request still open with no work recorded after it.

The test is deliberately not whether the guess was wrong. An assumption that
shapes the work is ordinary and often right. An assumption that *stops* the work
spends the operator's turn on a question they never raised. It is the first
detector here reading a claim about the operator rather than one about the
repository, and the failure is the same either way: an inference given the
standing of a fact, and then acted on.

## Four more of one shape

Every defect fixed late in this release was the same one — a mechanism that
exists, a report that points at it, and using it changing nothing.

- `remember --kind request` was rejected by argparse, so the closure every open
  request report recommended errored out. The digest fallback shipped earlier to
  fix this exact shape; it recurred one layer up in the command line.
- A request written by hand carried no digest and defaulted to `active` while
  every reader filters on `open`: recorded, and read by nothing.
- `inferred-ask-blocking` watched for `build`, `verify` and `attest` — commands,
  not record kinds. Only `plan` among them exists, so the check matched almost
  nothing in production while every test passed against a fake ledger that
  accepts any kind. Guarded now by an assertion that the watched set is a subset
  of `EVENT_KINDS`, and by one test through the real archive.
- The same mistake was caught in `fence acceptance` while it was being written,
  which selected `kind="build"` for the same reason.

A test double more permissive than the real store does not merely miss bugs. It
manufactures confidence, and this repository already knew that: `ArchiveContractTests`
exists for exactly this reason and was not consulted.
