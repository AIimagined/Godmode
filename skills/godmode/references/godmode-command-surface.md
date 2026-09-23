# Godmode command surface

Generated from the CLI's own parser; regenerate rather than hand-edit when
commands change (`docs --reconcile` guards the drift). Global flags `--brief`
and `--json` work on every command and may appear in any position;
`GODMODE_MODE=guided|standard|expert` changes exposure, never enforcement.

| Command | Purpose |
| --- | --- |
| `absorb` | Check whether a synced file is truly absorbed (reader + guard) |
| `actions` | Read capability audit events |
| `adopt` | Relink records stranded by an identity change (e.g. git init) |
| `assess` | Grade whether this project's own rules can be complied with |
| `assurance` | Emit an assurance case generated from live probes |
| `atlas` | Map the project's symbols and their relationships |
| `attest` | Record that a mandated step ran, found nothing, or was skipped |
| `authorize` | Configure or issue local capabilities |
| `benchmark` | Measure brief budgets and timings, locally only |
| `bindings` | Generate host manifests from one source |
| `branches` | Inspect branches and worktrees |
| `brief` | Assemble a bounded, model-independent context brief |
| `build` | Record an implementation result |
| `capabilities` | Report what this host can actually enforce |
| `ceilings` | Check reported spend against declared run ceilings |
| `changelog` | Fragment-based release notes |
| `charter` | Compile prose guidance into addressable rules |
| `checklist` | Update a cumulative private check |
| `checkpoint` | Record a recoverable handoff point |
| `checksums` | SHA-256 manifest over every tracked file |
| `claim` | Record a claim; unsupported claims are downgraded, not warned about |
| `config` | Validate every .godmode-*.json config file |
| `context` | Inspect or rebuild context continuity |
| `db` | Record database governance state |
| `digest` | The archive told as dated prose - what happened, in order, assembled verbatim from record fields |
| `docs` | Record documentation obligations, or reconcile the trigger table |
| `doctor` | Verify archive and continuity health |
| `drift` | Compare step sets across sessions and agents |
| `egress` | Disclose exactly what an action would send |
| `environment` | Classify a mutation target's blast radius; unknown fails closed |
| `evals` | Execute the authored skill evals: routing accuracy plus snapshot diff |
| `experiment` | Run the declared bounded experiment loop from .godmode-experiment.json |
| `explain-context` | Explain included and excluded continuity data |
| `export` | Write a sanitized context report |
| `forget` | Expire old episodes into a cold, still-chained segment (action and refusal after 30 days, attestation after 90; a record cited by a live claim, a checkpoint, a law guard or a pin never expires); report supersession chains; flag same-subject value contradictions |
| `gate` | Check a trigger; exit non-zero when a HARD rule is unattested |
| `grid` | Attack every enforcement control; report each cell's observed result |
| `guard` | Preview and authorize an exact operation without executing it |
| `history` | Read structured local history |
| `init` | Initialize the private local archive |
| `inspect` | Capture an on-demand repository snapshot |
| `integrity` | Run the thirteen test-integrity monitors over the current diff |
| `inventory` | Repository inventory operations |
| `lessons` | The promote-or-retire pipeline over recorded lessons |
| `locale` | Localized guidance surfaces |
| `loop` | Detect repetition the repeating agent cannot see |
| `method` | Select an analysis method from the evidence shape |
| `mistakes` | Run the mistake-class detectors |
| `netgate` | Prove the CLI surfaces make zero network connections |
| `observe` | What an observe-mode trial recorded - tier-shaped would-have counts; `--report` lists the decisions themselves |
| `operator` | Validate the typed operator profile |
| `ownership` | Show which gate rule owns each path or command, and refuse a stale decision table |
| `parity` | Compare neutral structure with an explicit local reference |
| `perimeter` | Perimeter checks (a boot, an import walk, a typed route) that must run before `session close` |
| `plan` | Record a private execution contract |
| `planmode` | Gate mutation behind an approved plan contract |
| `plant` | Prove a guard fails by planting a violation |
| `privacy` | Audit the local privacy boundary |
| `quality` | Every quality finding - docs, swallowed errors, minimality - worst first, with a proposed remedy each; executes nothing |
| `ratchet` | Run the project's declared debt counters, record each value, name every counter that rose |
| `recurrences` | Find controls that blocked twice on the same cause; --against matches a report to the fixed registry |
| `reflect` | Check a claim against what the record already says |
| `release-notes` | Build a version's release note from its CHANGELOG section, or check one: present, covered, no empty section, no narration, a Verifying section |
| `remember` | Record a decision, invariant, lesson, or obligation |
| `removal` | Remember why something was deleted |
| `report` | Emit a sanitized bounded report |
| `retest` | Every test that pins a changed file, as one command per runner; --run attests it |
| `resume` | Build a bounded continuity brief |
| `rewind` | Preview a rollback to a prior verified checkpoint |
| `roi` | Counts-only ROI report: burn beside gate activity, no causal claims |
| `roles` | Resolve authority documents by role |
| `sbom` | List what ships and what it depends on |
| `scenarios` | Stage known failures and check a control notices |
| `scope` | Enumerate the work before reasoning about it |
| `selftest` | Exercise every control and report what actually held |
| `session` | Open or close an attested session |
| `skill` | Validate or forge a project skill |
| `slice` | Read a bounded window that declares its own edges |
| `sprint` | Record private sprint state |
| `status` | Single writable status store |
| `untrusted` | Report repository text shaped like an instruction |
| `verdict` | Run an independent checker against a witness; the claim's admissibility |
| `verify` | Run a declared check and attest its exit code |
| `version` | Record a version fact, or reconcile every surface |
| `watch` | Per-boundary anomaly scan over this session's attestations |

