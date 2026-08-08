# Changelog

All notable changes to Godmode will be documented in this file.

The format follows Keep a Changelog principles, and releases use semantic versioning.

## [Unreleased]

### Added

- `authorize setup --password-stdin` and `authorize issue --password-stdin` for
  non-interactive hosts that pipe the password on standard input.

### Fixed

- Removed the duplicate `hooks` manifest reference that made Claude Code fail to
  load the plugin's hooks.
- `authorize setup` and `authorize issue` now fail immediately with guidance when
  no interactive console is available instead of blocking forever on the password
  prompt (including Windows `NUL` redirection, where `isatty()` reports true).

## [0.2.6] - 2026-08-08

### Added

- Four additions, each closing a gap the product could describe but not detect.

  `loop` reports a file repaired by `fix:` commits across three or more releases.
  Every other detector there reads checkpoint records, and recording a failure is
  voluntary — so across this project's whole archive not one checkpoint carries a
  non-green status and the spent-hypothesis detector could never fire. Inferring
  the failure from the records was tried first and abandoned: subjects are outcome
  summaries, not problem statements, and none of them cluster. The signal is in
  history instead, which is written by committing rather than by anyone choosing
  to admit being stuck. Run against this repository it names the action gate,
  repaired across four releases while the cause was structural — one release
  before that question was finally asked.

  `godmode_usage` measures a session from the transcript the host already writes
  to disk and hands to every hook. The product's only token figure measures how
  far the archive brief compresses the records, which is routinely misread as a
  saving, and nothing supported a claim about what a session cost. Counts are read
  and counts are kept: the file is streamed rather than loaded, only numeric usage
  fields are touched, the transcript's own path is not returned, and measuring
  writes nothing. Those properties are asserted against a transcript seeded with
  distinctive strings, so the privacy contract is checked rather than promised. A
  missing transcript reports insufficient data, never zero.

  `capabilities --usage` reports which declared surfaces this project has never
  used. Establishing that four of them had zero records took a manual
  investigation; the archive knew all along. It reports and never removes, because
  a surface unused in one project may be why someone adopted it in another.

  `docs --lint` gains a stale-figure check: a number in public prose that the
  runtime can count for itself is compared against the real count. Historical
  records are exempt, since a changelog entry states what was true when written,
  and a figure with no exact local answer is left alone rather than guessed at.
  The badge that motivated the check has been corrected by removing the count
  rather than updating it — a document stating how many tests exist goes stale on
  the next commit that adds one.

  A write to the operating system's temporary directory is ordinary work.
  Containment refuses writes outside the working tree and the agent's scratch
  directory sits outside it, so both rules were right and together made the
  intended temporary location unusable. The allowance is a property of the
  machine, deliberately not a path a project can declare: a repository able to
  nominate its own writable location could nominate any of them, which is the
  disarming this gate exists to notice.

  Finishing a task records the claim. `claim` grades an assertion against
  citations that must resolve and is the first thing this product demonstrates,
  and across the whole archive it had been used zero times — because it is a
  command somebody has to decide to run, and an agent finishing a task is reaching
  for the finish rather than for a subsystem. Reporting that work is done is
  itself an assertion about project state, so `report --record-claims` puts it
  through the same grading as any other. Nothing new is asked of the agent, and
  the honest outcome is the common one: a completion carrying no resolving
  citation is stored as a hypothesis.

  `benchmarks/` holds four tasks that check whether the mechanisms fire — a
  weakened test, a drifted version surface, a spent hypothesis, and the cost of
  the bounded brief. Each binary task ships a control run with the fault absent
  that must produce the opposite result, because a task whose control also fires
  measures nothing. They need no network, no model and no keys, and the results
  are committed so that a figure published anywhere has a file behind it. The
  brief's cost is reported as a size, not a saving: establishing a saving means
  doing the same work twice, which this harness cannot do and does not claim.

  A refusal can now be answered without disabling the guard. The gate named a
  remedy that did not exist: no host tool call carries a field a capability could
  travel in, so the broker was unreachable from the hook and the only response to
  a false positive was switching the plugin off. The broker was never the missing
  part — its token is password-issued, bound to one exact operation, expiring and
  spent once. What was missing was a place the hook could read it from.
  `authorize stage` puts it in the archive's own state directory, under the git
  metadata rather than in the working tree, so a cloned repository cannot carry
  one. Every other property is inherited unchanged, and the token is never
  printed, because a capability on a terminal is a capability in a scrollback
  buffer.

  The surfaces a host feeds are enumerated, each with a test that crosses its
  real boundary or a stated reason for having none. Four gate defects reached
  released builds because the tests fed the classifier strings written by hand
  while the host sends something else; fixing the gate fixed one surface, and the
  blind spot was structural. A hook the host invokes with neither a boundary test
  nor a reason now fails the suite rather than a release.
- `checkpoint --review` reports obligations that a later handoff may have made
  moot. Recording what must not be forgotten was always here; nothing ever asked
  whether a carried obligation was still worth doing, so an item recorded validly
  and superseded by a later release was restated in every handover until a human
  asked why it was still there. Both are continuity failures and only one was
  implemented.

  Two signals, deliberately dull. An obligation restated across three or more
  handovers without changing is reported, which needs no understanding of the
  text at all. An obligation about a version, recorded again later about a higher
  version, is reported as pointing at a release nobody will install.

  Findings, never closures — the fix for carrying something too long must not
  become dropping it too early, so each finding is phrased as the question a
  reader should answer.

  The first implementation grouped obligations by exact wording and found nothing
  in twenty-two real handovers, because real obligations are compound sentences
  that drift while meaning the same thing. They are now split on the joins that
  separate them and grouped by word overlap, and the test corpus is taken from
  the archive rather than written to suit the matcher.
