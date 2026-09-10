# Godmode v0.3.25

## Added

- **A would-ask is a deny when nobody answers it.** On Claude Code in
  `auto`, `dontAsk`, or `bypassPermissions` mode, a protected call that
  the gate would have asked about is refused instead, with the
  staged-capability remedy in the reason (`godmode authorize stage
  --from-last-refusal`). In `default`, `plan`, and `acceptEdits` mode the
  ask still reaches you. Every `gate-asked` record now carries the
  permission mode it was asked under.
- **`doctor` reads your `ask_only` list.** An entry for
  `git-history-or-remote` or `release-or-external-write` is named as a
  warning, because under an auto-answered mode it is an allow.
- **A check must be able to fail.** A `--verify` citation whose command
  only reports state (`git status`, `echo`, `ls`, `cat`) cannot contradict
  the claim, so the grade stays below `verified` and the support line says
  which citation is decoration.
- **A claim knows the code it describes.** Every existing file a claim's
  text names is hashed at record time; when that file changes, the claim
  shows as stale in `claim --stale` and in the session brief.
- **Project ratchets.** Declare the repository's own debt counters in
  `.godmode-ratchets.json` (name to command); `godmode ratchet run` records
  each value and names every counter that rose, and `integrity` carries
  the same finding as its thirteenth monitor.
- **Temporary state, noticed.** A process stopped and not restarted, a
  server started on a port and never stopped, a table updated once, a
  stash never popped, a persistent environment variable: named at Stop
  from the transcript, with the `checkpoint --owes` remedy.
- **The one-variable rule as data.** A check that flipped red to green
  with three or more files edited between the runs is named as
  unattributed.
- **"Sources unread" reads local files.** Reading the project's own files
  counts as reading its repository; when the nudge still fires it names
  what was read.
- **A plan step can be finished.** `godmode plan --done <step>` and
  `plan --close`; a closed ask can be reopened with `remember --kind
  request --status open`.
- **The record's own false-green rate.** The calibration digest (in
  `session close` and `status remaining --digest`) reports how often a claim graded
  `verified` was later resolved `failed`, with a Wilson 95% interval and
  the refusals beside it.
- **`godmode retest`.** Every test that pins a changed file, as one
  command per runner; `--run` executes it and attests the exit code, and
  the changed source files no test pins are named.
- **Self-attested is named.** A verified claim whose check was run by
  the claiming agent says so; an attestation from another agent or model
  makes it independent.
- **Registry-aware recurrence.** `recurrences --against "<report>"`
  matches a new report against the fixed registry's symptom column and
  names the row and its guard; the prompt hook does the same once per
  session for a report-shaped prompt.
- **Design reads.** `precheck --about` lists the inventory and design
  lines that describe the task; a reply that calls something a product
  decision while such a line was never opened is named at Stop.
- **Hosts whose gate is not HARD.** `session open` leads with the host
  reach and names the six-verb day-one path; `resume --brief` is one
  screen (goal, dirty, obligations, current step, next); reads seen in
  the transcript count toward required sources with case folded on
  Windows; `doctor` names a project without git; `init --detect` finds
  the constitution and spec files by name.
- **Measurement environment.** `precheck` on a latency, duplicate-request,
  or re-render task lists the environment the deciding number must come
  from. A quoted sentence is no longer read as a claim. A process-control
  call's advisory names `checkpoint --owes` for the restore.
