# Godmode v0.2.12

A release where every claim about the product is held to the product's own standard.

Godmode ships mechanisms that force a claim to earn its grade: a witness plus
an independent checker before "fixed" is admissible, a citation that has to
resolve against something real, a register that remembers what was already
rejected. This release turns that standard on the release itself. Every
number in this document is a citable output of a command run against this
repository, not a summary written from memory — the same discipline the
shipped code now imposes on every other claim a session makes. What follows
is the whole absorbed-capability program landing in one release: admissibility
and eval rigour, temporal verification, evidence discipline for read-only
operations, budget-real termination, graduated postures, and a set of reports
that state their own limits before anyone else has to point them out.

## Claim admissibility, from one signature to a panel

A "verified" claim used to mean a self-reported grade. It now means a
`verdict` record: a claimed value, a data-only witness, and an independent
checker that recomputes from the witness alone and asserts against the claim.
Three dispositions, never two — `confirmed`, `refuted`, `witness-malformed` —
with a missing witness or a checker that cannot run stored as "never judged,"
not folded into "judged false." Two invariants are refused at write time: a
self-acquitted `confirmed` (an independent checker is not optional), and a
`confirmed` disposition on a run whose own record says it was cut short by a
budget (`godmode verdict record|show`).

Where reviewers disagree, a single checker is not enough. `--checker` is now
repeatable — a panel, each member running independently against the same
witness — folded to one disposition by a closed rule, never a score: every
checker confirming reads `confirmed`; a refutation alongside a confirmation
reads `contested`; no confirmation at all reads `refuted`; and a panel where
nothing could judge anything reads `witness-malformed`. The archive itself
refuses a `confirmed` record whose own `checks` field carries a refuting
entry, whichever code path produced it (`godmode verdict record --checker
<cmd> [--checker <cmd> ...]`).

## Temporal verification: a fix has to have seen the failure first