- `tests/probe_installed_build.py` drives the hook of the *installed* plugin
  rather than the working tree's. Every gate defect this project has had was
  found by installing a build and using it, never by the suite, and twice a live
  result was reported that had actually come from a stale cache. The working tree
  and the artifact a user receives are different things, and only one of them
  ships.

  The probe runs twenty-one cases through the newest cached build and reports
  which behave differently from the release they claim to be. It is not collected
  by the suite, because it asserts about a machine's plugin cache rather than
  about this repository.

  `git commit --amend` is now named in the protected patterns instead of being
  left to fail closed. It was refused either way, but as an unclassified
  mutation, which tells the reader nothing about why the gate stopped them.

### Fixed

- A project checked out under the system temporary directory kept its containment
  rule. Recognising the temporary directory as ordinary working space was correct
  on its own, and so was refusing writes outside the working tree — but where the
  project itself sits under temp, every path near it is also under temp, so the
  first rule swallowed the second and every write outside the tree was permitted.
  That covers CI workspaces, sandboxes and any build under `/tmp`. Where the two
  overlap, containment governs alone.

  Found while reproducing an unrelated failure in a throwaway clone that happened
  to land in the temporary directory. No test would have looked for it, because
  nobody writes a test for a project living in `/tmp`.

## [0.2.5] - 2026-08-08

### Fixed

- The gate judges what a command runs rather than what it mentions, and stops
  interrupting work that never leaves the machine.

  A command named is not a command run. The classifier searched the whole line,
  so `grep "git push" notes.md` was refused because the words appeared in an
  argument — and a session working on protected operations trips that constantly.
  Quoted text is data now: it is blanked before the mutation patterns are
  applied. That is safe only because the safe listings are a whitelist matched on
  the original, so a shell invoked on a quoted script is still unrecognised and
  still fails closed.

  Staging and committing are no longer protected. A commit is local and
  reversible and loses nothing, and gating it made committing impossible in a
  session, because no host tool call carries a field a capability could travel
  in — there was no approval to give. They are recorded at the same tier as a
  file edit. `git commit --amend`, `reset`, `clean`, `rebase`, `checkout`, branch
  deletion and every form of `push` stay protected: those either leave the
  machine or destroy work.

  Release notes moved from the repository root into `docs/releases/`. Five files
  restating what the changelog and the release pages already carry made the first
  thing a reader sees a wall of near-duplicates.
- Four more refusals of ordinary shell work, all found by using the released
  build rather than by testing it.

  An input redirect was classified as a write. `wc -l < README.md` reads a file
  and writes nothing; the two characters were grouped only because they look
  symmetrical. Reading from a file is a read.

  `2>&1` was split at the ampersand. Making a bare `&` a separator so that
  `ls & rm` could not launder was correct, but in `2>&1` the ampersand
  duplicates a file descriptor and is part of one token — the split left a bare
  `1` behind, which classified as an unknown mutation and refused the whole
  command. The separator now ignores an ampersand that follows a redirect.

  Every command substitution was refused on sight. That held the line against
  `ls $(curl …)`, and denied `echo $(ls)` along with it, which runs nothing the
  classifier could not already see. What a substitution runs is now extracted and
  classified alongside the line containing it, so the laundering is stopped just
  as firmly and nothing legitimate is lost. `${VAR}` is expansion rather than
  execution and was never this.

  An output redirect inside the working tree was refused while the declared
  `Edit` of the same path was permitted. That gated the honest form and not the
  other, which is all cost and no cover. A redirect is now judged by where it
  lands, exactly as an edit is: inside the tree it is ordinary work, and outside
  it, or into `.git/`, `.env` or a key, it is protected.

## [0.2.4] - 2026-08-08

### Fixed

- The gate is tested the way the host drives it, and three defects it had been
  hiding are fixed.

  Every file edit was refused. The allowance for ordinary working files tested
  whether a path looked absolute, which read as a reasonable proxy for "outside
  the tree" and is not one: the host sends an absolute `file_path` for every
  `Write` and `Edit`, so the allowance could never fire and no edit was ever
  permitted in a session. Containment is now measured against the project root,
  which also subsumes traversal — a path normalising outside the tree fails
  containment rather than needing its own rule — while `.git/`, `.env`, keys and
  certificates stay protected wherever they sit.

  Shell control flow was refused. `for`, `do` and `done` are not commands, so
  they matched nothing and failed closed, and an ordinary loop over a few files
  was denied. Control flow is now recognised as structure: a keyword is stripped
  and the remainder judged, exactly as an assignment prefix is, so `do rm -rf x`
  stays protected and a loop body is still classified on its own.

  The refusal message named a remedy that did not exist. It asked for a one-use
  capability, but no host tool call carries a field a capability could travel in,
  so the broker was unreachable from the hook and the operator was sent looking
  for a token they had no way to supply. It now names what actually unblocks the
  call, and says plainly that there is no in-session approval — which is also the
  reason this gate must be conservative about what it stops, since every refusal
  is total.

  All three were invisible to the suite for one reason: the tests fed the
  classifier operation strings written by hand, one layer below the boundary
  where the host's payload arrives. A real `PreToolUse` payload now goes into the
  hook process and the decision comes back out, so a case can only pass by
  working the way it will work in a session.