- **Preflight is the push gate's other half.** `godmode precheck
  --preflight --suite-shards 4` validates HEAD in a disposable worktree:
  the designated suite as sequential shards, then every gate step the
  verify workflow declares, read from the workflow file, then the scans.
  It records a `preflight` attestation at that commit, and `authorize
  stage` refuses to stage a push or a release create without a green one
  at HEAD. `--without-preflight "<reason>"` stages anyway and records the
  reason.
- **Release notes as a verb.** `godmode release-notes build <version>`
  derives the note from that version's CHANGELOG section, grouped by
  kind, with a Verifying section built from the tests the entries name;
  `release-notes check <version>` holds an existing note to the shape:
  present, every entry covered, no empty section, no process narration,
  a Verifying section. The docs lint names process narration in a note
  (`release-note-narration`), from the version set in
  `.godmode-docslint.json` under `narration_from`.
- **README** describes the current surface: the iteration controls, the
  scope gate and the oracle, the ledger after a compaction, the sentinel
  shapes added in 0.3.24, the node scan, and the numbers.
- **Held-back checks.** `godmode oracle hold --command "<check>"` (with
  the operator password) keeps a check under the git metadata directory,
  where the agent never chose it; `claim --verify` runs every held check
  after the cited ones, and a red one caps the grade at `observed`.
  `oracle list` and `oracle run` read and run them by digest.
- **Claims that rest on claims.** `claim --depends-on SEQ` records what a
  claim rests on; the weakest grade among them is inherited, and an
  unverified claim carrying three dependents is named load-bearing.
- **Memory hygiene.** `godmode hygiene` lists near-duplicate and
  contradicting lessons and decisions among the newest active records
  per kind, as a review list; it decides nothing.
- **Registry rows the record proposes.** `recurrences --propose` names a
  reason that waived, parked, deferred or declined work three times as a
  proposed fixed-registry row.
- **A committed test map.** `retest` reads `.godmode-test-map.json`
  (source path to the tests that pin it) beside its textual pins.
- **Reopen with intent.** `remember --kind request --status open
  --intent-preserved kept|replaced` records whether the operator kept the
  agent's decision and reworded it, or replaced it.
- **Hook manifest desync.** The session brief names a running hook
  manifest that differs from another install of the same plugin and
  version; a truncated plugin-cache copy is the case it was built for.
- **Hook timing.** `godmode hooks time --event pre-action --runs 3`
  measures the real hook on a synthetic payload against the declared
  timeout.
- **Two static checks.** `ACTION_SUBJECTS` pins every subject an action
  record is written under, with a census over writers and readers; a
  second test names any `module.name` read no godmode module defines.
- **The tripwire says when compaction cannot help.** A measured context
  past the declared window names a stale `context_window` declaration; a
  compaction that already ran and left more than half the window says
  another will free little.

## Using it

- No configuration. The fold reads the `permission_mode` field the host
  sends with each tool call.
- To let a push through in an auto-answered mode, stage the exact
  command once with the operator password: `godmode authorize stage
  --operation "git push origin main"`. The capability is spent on the
  matching call.
- Run `godmode doctor` after upgrading; an `ask-only-external-write`
  warning means your policy file lists an external-write category under
  `ask_only`.

## Fixed

- `precheck --about` raised in the registry and design lookups between two
  commits of this cut; the preflight gate caught it, and the preflight now
  also runs the composite action's own gates (integrity and changelog
  against HEAD~1, release-notes check).
- One memory-write incident, four defects: a write into the host's own
  project-memory directory is an ordinary write, not "outside the working
  tree"; the no-terminal error names a separate terminal window and the
  shim path; a shell literal piped into `--password-stdin` is refused
  outright (`password-in-transcript`, R5) so a typed password never lands
  in a transcript; and a refusal record carries the full operation digest,
  so `authorize stage --from-last-refusal` stages a command longer than
  the 500-character record cut. A redirect into `$TEMP`, `%TEMP%` or
  `$TMPDIR` is a scratch write.
- A request closure closes only the asks recorded before it, and the
  stop gate reads the same request window the closure command reads, so
  the gate and `remember --kind request --status closed` agree.
- Stop-hook notices arrive one per line. Checkpoint pressure counts
  code-shaped edits, not prose appends.
- `claim --verify` runs project commands on Windows (`npx`, `tsc`,
  `vitest` shims resolve through PATHEXT; backslashes survive the split),
  a check that just ran red caps the grade at `observed`, and the support
  line counts runs and passes separately.
- External-write verbs are judged on bare words, never on a word inside
  a path.
- `checksums` hashes text files with CR stripped, so two honest clones of
  a project without an `eol=lf` attribute produce one manifest.

## Limits

- The fold covers the modes Claude Code documents. A host that sends no
  permission mode keeps the ask.
- A session keeps the plugin it started with; the fold applies from the
  first session after the plugin is updated.

## Verifying

- `python -m unittest tests.test_ask_only_hook.NoHumanAskModeTests`:
  a push with `permission_mode: auto` renders `deny`; with `default` it
  renders `ask`.
- `godmode history --kind action --limit 5` after a gated call shows
  `permission_mode` on the `gate-asked` row.
- `python -m unittest tests.test_authorize_field_incident
  tests.test_request_closure_ordering tests.test_context_tripwire
  tests.test_field_feedback_0_3_25b`: the four incident defects, the
  closure ordering, the tripwire's three sentences, and the red-check cap.
- `python -m unittest tests.test_ledger_builds_0_3_25
  tests.test_ledger_builds_0_3_25c tests.test_action_subjects
  tests.test_phantom_attributes tests.test_checksums_eol`: the held-back
  oracle, `depends_on`, hygiene, proposed rows, manifest desync, hook
  timing, the two static checks, and the checksums manifest.
