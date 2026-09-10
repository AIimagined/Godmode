# Godmode v0.3.24

The batch release. After three cuts in one day the operator said the
pattern itself was the problem: releases with items left for the next
one, and reports whose cons came back. This cut takes the field report
file of 2026-09-10 (nine findings, nine ranked fixes), the operator's
product requirements and research brief, the iteration-trap article, the
ten-point field roundup, and the compaction playbook as one set, builds
every item, and ships once. Nothing in that set is deferred.

## What changed

- **The scope gate.** "Everything is complete" with this session's asks,
  the plan's pending steps, uncited criteria, or a three-times-failed
  hypothesis still on the record is blocked once, with the list and each
  item's closing command.
- **Loop episodes.** Same error signature, same hunks, no new file,
  assertion, or error class for six attempts (four in the novice
  profile, eight in strict) is named at Stop with the turn where new
  information last arrived, and a `would-have-stopped-loop` receipt is
  recorded. A repeat-failure ask stops the fourth identical run inside
  the turn. Eight edits since the last read of the file under repair, or
  an error class that changed since the last read, names a re-observe.
- **The oracle shapes.** Five ExecCritic shapes as integrity findings and
  staged scenarios: a test weakened in the same diff as its source
  (blocking), an assertion literal moved (named, not blocking), a harness
  node dropped (blocking), a new test never observed red, and a cited
  check whose file the session edited. `session close` refuses a
  regression: a step attested green this session and red later with no
  green since. Thirty-two scenarios, each pinned by digest.
- **Perimeter checks.** `godmode perimeter add "<command>"` declares a
  boot, an import walk, or a typed route; `perimeter run` attests the
  exit code; `session close` refuses while an active check has no run
  this session. The "suite green, app does not boot" gap has a gate.
- **The ledger after compact.** The brief on every start, including the
  start after a compaction, carries goal, invariants, acceptance
  commands, files in play, failed approaches, last green, open
  obligations, and the current step, rebuilt from records. Stop names
  the window at or above seventy percent of the `context_window`
  ceiling, measured from the last assistant usage.
- **The authority stack.** `session open` records the hash and line
  count of every instruction file, names a document past 200 lines, and
  names a conflict between a file that forbids editing tests and a plan
  step that edits one.
- **The missing surface.** `precheck` lists what a task of this shape
  needs and agents leave out: authorization, retries and timeouts,
  tenant isolation, migration rollback, input limits, idempotency,
  races, invalidation. Obligations to discharge or waive, never code.
- **The dirty diff.** `git add -A` or `git add .` with an approved plan
  fence and files outside it asks (denies in the strict profile), naming
  the files.
- **Sentinel shapes the corpus never named.** Writes to hooks, workflows,
  and host settings (`hook-as-code-write`, R3); a release-freeze marker
  created or removed (R3); a docker socket mount (R3); a shadow copy,
  restore point, or backup catalog deleted (`recovery-point-destruction`,
  R5, previously read-only inspection).
- **Read-only node payloads.** `node -e` under the scan posture is read
  as tokens: requires only from the read-only module table, no eval,
  Function, import(), network object, or writing fs member. Print-only
  runs are no longer a mutation. Scan is the default posture.
- **The truncated log.** A tool output the host saved to a file that no
  later tool call opened is named at Stop with the file name; sixteen
  such outputs sat unread across the reporter's twenty-seven transcripts.
- **The repo-config trap.** The brief lists keys in the repository's own
  git config that run or redirect a command when the tree is opened
  (`core.fsmonitor`, `core.hooksPath`, shell aliases, filters), by key
  name and value hash only.
- **The read index.** Archive reads parse and hash only the files after
  the indexed prefix; a hook call that read the whole archive in four
  seconds reads it in one. An in-place rewrite of an indexed file drops
  the prefix and the full walk catches it. `GODMODE_VERIFY_READS=1`
  disables the index.
- **Measured spend and plateau.** Token spend is read from the host
  transcript against a declared ceiling; a commit-score plateau and the
  stall streak are named at Stop, the halt threshold blocks.
- **Drift and recurrence read the transcript.** A step the host log shows
  running is not "dropped"; a run after a tracked edit is a new
  experiment, and a step whose last attestation is green is not a
  recurrence.
- **The afternoon report.** Static false-green shapes (a test that
  cannot fail as written) as a twelfth integrity monitor; `checkpoint
  --owes` for a temporary change the scope gate names until restored;
  files written this session that nothing names, listed at Stop; an
  untracked new test counts as added; a bare `status` prints the survey;
  the evidence-pipe advisory respects `tee` and `pipefail`; a 0x08
  finding carries its byte-built repair.
- **Consistency.** The code-of-law skill reads the file only if it
  exists; Cursor and Antigravity have host pages with a proof recipe;
  `status remaining --digest` prints the session digest.

## Known limits

- No hard iteration cap: godmode does not own the loop. The repeat-failure
  ask, the loop episode, and the stall halt are the stops it can place.
- The node scan is a token allowlist, not a parser; it refuses anything
  it cannot read.
- The context tripwire reads the transcript's usage fields; a host that
  writes none leaves the notice silent, and it says so.
- The perimeter gate holds at `session close` and at the CLI; a host
  whose Stop hook does not fire (Antigravity on Windows) sees it only
  when the agent runs the close.

## Verifying

- `tests/test_sweep_0_3_24.py` and `tests/test_iteration_trap.py` fail
  against 0.3.23.
- `godmode scenarios` reports thirty-two staged failures caught, six of
  them new in this cut.
- `python -m unittest` across eight shards, `godmode integrity --base
  HEAD~1` and `godmode changelog check --base HEAD~1` green before the tag.