A "fixed" claim citing a command is now checked for shape, not just presence:
was that command observed failing before the last edit and passing after it.
The check reads the session transcript's own tool-result outcomes — digests
and pass/fail only, nothing about what the command printed — and downgrades
a claim with the reason named ("cited test was never seen failing before the
fix") when the red-then-green shape isn't there. A claim citing no timeline
at all is left untouched: absence of the instrument is a stated gap, never a
penalty. Alongside it, a criterion can be pre-registered before work starts
(`godmode criterion`) and cited back from the claim that closes it; a weak or
late-registered criterion surfaces as an advisory, not a downgrade. Plan
contracts now carry their own executable acceptance commands
(`accept: ["cmd:<command>", ...]`), and a session cannot close while any of
them lacks a this-session pass.

Root-cause claims get the same treatment from the other side: when two
comparable states already exist in the archive, a root-cause claim without a
differential between them is inadmissible. A new `differential` record
(`godmode differential record --subject ... --a <ref> --b <ref> --delta ...`)
is the citable comparison; the detector fires only once two comparable
records actually exist, so a claim made where nothing comparable was ever
recorded reads as a stated gap, not a violation.

## What a number is allowed to cite

A numeric claim about a named metric can now be locked to the one output
shape it's allowed to quote (`godmode metric-contract register --name <name>
--anchor <regex>`); a claim citing that metric with a different value is
downgraded naming both numbers. Anchor safety is checked twice, independently
— pattern compilation and a length cap at registration, and a hard 64-character
cap on the matched value at grading time — because a pattern that passes the
first check can still be made to hang the interpreter on a long enough input,
and the two checks close different halves of that gap.

## A register that remembers what was already rejected

Findings, fixes, and rejected approaches now have a place to live past the
session that produced them: a disposition register
(`established`/`superseded`/`refuted`/`worse-than-baseline`/
`matched-baseline`/`rejected-precedent`/`open`) over evidence-cited records,
with an unlisted key reading as the explicit default `open` rather than an
error. Every non-open entry needs a real citation, checked twice — once when
it's written, once again at the archive's own append boundary, so a
hand-crafted record cannot slip past the API that would have refused it.
Transitions are legal-only: a closed disposition can only become
`established` again by a new record naming exactly the one it supersedes.
When a task's own terms match a `rejected-precedent` key, `precheck` now
names the precedent and the two ways through: cite it and supersede it, or
drop the approach. A file-carried, opt-in exchange lets one project's register
entries travel to another as advisory-only foreign precedents — never
promoted to a project's own binding register without one explicit, human-run
`adopt` step, and never counted toward that project's own conflict checks.

## Surgical-diff fencing and a pinned evaluator

The existing scope fence now also reads the diff itself. `fence audit
--complete` parses the working diff into hunks and tells apart three shapes: a
hunk that changes lines in a file outside the declared editable set, a hunk
that only removes lines there (told apart because removing code nobody
declared as theirs to touch is a different problem than adding to it), and a
stray debug marker landing anywhere at all, in-scope or not. A project with no
approved plan sees none of this — the fence stays fail-open exactly as it
already was.

Whatever judges a change can now be pinned so the change can't be optimized
against it: `godmode protect --pin <path>` freezes a file, checked before the
scope fence even runs, so a pin always outranks a fence allowance. Unpinning
is gated the same way a forced push is — refused outright without a staged
capability. A pinned file mutated by a route the hook never saw is still
caught, on the next integrity pass, by comparing against what the archive's
own pin set would have produced.

## Termination that means it, and a ledger for what was tried

A composable stop algebra (`MaxRecords`, `MaxWall`, `OperatorStop`,
`MetricPlateau`, composed with `&`/`|`) replaces ad hoc loop conditions with
predicates that can be reasoned about and are spent once fired — asking a
fired stop again without resetting it raises rather than silently
re-answering. A bounded attempt that overruns its wall-clock budget is killed
outright, tree and all, and the result is marked `truncated` — a shape the
verdict seam already refuses to let anyone call `confirmed`. Two consecutive
empty checkpoints produce a blocking redirect finding; four produce a
governance halt that only an operator-sourced record can clear, never an
agent's own inference about its own state.

Alongside it, every experiment cycle is now commit-linked and adjudicated
before the next one is allowed to start: `run_experiment` refuses a new cycle
until the last one has a verdict, and an epsilon threshold decides keep versus
discard — with a declared-but-flat, declared-simpler result the one exception
that keeps without meeting epsilon, never a regression rescued by "simpler"
alone. Scenario coverage and eval definitions are now versioned against a
pinned digest registry, so an edited scenario left at its old version number
surfaces as a blocking drift finding instead of looking untouched.

## Content trust, extended to what a host loads and follows

Trust scanning covered settings and MCP configuration; it now also reads
`skills/`, `commands/`, and `agents/` content the same way, because that
content is prose a host loads and follows the moment a session starts, not
configuration a host merely parses. An instruction-shaped line inside any of
those files is now a named finding, the same as it already was for settings.
Godmode's own six shipped skills are the population check: they run through
the new scan as part of the suite and return no findings.

## Measurement that counts, and reports that refuse to claim more

Session measurement streams a host's own transcript and tallies tool calls,
commands, test runs, and token usage — counts and a closed set of names only,
capped and content-free by construction. A counts-only ROI report folds that
against gate activity and verdict dispositions into one view — denials,
asks, contested-versus-confirmed verdicts, a session with no measurement
record stated as unmeasured rather than interpolated to zero — and is held to
a checked denylist of attribution language, so it cannot claim savings it
never measured. Observe mode extends the same discipline to enforcement
itself: a policy-declared posture converts every deny/ask into a recorded
advisory instead of a block, announced loudly at session start, entered only
by an exact policy-file edit — and its own digest command renders what would
have been caught without ever calling that a saving.

Graduated starting profiles (`init --profile novice|standard|strict`) set a
starting posture on the same tighten-only ratchet everything else here
respects: a profile can widen what asks for approval, never remove a category
an operator or an earlier profile already made explicit. Recurring-ask mining
folds a session's own request ledger into SOFT charter-rule candidates when a
normalized ask recurs across enough sessions — candidates only, promotion
stays a human decision, and the original request text never reaches the
report, only its normalized terms and session references.

## The release held itself to the same standard

`capabilities.json` now enumerates 81 capability entries against this
repository's own private sprint ledger — 50 built, 19 unbuilt, 7 partial, 5
rejected — each `built`/`partial` entry carrying the file and test that back
it, and reconciled in both directions: a `built` entry whose pointer stops
resolving is dead, and an `unbuilt` entry whose pointer starts resolving is
stale the moment the code lands (`godmode capabilities --reconcile` exits
non-zero on either). `godmode assess` surfaces the 19 unbuilt ids as
`capability_debt` rather than hiding them, and the assessment's own verdict
on this repository is `at-risk` — reported, not smoothed over, because
several proprietary role documents this project's own convention gitignores
are honestly absent from a fresh checkout.

Dogfooding follows the same rule: this repository's own five live HARD
charter rules are now provably planted, each against the specific test that
already exercises the line it guards (`assess.charter.hard_unplanted == []`),
and all 19 of its advisory rules carry a real, rule-specific review decision
(`assess.charter.advisory_unexplained == []`) rather than sitting unreviewed.
A fabrication-pattern detector catalog names all 14 live mistake-class
detectors against the function and test that back each one, and records the
gap plainly where a numbered class was never built rather than implying full
coverage. A capability-coverage table answers, in godmode's own vocabulary
across 13 rows, what's `covered`, `partial`, or explicitly `not-claimed` —
prose-restyling and token-burn reduction stated as roadmap only, not
mechanized, so nobody assumes it from omission. A one-command minimality
report aggregates duplicate/orphan symbols, speculative seams, and
unexercised surfaces that already existed as separate checks — aggregation
only, no new analysis. And a two-minute demo script walks five real CLI
commands in order, every one pinned against the actual console parser, with
every quoted number carrying its own basis and no causal language anywhere
in it.

## Fixed

- **A clean-scan claim over files never opened.** The untrusted-content walk
  capped itself at 400 files and stayed silent about the cap; once a project
  grew past it, a file sorting later in the tree could go entirely unread
  while the scan still reported clean. The walk now counts every candidate
  before capping, reports the true count and a `truncated` flag when it
  applies, and a `truncated` scan can never report as a clean sweep — the
  default cap also moves from 400 to 2048, roughly double this repository's
  own current file count, for headroom before the gap reopens.
- **Two independent freshness-ranking instruments, each now stable within its
  own mode.** Context ranking's freshness tie-break read raw filesystem
  timestamps, which neither a git checkout nor a non-git copy preserves in a
  content-derived order — two checkouts of the same commit could rank
  identical content differently, purely from copy timing. A git-tracked
  project now reads the file's last commit time; a non-git project falls back
  to a deterministic path sort. Each is now proven stable against shuffled
  timestamps within its own mode; the two instruments are not claimed, and
  are not required, to agree with each other on tie order for the same
  content across modes — a ranking snapshot has to be generated and compared
  in the mode it will be evaluated in, which is now stated directly in the
  ranking function's own contract.
- **A real-denial counter that counted zero real denials.** The ROI report's
  denial count only ever read one archive-record convention that no shipped
  code had written to since an earlier release started recording gate
  refusals under a different record kind. This repository's own archive held
  hundreds of real refusals the report reported as zero; it now folds both
  record kinds, disjoint by construction, so no refusal is double-counted and
  none goes uncounted.
- **Sixteen of nineteen advisory charter rules had never been through their
  own review command**, and the repository-state test asserting that review
  exists could never pass on a fresh checkout, where no review record exists
  yet. Every rule now carries a real, rule-specific decision; the test
  degrades to an explicit skip on a fresh checkout instead of failing where
  it structurally cannot pass, and asserts fully once real records exist.

## Deliberately not built

Prose-restyling and token-burn reduction are stated `not-claimed` in the
capability-coverage table, not silently absent from it. Godmode measures burn
and bounds its own context budget; rewriting a host's or a model's output to
use fewer tokens is a host output-style concern, and claiming it here would
be exactly the kind of unearned grade this release exists to refuse.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_verdict tests.test_red_before_green -v
python -m unittest tests.test_disposition_register tests.test_termination_algebra -v
python scripts/godmode.py --project . capabilities --reconcile
python scripts/godmode.py --project . assess
python scripts/godmode.py --project . docs --lint
python scripts/godmode.py --project . untrusted --brief
python scripts/godmode.py --project . version --reconcile
```

`godmode capabilities --reconcile` reconciles clean on this repository: 81
capability entries, 14 detectors, 13 coverage rows, zero dead pointers in any
of the three. `godmode assess` reports `hard_unplanted: []` (5 of 5 HARD
rules planted) and `advisory_unexplained: []` (19 of 19 advisory rules
reviewed), alongside the honest `at-risk` verdict and its 19-entry
`capability_debt` list. `docs --lint` is `clean` (32 advisory notes, none
blocking) and `untrusted --brief` is `data-only`. Run
`scripts/dev/run-suite.ps1` for a fresh sharded run of the full suite.