## [0.2.3] - 2026-08-08

### Added

- The document linter now checks both directions. Every check it shipped with was
  negative — rationale leaks, unverifiable claims, counterfactuals, internal
  notes, unfinished markers, local paths — and all six ask whether a document
  contains something it should not. None asked whether it contains something it
  must, so a document that silently omitted a required section was reported
  clean. The bias runs one way: in a one-sided
  linter every false negative makes the output look better than it is, which is
  the wrong direction for a tool whose purpose is to stop overclaiming.
  
  A project may now declare artifact contracts in `.godmode-docslint.json`,
  mapping a path pattern to the sections a document must carry. Both halves are
  checked: `missing-section` when a required heading is absent, and
  `empty-section` when one is present with nothing under it — a heading with no
  content satisfies a word-search and satisfies nobody reading it. A mistyped
  contract is reported rather than dropped, since an operator who believes their
  documents are under a check that never ran is worse off than one who declared
  nothing, and the report states which contracts were applied so it cannot be
  read as contract-checked when none was declared.
  
  Applying the first contract to this project's own release notes immediately
  found one shipped without any verification instructions.
- `godmode trust` reports what a repository's checked-in agent configuration
  would run and what it would permit. Host settings, server declarations and hook
  definitions were already being read, but only to ask whether their prose was
  shaped like an instruction — never the structural question of whether the
  configuration a repository ships *executes* anything or *disarms* anything.
  
  A cloned repository can declare a hook that runs a command the moment a tool is
  used, declare a server whose launch line is arbitrary, or pre-authorise the
  exact operations the action gate exists to interrupt. That last one made the
  omission reflexive: this product's own enforcement is a host hook, so the
  gate's off-switch lived in a file the gate never read.
  
  Blanket permission modes and fetch-and-run hooks fail the command. A declared
  server or an ordinary allowance is reported without failing, because a check
  that stopped every clone carrying one would be switched off. Nothing here
  decides whether a declaration is hostile — that is the operator's judgement
  about their own repository — and an unreadable configuration file is reported
  rather than skipped, since silence on a file that could not be parsed reads as
  approval. Absent configuration and inert configuration are reported as
  different facts.
- Each release gate is now run against a copy of the project with the property it
  defends deliberately broken, and must report failure. A gate that stays green
  under its own breaking mutation is not a check, and six times in one session a
  check reported a success it could not have withheld — twice a gate battery
  piped through a pager so the recorded exit status belonged to the pager, twice a
  probe that passed only on a machine already initialised, once a suite that
  proved refusals without asking whether ordinary work could still proceed, and
  once a contamination grep read as clean when its exit code meant the opposite.
  Knowing about the failure mode did not prevent the sixth instance, which is why
  it is asserted rather than remembered.
  
  Writing the mutation turned out to matter as much as running it. Three of the
  first mutations attempted were wrong — they broke something the gate never
  claimed to watch, and three gates were briefly and wrongly suspected of being
  blind. A breaking mutation cannot be written for a gate whose contract is not
  understood, so the harness doubles as a statement of what each gate is for.
  Gates without a proof are listed with the reason, because a harness that
  quietly covers a subset reads as covering everything.
  
  Module self-checks are now discovered rather than registered by hand. Six
  already existed and had never been wired into the suite, and the action gate —
  the classifier deciding whether a destructive command is interrupted — had no
  self-check at all while quieter modules did. It has one now, asserting both
  directions: the commands a working session issues must pass, and the
  destructive forms must not.
- A portable `plugin.json` at the repository root makes this installable by any
  client implementing the Agent Plugins specification, alongside the existing
  host manifests, which stay where their hosts look for them. The skill layout
  already conformed exactly; the field vocabulary already matched. What was
  missing was a manifest at the location every conformant client checks.
  
  The specification's schema is closed, so host-specific data moves under
  `extensions` behind a reverse-domain namespace that other clients ignore
  without validating. No `mcp.json` is shipped, because this product declares no
  MCP server and an empty one would advertise something that does not exist.
  
  The description says plainly that the portable package carries skills and that
  the action gate needs a host with hook support: hooks are outside the v1
  format, so a client without them installs the skills and none of the
  enforcement. A governance tool that does not say so is mis-sold.
  
  Conformance is asserted locally against the closed field set rather than by
  fetching anything — the schema URL in the manifest is a string, never a
  request — because a manifest validated only by other people's installers is
  exactly the shape that let the composite action stay broken for a fortnight.
  The root manifest is registered as a version surface, since adding one without
  registering it is the silent drift that command exists to catch.

### Fixed

- Changelog fragments are linted as public prose. They were treated as working
  material, so a fragment's wording was only checked once it had been merged
  verbatim into the public changelog — at which point changing it edits a
  published record rather than a draft. The linter caught its own release note
  this way, flagging a superlative in text that had already shipped into
  `CHANGELOG.md` when the same words had passed unexamined in `changelog.d/`.
