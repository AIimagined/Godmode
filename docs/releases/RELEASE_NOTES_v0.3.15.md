# Godmode v0.3.15

The depth release: eighteen changes with one spine - depth that cannot be
silently skipped, and shallowness that cannot pass for verification.

The claim ledger stops taking words for evidence: a doc: citation must
mention the claim it supports or it is named as decoration; a hypothesis
names its falsifier (`--refuted-by`) or the gap is named; a universal
claim (every/all/100%) enumerates its lanes - a grep proves existence, an
enumeration proves coverage; a sweep verdict states its reading depth; and
`claim --verify` collapses the verify-then-claim two-step, running every
cmd: citation through the attested checker in one command. Withdrawing a
claim as failed now asks what was built on it while it stood.

Enforcement honesty: "the CLI refused this" and "the host itself blocked this"
are different statements, and capabilities now says which is which -
CLI-bound controls read HARD-IN-CLI, with the cap reason named, on any
host without a live interception proof. A charter compiling zero rules
says so at session open. A clean-diff inventory baseline no longer warns
on age alone.

The write-time detectors grow four: a build-shaped duty overlapping a
shipped capability names the elder ("reuse it, or say what differs");
the post-edit hook pushes an edited file's recorded invariants,
incidents, and prior fixes at the edit moment, before the regression;
a correction-shaped prompt - the operator catching a miss - draws a nudge
to record it while the evidence is fresh; and a completed checklist row
without a runnable command in its evidence is named a suggestion, not a
gate. THE RATCHET RULE joins the doctrine as its eighth reflex: a miss
that recurs gets a guard, not a lesson.

Field fixes: the orientation screen states the one resolvable invocation
(godmode is not on npm, and a guessed `npx godmode` now lands loudly);
operator asks surface as their own words in spoken order with a
paste-ready closure, not a hash and a keyword bag; a progress report
("still running", "so far") no longer arms the done-bar; passing the
done-bar by rewording draws a named advisory on the re-fire; and two
skills sharing a name - a collision the host resolves silently - fail
`godmode skill names`.

And the release closes its own loop twice over: the push preflight now
surfaces every open stated operator ask as a finding - a cut over an
operator-named set is the goal-misread class, caught by machinery instead
of memory - and fetch-class tool output carries a once-per-session
untrusted-data notice, the one output-governance import the full
upstream-repo sweep produced.

## Verifying

- `python -m unittest discover -s tests` — the full suite (3,183 tests).
- `godmode claim "the suite is green" --verify --cite "cmd:python -m unittest tests.test_digest"`
  — one command: check attested, claim recorded on it.
- `godmode claim "every lane is covered" --cite "file:README.md"` — watch
  the universal-claim advisory name the enumeration bar.
- `godmode capabilities` on a host without interception — CLI-bound
  controls read HARD-IN-CLI with the cap reason.
- Edit a file the archive has records about — the post-edit line names
  the newest recorded fact and the `context why` command for the rest.