Run `bin/godmode <command> --help` (`bin/godmode` probes python3, then python, then py; `bin\godmode.cmd` on Windows probes py -3, then python, then python3) for flags and sub-verbs.

## `atlas law`: falsification bonds gate ratification

`atlas law propose --target <path> --diff <file> --cite <ev>` records an
`improvement_proposal` (capped at 12 open at a time - evidence quality,
never truncation; ratifying one frees its slot). `atlas law bond-test
<name> --command <cmd> --file <path> --replace <old> --with <new>` reuses
`plant`'s green -> red -> green proof against a synthetic bad case in the
same file the proposal names, and records a `checker_bond`. `atlas law
ratify <proposal-seq>` writes an `improvement_verdict` only when: the
caller itself currently holds an operator-granted checker session; a
passing, not-yet-consumed bond ran in THIS session, written by this same
caller, targeting the proposal's own file; and the proposer is not the
same actor (fingerprint, not role) as the checker; otherwise it is refused
with a named remedy. With `GODMODE_AGENT_ID` undeclared, every process
shares one fingerprint, so `ratify` cannot succeed until per-agent ids are
declared.

## `lessons promote|approve`: structured lessons graduate through approval

**`law compile` admits a guarded lesson two ways, and only two:** the
record carries approval lineage (`approval_seq`, which only `lessons
approve` mints), or it was written with operator trust (`--as-operator`
with its verification). An agent's guard needs a second actor; an
operator's guard is the second actor. A guarded lesson appended by an
agent with neither is not law, whatever its `status` says.