- A claim about the outside world is now recognised without being declared. The
  runtime already refused to record a verified claim about an external system
  unless a primary source had been read, but that check only ran when the caller
  passed the flag — so it protected whoever remembered they were talking about a
  remote system, which is not the person who needs it. The seed case was an
  assertion that a pinned action version did not exist: stated from recall,
  wrong, and caught only because a human checked. No flag was passed, because it
  did not feel like a claim about anything remote.
  
  Detection is narrow on purpose, firing on third-party artefacts pinned at a
  version and on assertions about what a released version does. A detector that
  fired on ordinary local statements would teach the operator to route around it.
  
  Fixing the detection exposed the gate behind it as unsatisfiable. It demanded a
  `doc:` or `url:` citation and then rejected every one of them as unresolvable,
  so a claim about the outside world could never be recorded as verified whatever
  the author had actually read. A source outside the worktree now resolves as the
  operator's declaration that they read it — nothing local can confirm that, and
  confirming it over the network is not something this runtime does — and the
  record names which citations were asserted rather than checked, so a later
  reader sees the difference instead of one uniform "verified".
  
  The seeded fuzz harness caught the first version of that change accepting a
  citation of control characters and encoded traversal, which a declared source
  reference must now not look like.
- Merging a version twice no longer produces that version twice. A release is
  rarely cut in one pass — a fragment arrives after the first merge, usually
  because a gate caught something, which is the system working — and the second
  merge inserted a second heading for the same version above the first rather
  than folding into it. Entries already recorded are kept verbatim, so a re-merge
  never reformats prose that has already been published.

  One such duplicate shipped in a tagged release while 464 tests, thirteen gates,
  the changelog check and the document linter all reported green, because nothing
  had ever asked whether a version appears once. The repository's own changelog
  is now asserted to carry each version exactly once.

## [0.2.2] - 2026-08-08

### Fixed

- The injection scanner no longer reads vocabulary as instruction: an
  exfiltration verb must govern its object within a few words, so a threat model
  describing "memory leak" and "secret scan" on one line is documentation rather
  than an attack. The acceptance suite now runs every gate the CI workflow runs,
  reading the list out of the workflow file itself and checking each exit code,
  so a gate that only exists in CI can no longer regress unseen. The composite
  action resolves `python3` when a bare `python` is absent instead of failing
  with "command not found".
- The composite action loads again: an input description interpolated
  `${{ github.base_ref }}`, and expressions are evaluated in a manifest where
  that context is not bound, so the whole file failed to parse. A second defect
  made a `run:` scalar start with a quoted string and continue. Both classes are
  now asserted locally, because nothing but GitHub had ever read that file. Two
  behaviour probes were quietly machine-dependent — they called commands needing
  an initialised archive, so they passed on a developer's machine and failed on
  a fresh checkout; they now exercise the same skills without one. The anchor
  test resolves both sides before comparing, since macOS maps `/var` to
  `/private/var`.
- The pre-tool gate denied a working session: `ls`, every pipe, every compound
  command and every file edit fell through to `unclassified-mutation` and failed
  closed. Compound commands are now split and judged by their worst part, so a
  pipeline of reads is a read and a safe head cannot launder a dangerous tail;
  ordinary shell reads are recognised; editing a working file is the work rather
  than a protected action, while `.git/`, `.env`, keys and paths outside the tree
  stay protected; and running an interpreter is recorded as local compute, since
  this gate covers named protected operations and is not a sandbox. A new
  usability suite runs twenty commands taken from a real session and fails if any
  is blocked — the question no test had asked before.
- The gate denied every PowerShell command. The pre-tool hook fires on
  PowerShell calls, but the classifier knew only POSIX vocabulary, so on Windows
  each cmdlet was an unclassified mutation and the whole session failed closed —
  the same defect as the previous release, surviving its own fix because the
  usability corpus had been taken from a session that happened to run a POSIX
  shell. PowerShell's approved-verb convention now classifies it: `Get`, `Test`,
  `Measure`, `Select`, `Resolve` and their peers read, and every other verb is
  absent on purpose so `Set-Content`, `Remove-Item` and anything nobody
  enumerated still fail closed. `find`, `findstr` and `where` are recognised
  too, while `find … -delete` and `find … -exec` are named as the mutations they
  are.
  
  Granting a read allowance had also created something to hide behind. While
  `ls` still failed closed, a separator the splitter missed cost nothing; once
  `ls` was a recognised read, a newline or a bare `&` handed the rest of the line
  the tier of its first word, so `ls⏎Invoke-WebRequest …` classified as a
  listing. Both now end a segment. A command substitution cannot be split out at
  all — it never appears as a segment — so `$( )`, backticks and `${ }` withhold
  the read allowance instead of extending it over an operation the classifier
  never saw; a plain `$VAR`, `$env:` or `$_` is a value, not a command, and is
  unaffected.
  
  The usability suite now carries a Windows corpus alongside the POSIX one, and
  asserts the laundering cases directly, so neither half of the contract rests
  on which shell the last session happened to use.

## [0.2.1] - 2026-08-07

### Added

- Behaviour assertions now execute instead of being counted: an assertion in a
  skill's `godmode-evals.json` may carry a `check` (argv command plus expected
  exit code and output substring) that runs for real from the project root,
  while bare strings stay valid and are reported declared-only. Each of the
  five skills ships at least one executable probe. Two new snapshot families
  join routing: `charter-rules.json` freezes every compiled rule (id, trigger,
  enforcement, verify, text hash) so editing a prose rule shows a field-level
  diff, and `ranking.json` freezes the ordered segment selection the context
  brief makes for a fixed three-task set, so retrieval drift fails loudly.
