# Godmode v0.3.24

Iteration controls, an oracle over the tests, a scope gate on "done",
perimeter checks, a ledger that survives compaction, and four sentinel
shapes the gate never named before. One upgrade, no configuration.

## Added

- **Scope gate.** A reply that declares the work complete while the
  record still holds this session's operator asks, the plan's pending
  steps, criteria no claim cites, a hypothesis that failed three
  checkpoints, or a temporary change nobody restored is blocked once at
  Stop, with the list and each item's closing command.
- **Loop episodes.** One error signature, the same hunks, and no new
  file, assertion, or error class for six attempts (four in the novice
  profile, eight in strict) is named at Stop with the turn where new
  information last arrived. `godmode loop --transcript <path>` prints
  the episodes on demand.
- **Repeat-failure ask.** The fourth run of a command that failed three
  times against an unchanged tree is asked about, with the count.
- **Re-observe notice.** Eight edits since the file under repair was
  last read, or an error class that changed since that read, is named.
- **Measured spend and context.** Token spend is read from the host
  transcript against a declared `tokens` ceiling; the window is named at
  seventy percent of the `context_window` ceiling (default 200,000,
  set it in the ceilings file).
- **Commit-score plateau and stall halt.** `score = <n>` in commit
  subjects is read; four scored commits that did not beat the best
  before them are named. The stall streak's halt threshold blocks until
  an operator-stated record clears it.
- **Oracle shapes in `integrity`.** A test weakened in the same diff as
  its source (blocking), an assertion literal moved (named), a harness
  node dropped (blocking), a new test never observed red, and a test
  that cannot fail as written (no check, a constant asserted, a value
  compared to itself, an assert after return, a swallowed assert, an
  empty raises context). Twelve monitors.
- **Perimeter checks.** `godmode perimeter add "<command>"` declares a
  boot, an import walk, or a typed route; `perimeter run` attests the
  exit code; `session close` refuses while an active check has not run
  this session. `perimeter list` and `perimeter retire` complete the
  verb.
- **Regression-zero close.** A step attested green earlier this session
  and red later, with no green since, refuses `session close`.
- **Ledger in the brief.** Every session start, including the start
  after a compaction, carries goal, invariants, acceptance commands,
  files in play, failed approaches, last green, open obligations, and
  the current step, rebuilt from records. `status remaining --digest
  --transcript <path>` prints it with the loop episodes and spend.
- **Authority stack.** `session open` records the hash and line count of
  every instruction file, names one past 200 lines, and names a conflict
  between a file that forbids editing tests and a plan step that edits
  one.
- **Missing surface in `precheck`.** Authorization, retries and
  timeouts, tenant isolation, migration rollback, input limits,
  idempotency, races, and invalidation, derived from the task text as
  obligations to discharge or waive.
- **Dirty-diff ask.** `git add -A` or `git add .` with an approved plan
  fence and files outside it asks with the file names; denies in the
  strict profile.
- **`checkpoint --owes "<restore>"`.** A temporary change (a role bump,
  a throwaway spec) becomes an open obligation the scope gate names
  until it is closed.
- **Files nobody named.** Files written this session that no claim,
  change, or checkpoint names are listed at Stop with their paths.
- **Unread truncated output.** A tool output the host saved to a file
  that no later tool call opened is named at Stop with the file name.
- **Repo-config traps.** The brief lists keys in the repository's own
  git config that run or redirect a command when the tree is opened
  (`core.fsmonitor`, `core.hooksPath`, shell aliases, filters), by key
  name and value hash.
- **Sentinel shapes.** `hook-as-code-write` (R3: `.git/hooks`,
  workflows, host settings and hook files), `release-freeze-mutation`
  (R3), `container-host-escape` (R3: a docker socket mount),
  `recovery-point-destruction` (R5: shadow copies, restore points,
  backup catalogs). Sixteen new gate-corpus rows.
- **Read-only node payloads.** `node -e` and `node -p` under the scan
  posture are read as tokens: requires only from the read-only module
  table, no eval, Function, import(), network object, or writing fs
  member. Print-only runs are no longer a mutation.
- **`doctor`** names an interpreter wildcard in a host's permission
  allow list and an MCP server run through `npx` without a pinned
  version.
- **Archive read index.** Reads parse and hash only the record files
  after the indexed prefix; `GODMODE_VERIFY_READS=1` disables it.
- **Host pages** for Cursor and Antigravity under `docs/hosts/`, and
  `docs/COMPACTION-AND-LEDGER.md`.

## Changed

- The read-only Python payload scan is the default posture
  (`inline_interpreter` defaults to `scan`); `"ask"` opts out.
- `drift` no longer lists a step the host transcript shows running;
  `recurrences` skips a step whose last attestation is green; `loop`
  resets a repeated-action count when a mutation sits between runs.
- `claim --transcript` downgrades a claim whose cited check runs a file
  this session edited, or whose result is an operational error rather
  than a verdict.
- A parked ask nag is dropped the turn its ask is closed. A sentence
  that lists what is pending is not a claim.
- An untracked new test file counts as added in the integrity and
  oracle diff readers.
- A bare `godmode status` prints the survey. The evidence-pipe advisory
  stays quiet behind `tee` or `pipefail`. A control-character finding on
  a 0x08 names the byte-built repair.
- The code-of-law skill reads `GODMODE-CODE-OF-LAW.md` only when it
  exists.

## Limits

- No hard iteration cap: godmode does not own the loop. The
  repeat-failure ask, the loop episode, and the stall halt are the stops
  it can place.
- The node scan is a token allowlist, not a parser; anything it cannot
  read keeps the ask.
- The context tripwire needs the transcript's usage fields; a host that
  writes none leaves it silent.
- The perimeter gate holds at `session close` and at the CLI; a host
  whose Stop hook does not fire sees it only when the agent runs the
  close.

## Verifying

- `python -m unittest tests.test_sweep_0_3_24 tests.test_iteration_trap`
- `godmode scenarios --brief` reports `all-caught | total=29`.
- `godmode integrity --base HEAD` on a diff that removes an assertion
  returns `blocked`.