A lesson's structured schema (`remember --kind lesson --root-cause <r>
--correction <c> --reflection <x> --guard <g> --falsifier <f>`) missing any
of its five fields is written as `status: candidate` - never refused; a
plain `--guard`-only lesson (enforce predicates, standing guards) is the
pre-existing advisory shape and is untouched by that write-time rule. It
does not need to be: promotion is where the schema is mandatory. Any of the
four structured flags on a non-`lesson` kind is refused, never dropped.

`lessons promote <lesson-seq> --cite <ev> --rerun-hash <h>` writes a
`lesson_promotion`, refused (naming the missing fields) when the lesson at
that sequence is not fully structured, when it is not a `candidate` (an
already-active or retired lesson has nothing to graduate), when it is no
longer the newest record for its subject, with no citation, or with a
`--rerun-hash` that is not a sha256 digest. `lessons approve
<promotion-seq> --rerun-hash <h>` writes a `lesson_approval` and graduates
the lesson: a fresh record, same subject, `status: active`, carrying the
`approval_seq` the compiler reads. It is refused when the approver is the
same actor as the promoter (fingerprint, not role), when `--rerun-hash`
repeats the promotion's own (the checker merely re-cited the author's
re-run), when the promotion has already been approved (named, with the
first approval's sequence), or when the promotion is stale - the subject's
newest record is no longer the promoted one. That last rule is what stops
an approval undoing a retirement: retirement is the documented way to lift
a bad guard, and a promotion minted before one may not be approved after
it. A refused approval writes nothing.

Actor is always Task 5's own `agent_id()`; neither verb accepts an actor
override. The three-session correction/instruction ladder (`law promote
--candidate <seq> --guard <g> --subject <s>`) feeds this same pipeline
instead of writing an active law directly - its five structured fields are
synthesized from the cluster's own counters, so a ladder promotion passes
the completeness check on bookkeeping rather than authored analysis.

## Skill-impact ledger and the strict-improvement gate

Every skill or law proposal's before/after score and accept/reject outcome
is recorded as a `skill_impact` {target, diff_hash, score_before,
score_after, outcome, patterns}. Two writers: `atlas law ratify` and
`skill forge`. When a proposal's `target` is a `skills/<name>/...` path,
`atlas law ratify <proposal-seq> --diff <file> [--pattern <seq>]` needs
the SAME diff `propose` hashed; it applies that diff to `target`, scores
the skill before and after with the eval harness's own per-skill numbers
(routing score and behaviour-assertion pass rate, averaged), and accepts
only on a STRICT improvement over the best `score_after` any earlier
accepted change for this same target ever recorded (or, with none, over
this change's own before-score). Anything else - a tie or a regression -
is refused: the target is restored to its pre-change bytes (never the
operator's own `git checkout`) and the attempt stays recorded with
`outcome: "rejected"`. `skill forge --pattern <seq>` is gated the same
way, with `score_before` fixed at `0.0` (the skill did not exist before).
Either way, a later proposal whose `--diff` hashes to a previously
rejected `skill_impact` is refused outright, naming that record's own
sequence - the proposer is expected to read this ledger before proposing
again.

Three refusals sit in front of all of that, and each has a reason:
`--target` is recorded under ONE canonical spelling (separators, `.`
components and, on a case-insensitive filesystem, filename case), so
respelling a path does not buy a fresh start after a rejection or hide the
best score already recorded for that file; a target that IS one of the
skill's own grading inputs - its `godmode-evals.json`, whether or not one
exists yet, or any file a behaviour assertion's `check.command` names - is
refused, because a change to the thing that grades it cannot be graded by
it; and `--pattern` values are checked before anything is written, so a
malformed citation costs a refusal rather than an unrecorded change. A
target outside `<project>/skills/`, an absolute one, one containing `..`
and a directory are all refused the same way.

## Record verbs: one shape

Every verb that writes a record from text you dictate - `remember`,
`checkpoint`, `attest`, `claim`, `build`, `plan`, `criterion` - takes that
text in one shape, two spellings that mean the same thing:

| Verb | Positional | Named flag | Always required with it |
| --- | --- | --- | --- |
| `remember` | `"<whole record>"` | `--value` (`--subject` labels it) | `--kind` |
| `checkpoint` | `"<summary>"` | `--summary` | `--status` |
| `attest` | `<step>` | `--step` | `--status` |
| `claim` | `"<claim>"` | `--text` | - |
| `build` | `"<summary>"` | `--summary` | - |
| `plan` | `"<title>"` | `--title` | `--step` |
| `criterion` | `"<pass condition>"` | `--text` | `--task` |

The rules, enforced once in the console (`_one_text`):

- Positional or flag, either alone records; both with the same text is one
  record; both with different text is refused as ambiguous, never picked.
- Neither given is refused with the verb's paste-ready line.
- `remember` derives `--subject` from the opening words when it is not given.
- `--evidence` is repeatable on every record verb; on `claim` and `criterion`
  it is the same flag as `--cite`.
- Fixed-form records (`removal record`, `register set`, `metric-contract
  register`) name every field by flag and take no positional; that is the
  one deliberate exception.
- `remember --kind pattern` additionally needs `--class` (one of the closed
  failure-class vocabulary `record_incident`'s `--failure-class` shares)
  and `--occurrence seq:<n>` naming the record that shows this instance; a
  second occurrence on the same subject appends a new record rather than
  duplicating - `history --kind pattern` lists every occurrence as its own
  record (the evolution log), `index patterns` folds them to the latest
  record per subject (the index).

## `atlas loop`: signature-based halt on a retry loop

`atlas loop advance --task <id> --failing <ids…> [--diff-from-git]` records
one retry attempt's failure signature (a hash of the failing test ids plus
the shape of the diff that produced them) and its remaining budget. Budgets
- an operator's own stop flag, then steps, tokens, and wall time, in that
order - are checked before the signature test ever runs; each exhaustion
refuses with its own named `loop_halt` reason (exit 2). When budgets clear,
a signature equal to the task's last two recorded signatures also refuses,
exit 2, and the `loop_halt` carries all three matching signatures; a
changed signature is recorded and the attempt is allowed. `atlas loop
resume --task <id> --evidence seq:<n>` reopens a halted task only when the
cited record's writer differs from whoever wrote the halt - the same actor
citing itself again is refused.