- Chronicle depth work in three parts. Append no longer re-verifies the whole
  chain on every write: a `godmode-head.json` hint in the archive root is checked
  against the last record file only, falling back to a full verified scan (and
  rebuilding the hint) whenever the hint is missing, corrupt, or stale — full
  verification is unchanged and still catches mid-chain tampering via
  `verify()`/`doctor`. `append(..., dedupe=True)` returns the most recent
  byte-identical record of the same kind and subject (marked `"deduplicated":
  True`, never persisted) instead of growing the chain; the default is off, and
  dedupe never crosses subjects. New `Chronicle.expunge(sequence, reason)` erases
  a record's data and evidence after a secret slips the shape scanner: the record
  and every subsequent one are re-sealed so the chain still verifies, and an
  `incident` tombstone (sequence, reason, old record hash) makes the rewrite
  auditable instead of silent.
- The mandatory task-completion report (PRD 23.2) now exists as
  `godmode_report.completion_report`: twelve fields assembled from archive
  records and read-only git observation instead of composed from memory. The
  status verdict is derived, not asserted - "verified" is only reachable when no
  claim this session was downgraded and session close would pass, a blocked gate
  forces "blocked", and a session with no change records reads "no change
  required". Every field carries an uncertainty label from the 23.1 vocabulary,
  and `render_markdown` emits the TASK COMPLETION REPORT table (field, value,
  label) in a fixed order.
- A derived SQLite index (`index.db` in the archive) now persists ranked corpus
  segments, compiled rules, and archive summaries between sessions: `rebuild`
  regenerates it wholesale from the live sources, `fresh` proves the sources have
  not moved before any read, and `query` refuses a stale index outright unless
  the caller opts in and accepts a `stale: true` label. Alongside it, a read-only
  database architecture manager inventories every SQLite file via `mode=ro`,
  runs the 11-row Mandatory Schema Review (rollback text is a hard fail, never a
  question), and statically flags hazardous migration SQL such as `DELETE`
  without `WHERE`.
- `godmode fuzz` feeds seeded garbage — unicode, nulls, separators, quotes,
  comment markers, encodings, lengths — to the command classifier, path
  containment, migration review, citation binding, and every config reader, and
  asserts the properties that must hold for any input. Findings carry the seed
  and case index so a failure replays instead of being hunted. Its first run
  found four config readers that crashed with `AttributeError` on a file
  containing `null`; they now degrade to defaults, and 2,500 fuzzed cases across
  five seeds report fail-closed.
- A mid-rebase repository used to read as merely "dirty". `repo_state` now
  detects in-progress git operations (merge, rebase, cherry-pick, bisect,
  revert), detached HEAD, and stash depth straight from git's own metadata —
  worktree `.git` pointer files included — and surfaces a crisis as a
  `repo-in-progress-operation` context warning, inside `observe_git`, and as a
  named `warning` in the opening handshake, right after the dirty count it used
  to hide behind. Lessons now carry a project scope tag (`record_lesson_scoped`
  / `lessons_for`) so one project's habit cannot leak into another unless
  explicitly marked portable, and `advance_evidence` enforces the §15.2 ladder:
  confidence climbs one rung at a time, and demotions always pass but must state
  a reason.
- The parity matrix now compares eleven capability-level dimensions instead of
  file-surface counts: `capability` (public symbols via the atlas, both trees),
  `architecture`, `runtime-wiring` (orphan ratios: presence vs wiring), the six
  surface dimensions, `identity-freshness`, and `project-invariants`. Each
  dimension carries one of five verdicts (ADOPT, EXTEND, DIVERGE-DELIBERATELY,
  REJECT, ALIGNED) with a one-line reason; reference-ahead gaps name their adopt
  candidates and project-ahead gaps list local extensions, never "ignore".
  `adoption_floor` enforces E-14: an ADOPT whose paths overlap a recorded
  invariant's `file:` evidence flips to REJECT ("protected local fix; parity is
  a floor, not a ceiling"), wired into `parity_matrix` via a new optional
  `archive` parameter. `waive` records written acceptance of a gap, and the
  matrix's new `accepted` flag stays False while any open recommendation lacks
  one.
- A `PreToolUse` gate decides mutating tool calls in the host's own contract:
  protected operations without a capability, reached run ceilings, and a
  three-skip pattern all return `permissionDecision: "deny"` with the reason.
  Tool calls and elapsed time are now measured by the runtime instead of
  reported to it (tokens stay host-declared and are labelled as such), and
  `tool_call_interception` reports `HARD` only where the gate is actually
  installed.
- `godmode metrics` computes the twelve product measures from local records
  only — whether resumed sessions follow their stated next action, whether root
  causes survive scrutiny, whether finished work stays finished — each stating
  its basis and reporting `insufficient-data` rather than a flattering zero when
  there is nothing to measure. Duplicate detection stops counting test-method
  names and repeated house helpers as duplication (499 pairs to 33 on this repo)
  and is reported as leads rather than a pass/fail target.
- `session close`, `status handover`, and the session-end hook now report what
  the gates actually did — checks blocked, claims downgraded, steps skipped,
  secrets refused, scope drift, and the measured context reduction — each count
  carrying the record sequences that produced it. The summary reports activity,
  never averted disaster, because that counterfactual is unmeasurable; it stays
  silent when nothing fired and is switched off with `.godmode-report.json`
  `{"session_summary": false}`.
