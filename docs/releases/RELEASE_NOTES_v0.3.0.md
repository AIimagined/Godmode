# Godmode v0.3.0

The record is the headline. The gate is one consumer of it.

Every manifest, the listing kit and the README now describe Godmode in one
sentence whose every clause names a shipped mechanism with a test behind
it: *a local, tamper-evident record of what a coding agent did, what it
claimed, and what was verified.* This release is what makes that sentence
true for more than one agent, across a history rewrite, and on the public
surfaces where prose used to escape the claim gate. Fifty-four changelog
fragments fold into it - thirty-four added, twenty fixed - and every one
was written before its commit, per the changelog gate this repository
enforces on itself.

## What an agent did, recorded beside what the host decided

Every host adapter already lifted the host's own sandbox and approval
metadata onto the event it built, then dropped it. The host's approval
decision is now a first-class record beside godmode's own, and `godmode
approvals` surfaces the disagreements in both directions: what the host
allowed that godmode would have refused, and the reverse. Cooperating with
host controls stopped being a sentence and became a table.

The interception proof is truthful now. `tool_call_interception` reports
one of five levels - `UNAVAILABLE`, `SOFT`, `PARTIAL`, `HARD`, `DEGRADED` -
and `HARD` needs a live, chronicled proof, not an environment variable. A
published claim is withdrawn in the same breath: `hooks probe` reaching
`HARD` was read as evidence that a host's runtime calls the gate, and the
probe self-injects, so it proves the script and not the wiring. The README
host table says which hosts are proven and which are not. Native per-host
hook manifests are generated from `packaging/hosts.json` by the same
mechanism as every identity manifest, and a git-hook backstop (`hooks
install|status|verify --git`) enforces on any host, including ones that do
not exist yet.

## More than one agent on one record

Every record carried a host and a model, which stops being an identity the
moment two agents share both. Each agent now declares an identity
(`GODMODE_AGENT_ID`, else derived), takes exclusive leases on the paths it
is working, and records who dispatched whom. A lease held by another agent
and a delegation that would make an agent its own ancestor are refused at
write time. Leases carry a term and lapse by the clock, so a stopped agent
does not hold a path. `godmode fleet` shows the state.

## A record that survives its own history being rewritten

A claim graded against `file:src/api.py` kept its grade for the life of
the archive while the file changed underneath it. `reanchor` names
citations that came loose - cited files committed over since the record
was written, `commit:` citations whose object the repository no longer has
- and reports without regrading, because a stale citation and an
unsupported claim are different facts. Before a history rewrite, `reanchor
--snapshot` fingerprints every cited commit by tree, subject and author
date; after it, `--remap` finds each one's new sha. A scrub that would have
orphaned every commit citation now moves them.

Restore points are attested rather than inferred: a green carries the
command, its exit code and the commit it ran against, and a failing run
cannot mark one. `rollback` names the last green, what changed since, and
hands over a non-destructive command. `forecast` says what an operation
would classify as, with precedent from the refusal corpus; `replay`
re-runs every recorded operation against today's rules and separates
tightenings from relaxations, because a relaxation is the one outcome that
means a rule went backwards.

## Governance proposed from the record, never installed by it

The skill forge pivots to evidence-derived governance: `godmode governance`
proposes rules from the project's own refusals, requests and attestations,
under three guardrails that are structural rather than conventional -
propose-never-install, tighten-only, provenance-and-expiry. The recurring
ask miner is layered, not reimplemented. The minimality report gains a
ceiling: `minimality --set-baseline` records the counts, later runs
compare, and growth exits non-zero until it is answered for with
`--accept-growth <section> --reason ...`, so added surface carries the
reason it was added.

## Ten capabilities that were unbuilt, built

The register carried ten `unbuilt` statements. Each now has an
implementation pointer and a test pointer that resolve, and the register's
debt list is empty for the first time.

- `quality` folds the docs lint, the swallow scanner and the minimality
  report into one severity-ranked list, worst first. Remedies are
  proposals; the command executes nothing, and a test pins the tree
  byte-identical after a run. `--format editor` and `--format sarif` give
  an editor the same findings.
- `freshness` checks `file:` and `commit:` citations locally and reports a
  `url:` citation as unverifiable, never fresh. `partial` names what was
  not checked and is not a failure.
- `--terse` puts the next action on line one.
- `skill forge` writes an expected-output fixture per host; `skill
  validate` refuses a forged skill missing one.
- `examples --check` reproduces every worked example against the real
  console in a throwaway project.
- `extensions run <name>` runs an extension only when the project's policy
  names it; `extensions list` imports nothing.
- `watchdog` names a repeated operation, a refusal burst, or an unattested
  run, on demand, with no daemon; `--interrupt` writes the operator-stop
  flag the stop algebra already honours.
- `arbitrate` scores competing plan files and returns `undecided` on a tie
  rather than breaking it.
- `docs/LADDER.md` is four tiers of onboarding, parser-walked; `guide
  --tier N` prints one.

## The claim gate reaches the public surfaces

The gate downgraded an unsupported claim, but only one that went through
`godmode claim`; a sentence typed into the README never met it. `claim
--scan` lists every claim-shaped sentence on the public surfaces - a
measured number with a unit, or a verb that promises an outcome - whose
line names no reproduction and no claim record carries. A test runs it
over this repository with an empty archive, so the prose must cover
itself. Its first run found two measured latencies whose only basis was
"same source"; both now link the release notes they came from.

## The session's own cost, measured and capped

What godmode injects per session is measured and capped (`brief` reports
per-section costs, counts only). The resume digest answers the first
question a resuming agent asks - was I mid-task? `context structure`
builds a bounded structural outline; `trends` renders per-session
measurements as counts. The console's exit contract is enforced at the
dispatcher - 0 ok, 1 findings, 2 error - so a command that reports a
failure in its body cannot exit 0, and commands added later inherit the
contract without opting in.

A cache miss in `resolve_anchor` cost six git spawns, seven with a second
remote, each with a five-second timeout - exactly the budget the host gave
the prompt hook before killing it. It is three spawns now, and the prompt
hook, which records the operator's ask and returns nothing, is declared
asynchronous in the manifest.

## Security

SEC-A, an external audit's four fail-open defects, is fixed and pinned.
The gate refuses when the authorization policy file cannot be read, and a
policy file mid-rename is not a malformed policy file. Codex's
`apply_patch` is read in both of its shapes - a body under `command`, and
an argv array. The recovered field-ask corpus (twenty-eight commands from
real governed sessions) is a formal regression corpus, and the two highest-
frequency friction classes in it are fixed.

## Verifying

```
python -m unittest discover -s tests
python -m unittest tests.test_quality tests.test_freshness tests.test_watchdog tests.test_arbitrate tests.test_extensions tests.test_examples_corpus tests.test_claim_scan -v
python -m unittest tests.test_fleet tests.test_reanchor_snapshot tests.test_rollback tests.test_forecast tests.test_host_approval -v
python scripts/godmode.py --project . capabilities --reconcile
python scripts/godmode.py --project . claim --scan
python scripts/godmode.py --project . examples --check
python scripts/godmode.py --project . docs --lint
python scripts/godmode.py --project . version --reconcile
```

The full suite at the release commit ran 2672 tests OK, one skipped, as
four module chunks summed (`python -m unittest discover -s tests` reports
the same total in one run). `capabilities --reconcile` reconciles clean:
81 capability entries - 63 built, 7 partial, 11 rejected, 0 unbuilt - 14
detectors, 29 coverage rows, zero dead pointers in any direction. `claim
--scan` reads `covered`; `examples --check` reads `reproduced` over four
examples; `docs --lint` is `clean`; the charter compiles 16 rules, 7 of
them HARD, each owning a plant that watches its guard go red. `version
--reconcile` agrees once this release is tagged; on the untagged tree it
reads drift on the tag surfaces by design, as every release before it did.