- The §12 lifecycle is now a stage machine read from the archive instead of a
  convention: `godmode_stages` derives each stage's entry requirement from records
  the work already produced (inventory, parity decision, approved plan, change,
  ran check, reconciled docs, undowngraded claim), `stage_gate` checks the whole
  prefix up to the target, and `advance` attests entry only when the gate passes.
  A stage may be skipped only by a recorded decision that states a reason. The
  §15.1 troubleshooting SOP ships in the same module as a fifteen-step checklist
  (T0–T14) whose completion is `sop:Tn` attestations; `sop_status` reports the
  next required step and names a root-cause claim premature while reproduction,
  staleness, and guard-observation remain unattested.
- Work items now carry the §19 schema: `status` records accept a closed item
  type (epic/story/bug/spike/chore/security/debt), Fibonacci points with a
  split-at-8 / spike-at-13 advisory finding, acceptance criteria, dependencies,
  branch, and severity. Three gates hold the schema load-bearing: verified with
  declared acceptance needs evidence, a bug cannot close without a root cause or
  an incident citation, and blocked requires naming the exact blocker. The
  rolling handover adds the §20.1 contract fields (repository anchor, approved
  objective, verified-versus-unverified split, protected invariants, changed
  files, remaining story points), and the reconciler gains a record-based
  trigger table (`record_triggers`) that reports changes without checkpoints,
  bug closes without guards, uncited decision reversals, and incidents without
  lessons.

### Changed

- The README is rewritten around what the product now does — the problem it
  addresses, how enforcement lives outside model output, per-host install,
  what is actually enforced, and the commands that prove each claim — and the
  logo ships with a transparent background so it sits on any page.

### Fixed

- First consumer dogfood of the installed plugin fixed four rough edges: the
  generic-adapter doc taught a `--name` flag `verify` does not have; `session
  open --brief` now shows the handshake's branch, dirty count, and
  sources statement instead of only the id; `verify --brief` states the check
  name and pass verdict; and a project with zero compiled rules is told its
  gates are vacuous (in `charter` and at session close) instead of reading as
  green.
- Egress hardening closed four gaps at the disclosure boundary. Path containment:
  every path a manifest or scan touches is resolved and verified inside the
  project root first; `../`, absolute, and symlink escapes are refused unread
  with a `path-escape` finding. Disclosures now carry `destination` and
  `destination_known`, stating "unknown" explicitly instead of omitting the
  receiving party. An optional `.godmode-privacy.json` lets a user declare
  `sensitive_paths` and `never_leave` globs that extend (never shrink) the
  built-in denials; a never-leave match blocks a notice exactly like a secret.
  And `redact=True` makes the "redact further and send less" choice real:
  blocking items are replaced by bare `redacted` entries - no counts, no
  excerpts - and the remaining scope is no longer blocked.
- Anti-loop fixes and scenario coverage: oscillation rollback now targets the
  last STABLE checkpoint (status green/verified, per §15.3) instead of merely the
  most recent one; a blocking `loop` verdict carries a four-part plain-language
  `notice` (what repeated, what it means, the next safe step, and no further
  mutation until the evidence changes); the repetition threshold is configurable
  via `.godmode-loop.json` `{"repeat_threshold": n}` clamped to 2..10 (default 3);
  and `transport-evidence:` attestations now count as non-model controls for
  model blame. The instruction-shaped-content scenario is relabelled from the
  mistaken E-13 to SEC-injection, and six golden scenarios are staged: false RCA
  (E-04), automated deletion preview (E-11), new-table temptation (E-15), context
  brief latency (E-19), session restart (CTX-01), and prior-fix protection
  (CTX-02) - 21 staged failures, all caught.
- The sentinel classified `git branch -d X` as read-only because the safe
  inspection prefix matched `git branch` before any protected pattern ran.
  Mutating flag forms of `git branch` now classify as `git-branch-mutation`
  ahead of every safe pattern, and the safe listings for `git branch`,
  `git tag`, `git stash`, and `git remote` are anchored so create, delete,
  rename, and remote-mutation forms fall through to protection. Every
  classification now carries a §9.2 risk tier R0-R5, with R5 (force-push,
  hard reset, `branch -D`, `clean -f`, SQL DROP) demanding a second
  confirmation. Capabilities bind to repository, worktree, and HEAD at mint
  time and refuse to be consumed elsewhere; pre-existing unscoped tokens
  still consume but say so. An optional `.godmode-authorization-policy.json`
  can tighten (never loosen) the boundary: TTL clamped to 60-900 seconds and
  `password_required` extending the protected categories.

## [0.2.0] - 2026-08-06

### Added

- `GODMODE_MODE=guided|standard|expert` changes exposure, never enforcement:
  guided appends plain-language guidance to every refusal, expert reports one
  line. `charter --bootstrap` mines candidate invariants from the project's own
  commit history for review, and `godmode operator` validates the typed operator
  profile — which has no name field on purpose and refuses profiles containing
  the OS account name.
- `godmode loop` reads the archive's own records and blocks the repetitions the
  repeating agent cannot see: identical normalised actions, reapplied patches
  (citing the prior attempt), A→B→A oscillation with a rollback point, changes to
  guarded files without re-observing the guard, and zero-output "successes";
  `loop --blame` refuses model-blame until a non-model control is attested.
- `atlas diagnose` now reports per-suffix support — a suffix whose files yield no
  symbols is "counted, not understood" and makes the atlas untrustworthy for
  structural claims — and `atlas duplicates` compares approximate symbol bodies
  as well as names, so one behaviour implemented twice under unrelated names is
  reported with `basis: body`.
- The atlas now dispatches extraction through a suffix registry — a third
  language is one `register_extractor` call, not a core edit — records
  `tested-by` and `documents` edges so `affected` can bound traversal by
  relation kind and bucket its answer into callers / tests / docs, and can be
  persisted with `save_index` / `load_index`, which reports fresh, stale, and
  missing files from content hashes with a derived confidence, never from time.
- `godmode benchmark` measures cold-start and resume brief cost against the
  declared token budgets with timings, computed and printed locally only; and
  `claim --external` downgrades a verified claim about an external API or
  library to hypothesis unless it cites a `doc:`/`url:` primary source actually
  read this session.
- `godmode changelog check` fails when a code change arrives without a
  `changelog.d/` fragment, and `godmode changelog merge --set-version X` folds the
  fragments into CHANGELOG.md at release time.
- A composite GitHub Action (`action.yml`) runs Godmode's gates — the
  test-integrity monitors and the changelog fragment gate — on a pull request with
  only a checkout of this repository; the runtime remains standard-library Python.
- `godmode config check` validates every declared `.godmode-*.json` file against
  its typed contract, failing with a `$.field` schema path instead of a stack
  trace; the extension-model split (S26-01/02) is deferred by recorded decision
  until a second consumer exists.
- `detect_context_issues` gains two staleness inputs — a `stale-lock` warning when
  an archive `*.lock` file has survived ten minutes, and `clock-or-restore-anomaly`
  when a file's mtime moved backward since the recorded baseline; new
  `capacity_checkpoint_due` returns the deterministic pre-compaction signal (due at
  80% of the context-brief token budget) for host hooks, and new `why` answers
  `context why --about X` with evidence-linked decisions, fixes, dependencies, and
  invariants actually recorded about a path or topic.
- README grows the missing front-door sections (badges, why, uninstall,
  troubleshooting, FAQ, documentation index); v0.1.0 release notes exist as an
  explicit draft with an owner checklist and no tag; and
  `scripts/godmode_docs_site.py` renders the repository's own Markdown into a
  self-contained offline HTML site with zero generator dependencies.
- The authored skill evals now execute: a deterministic routing runner scores every
  positive and near-negative prompt leave-one-out with stable tie-breaks, snapshot
  fixtures under `evals/fixtures/` turn any routing change into a field-level diff, and
  an adversarial grid attacks each control with real probes - breaches included.
- Forge output is now diffed against a checked-in golden skill tree, so a
  generator regression fails CI naming the drifted file; the learning loop's
  scanner → analyzer → writer → verifier phases each name their implementation
  in a registry.
- Gates deepen: egress `scan_staged`/`scan_paths` find secret-shaped values
  (masked, never repeated) in staged and untracked content before a commit exists;
  `loop` blocks after three non-green checkpoints under one unchanged hypothesis and
  demands a reset; scope `minimality` reports size pressure by name without blocking.
- A generic adapter reference lets any agent drive Godmode with shell, JSON, and
  exit codes alone — enforcement honestly labelled SOFT on unlisted hosts
  (S9-01); the LICENSE appendix names the copyright owner. Live install tests
  passed on both Claude Code (5 skills + hook inventoried) and Codex (installed,
  enabled, five skills discoverable).
- The scenario harness grows from 10 to 15 staged golden failures, each bound to
  its PRD acceptance ID (E-nn / CTX-nn): fix oscillation (E-03), test weakening
  (E-05), wrong environment (E-16), removal forgotten (CTX-03), and undocumented
  change (CTX-07) join the catalogue; `explain-context` now states the token
  cost of loading before anything loads.
- Instruction-file adapters for OpenCode (`AGENTS.md`), Cursor
  (`.cursor/rules/godmode.mdc`), and Gemini CLI (`GEMINI.md`) drive the CLI over
  shell, JSON, and exit codes; each host's enforcement is declared in
  `packaging/hosts.json`, `capabilities --host X [--record]` prints and records
  the negotiated table, and a test fails if an adapter document's stated levels
  drift from the declaration.
- Session open now performs the fixed model-independent handshake (identity,
  branch, dirty state, active plan, obligations, invariants, required-source
  count, and the host's enforcement table); a pair rule attested with one
  artefact blocks closure naming the missing half; `charter --decay N` surfaces
  rules no session touched; and the context brief ranks by freshness and states
  "read N of M required sources".
- `skill lifecycle`/`skill retire` give every skill a state and a recorded
  reason; `godmode lessons` runs the promote-or-retire pipeline (a lesson either
  gets its guard observed running or is retired — never appended forever); and
  `godmode experiment` executes the bounded loop declared in
  `.godmode-experiment.json`, recording every run and refusing to pass the bound.
- `godmode locale check` validates `locales/<lang>/` guidance variants against
  their English sources — heading structure must match and fenced code blocks must
  be byte-identical — and a Hindi `GODMODE.md` ships as the first variant.
- `godmode mistakes` runs the mistake-class detectors distilled from the lesson
  corpus: a status label used as evidence must trace to its assigning record, a
  regenerated-but-never-cited artefact is a box-tick, a generalized guard citing
  one surface blocks, bundled claims must split, and `--process-started` blocks
  an RCA against a process older than the code it runs.
- `netgate` differential capture proves the runtime dials nothing: each CLI
  surface runs against a throwaway project under a socket audit hook, any
  connection fails, and a detector that cannot catch a planted attempt raises
  instead of reporting clean; CI adds a `pip-audit` scan of the CI tooling
  environment (the runtime has zero dependencies) with `security`-labelled
  issue triage against THREAT-MODEL.md.
- `godmode_parity` turns comparison into decisions: `parity_matrix` scores a local
  reference across eleven named dimensions, attaching a verdict+action pair to each
  and labelling stale references; `absorption_check` rejects synced-but-unwired
  files until a reader and a ran guard both cite them; `schema_ladder` exhausts
  existing columns and tables before allowing a reviewed new table.
- `planmode specify` records the what/why before any plan states a how — a plan
  without a spec is refused; the contract gains `parity`, `steps`, and `points`
  fields; and an approved plan now survives a session handoff: a different model
  resumes it (it appears in the resume brief) instead of re-deriving it.
- `godmode method --check-method X --check-record file.json` gates an RCA on its
  method's completion contract: fault-tree cut sets are derived from the tree (not
  typed from memory), timelines need three instruments with ordered events and
  declared holes, fishbone spines are project-configurable via `.godmode-rca.json`,
  and an "unknown" root without a shipped instrument is refused for every method.
- `godmode environment --target` classifies a mutation target's blast radius
  (unknown fails closed as production, never overridable by repo text);
  `version --reconcile` diffs the version across every surface that states one;
  and `docs --reconcile` enforces the change→documentation trigger table,
  configurable per project via `.godmode-docs.json`.
- Every archive record now carries its author's fingerprint (host, model, effort,
  adapter enforcement level) at the chronicle layer, not only attestations; the
  context brief is proven byte-identical across models in the suite; and a
  handoff test proves agent B resumes agent A's approved plan and next action
  without reading any transcript.
- `godmode removal record` remembers why something was deleted — reason, location,
  replacement, references, restoration path, and authorizer are all required — and
  `godmode removal why` answers from the record instead of archaeology.
- Runtime guardrails inside the no-daemon boundary: `ceilings` checks reported
  spend against declared run limits, `watch` is a per-boundary anomaly scan that
  interrupts on a skip pattern, `rewind --to SEQ` previews a rollback to a
  verified checkpoint (checkpoints now record HEAD; execution stays with the
  operator), and `planmode arbitrate` scores every open plan instead of taking
  the first one stated.
- `status render` emits the status document read-only from the store, `status
  handover` gives one rolling handover view, every pending item is
  existence-checked before presentation (a phantom whose cited artefacts all
  vanished is closed in the same pass with evidence), and `sprint` now routes
  through the single status writer instead of appending a second truth.
- `sbom --format spdx|cyclonedx` emits the zero-dependency claim in standard
  forms, `sbom --gate` fails the build when the declarative dependency policy
  (default budget: zero) is violated, and `checksums` produces a reproducible
  SHA-256 manifest over every tracked file with `--verify` for clean-clone
  comparison; CI enforces the gate and proves the manifest reproducible.
- `godmode integrity` runs the nine test-integrity monitors (assertion-diff,
  skip/quarantine, mock expansion, coverage shape, requirement anchor,
  red-before-green, harness validity, negative control, protected-test gate) over
  the current diff and exits non-zero when a change weakens what the suite proves.
- Over-budget briefs now degrade through typed compression before dropping
  anything: each compressed view declares the fields its mask removed and the
  `seq:` handle that reconstructs the original from the archive; record
  confidence decays with the records written since (not wall time), and baseline
  staleness reports that decay instead of flipping a binary flag.
- `branches --claim` declares this agent active in the worktree and exits
  non-zero when another agent's live claim exists — the collision surfaces before
  mutation; `--release` hands it back. No merge driver ships: per-record
  append-only files make state conflicts structurally impossible (decision
  recorded).

### Fixed

- The two routing-eval positives that misrouted between the router and
  continuity skills were reworded with home vocabulary; routing is now sound at
  10/10 with regenerated snapshots, and the eval gate exits green.
- The completeness sweep's findings closed: the CI action job diffs HEAD~1 on
  push instead of passing vacuously; the verify matrix gains Windows and macOS
  legs plus the full gate battery; the command-surface reference is regenerated
  from the parser (74 commands); the acceptance doc maps every gate to its proof
  command across all three host manifests; each SKILL.md routes to the gates it
  governs; the repository's own charter now compiles 5 HARD rules (Hindi variant
  kept in step); `docs` without flags names the missing flag; and the atlas
  resolves cross-module imports — orphan noise drops from 57% to 38% and
  `diagnose` flags its own resolver when the ratio is implausible.

## [0.1.0] - 2026-08-02

### Added

- Local-first, project-bound continuity archive with atomic hash-chained records.
- Evidence-led inspection, resume, diagnosis, and context explanation commands.
- Protected-action classification, previews, and scoped single-use capabilities.
- Branch, version, plan, checklist, incident, privacy, parity, and export workflows.
- Validated on-demand project skill forging for evidenced reusable gaps.
- Five routed skills for Codex and Claude Code, a bounded Claude `SessionStart` adapter,
  acceptance tests, and release checks.
- Codex and Claude Code manifests plus a Claude plugin marketplace catalog.
- Godmode logo, social-preview artwork, and passive AIimagined project identity metadata.

[Unreleased]: https://github.com/AIimagined/Godmode/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AIimagined/Godmode/releases/tag/v0.1.0
