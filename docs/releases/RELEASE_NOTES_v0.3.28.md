# Godmode v0.3.28

The archive got harder to corrupt. Every record now names its writer and carries a
trust derived from it, so an operator's correction outranks an agent's note, a secret
in free text refuses the write, and only a subject's creator can close it. Verification
is checkpoint-audited: one full walk proves a checkpoint, later walks re-read only the
records after it, and `godmode doctor` exits 1 naming the first broken record's
sequence, file and line instead of failing bare. Appends are serialized by an
operating-system lock the kernel drops when the writer exits, so a crashed process no
longer blocks the next append until an age-out. Every path that arrives from a record,
a manifest or a host payload is contained to your project or your state home after
symlinks are resolved - an escape is refused or skipped, never followed.

Memory also stopped only growing. `godmode forget` expires old episodes into a cold
segment that is still part of the same hash chain, reports supersession chains, and
flags contradictions as review records you close one finding at a time; a record a live
claim, a checkpoint, a law guard or a pin still cites never expires. At the other end of
the same lifecycle, a guard becomes law only through a promotion a *different* actor
approved after an independent re-run, so an agent can no longer write the rules it is
judged by. Guards recorded before that rule existed are not dropped: the first compile
after upgrading records one chained migration, marks those laws `[GRANDFATHERED]`, and
keeps them in force - your Code of Law survives the upgrade instead of emptying.

Around that, hosts are replicated rather than hand-wired. Host capabilities are a closed
enum; each host's manifest, launcher and support-matrix row is generated from it and can
no longer drift; `hooks wire --all --dry-run` previews every host with the same code that
applies it and merges only Godmode's own block of a shared config; and a generated CI job
per host installs the plugin that host's way and fires one hook. Copilot and Kiro join the
generated set. Six new skills land - second-look, changelog, host-sync, codegraph,
skill-eval and spec-lifecycle - each carrying a purpose file that cites the records which
motivated it, a routing score the eval ratchet refuses to let fall, and a description that
names the cases it is *not* for.

## Added

- `godmode forget` expires old episodes into a cold, still-chained segment, reports supersession chains and flags contradictions as review records; a record cited by a live claim, a checkpoint, a law guard or a pin never expires, and history can still reach a cold record by sequence. `remember --kind review --review seq:<n>` names which flagged contradiction a closure closes, so a subject carrying more than one open review can be cleared one finding at a time.
- `remember --supersedes <seq>` records versioned supersession; history renders the chain and every latest-per-subject reader follows it.
- The archive's five memory layers are covered by an eight-test contract: recall across sessions, contradiction flagging, staleness, promotion after three successes, load, the scheduled forget pass, continuity and project isolation.
- A checkpoint is an audited chain entry: verification walks only the records since the last checkpoint proven by a full walk; tampering before that checkpoint is caught at the next full walk. `godmode doctor` now exits 1 with an `archive-chain-broken` finding when its walk fails.
- Every record names its writer and carries a derived trust; an operator correction outranks an agent record, a secret in free text refuses the write, and only a subject's creator can close it.
- Instruction-shaped text in a tool result is recorded as untrusted content, a claim that cites it is capped at observed and marked, and the session brief states that tool output and fetched files are data, never instructions.
- Recurring failure modes are pattern records that accumulate occurrences instead of duplicating.
- Claims record a working-tree fingerprint and verdicts record their witness's hash at cite time, `claim --stale` reports a claim whose tree or a verdict whose witness changed since, and a citation of a record sequence that does not exist is refused.
- The state home and anchor cache are created owner-only, and doctor warns when group, world, Everyone or Users can read or write the state home (mode bits on POSIX, the DACL on Windows).
- When a host sends a `usage` block on Stop/SessionEnd, it is recorded per event, `status remaining --digest` shows the session's spend from it, and `ceilings` counts tokens from it for the current session.
- An agent's guard reaches the compiled law only through a promotion approved by a different actor with an independent re-run; an operator's own guard is the second actor and needs no promotion. A promotion names the structured fields an unstructured lesson lacks, is approved once, and is refused as stale once its subject has moved on - a retirement is never silently undone. The three-session ladder feeds the same pipeline, and its five structured fields are synthesized from the cluster's own counters, not authored analysis.
- Upgrading a project whose lessons predate that rule no longer empties its Code of Law: the first `law compile` records one chained migration naming the cutoff sequence and the guards it grandfathers, those laws are marked [GRANDFATHERED] in the file with the steps to convert one, and `law hygiene` counts the ones still unapproved. A guard recorded after the rule shipped still needs a second actor, and retiring a grandfathered guard still lifts it.
- A lesson can carry an enforce predicate; a matching write is refused with the guard as the remedy.
- Run `godmode doctor` once after upgrading: it warms the enforce-predicate sidecar outside the write lock, so the first live write on an archive that has never had it does not hold the lock for several seconds.
- `atlas law ratify` accepts a law, guard or skill change only after the checker proved in the same session that it fails a planted bad case, and never from the proposer.
- Every skill carries a PURPOSE file citing the records that motivated it, and the skill linter requires one.
- Six new skills ship through skill-forge with purpose files, routing evals and flow tests: second-look, changelog, host-sync, codegraph, skill-eval, spec-lifecycle.
- Copilot and Kiro hook manifests are generated, wired through the launcher and covered by the host matrix.
- `hooks wire --all --dry-run` previews every host's wiring with the same code that applies it, merges only the Godmode-owned block of a shared config, and `hooks status` shows in-sync, drifted or absent per host.
- One documented hook contract every host manifest is tested against; the same command gets the same decision from Bash and PowerShell.
- The dispatch workflow gains a generated job per host manifest that installs the plugin that host's way and fires one hook.
- `doctor` flags a shipped hook missing from a host manifest and a manifest entry pointing at a missing file.
- `hooks wire --host codex` refuses from a linked worktree and names the primary checkout; the Codex probe records the installed-runtime premise first.
- Both hook launchers are generated from templates and diffed by a test; hosts without hook dispatch carry a named fallback tier instead of "unverifiable".
- `godmode ownership --check` shows which gate rule owns each path or command and fails when the decision table is stale against the classifier; the installer records every path it creates and `hooks status` reads that manifest.
- A hook that times out is recorded as `timeout`, distinct from a hook that returned nothing (`empty`).
- The gate classifies every component of a compound command and reports them; the worst component decides the call and an unknown component is protected by default.
- The gate applies a stricter policy row when no operator is present: lower ask threshold, no `--without-preflight`, faster capability expiry.
- `benchmarks/gate_latency.py --check` compares the PreToolUse fast-gate and escalation p95 against a committed baseline and fails on a regression of twenty percent or more; `--write-baseline` records the baseline and the hook timeouts it recommends.
- `grid` runs a meta-gate suite with a guaranteed-deny fixture for every protected class, and a test proves that removing one classifier rule turns the suite red.
- `selftest` lints assembled gate refusal and Stop-boundary messages in the session hook, the fast gate, the host renderer, and the staging hint against a bad/fixed wording table (bare tier codes, double negatives, remedies that name no command, internal record vocabulary, overlong sentences), and those messages now pass it.
- Done-bar checks carry a role: reviewer checks cannot be escalated, builder checks accept a recorded reason for a few turns; `governance --checks` prints the table.
- After two red retests of one check, a third edit to the same file is refused until an incident names the hypothesis and its falsifier.
- The installed pre-commit backstop refuses a commit that stages a version surface out of step with the others and names `version --reconcile` as the remedy.
- The git pre-commit backstop refuses a commit whose staged code files lack a green retest newer than their last edit, naming the stale files; an uncovered file (nothing retests it) or an unattested one (no recorded edit and no matching retest) is refused separately with its own remedy; a staged deletion is never checked; `godmode retest --run` refreshes a saved atlas index so the check answers fast on a clean tree; a build that has to run prints a one-line stderr notice first, instead of sitting mute for up to 180s.
- `atlas --direction` (also a `selftest` control and a CI gate) fails when a hook imports a runtime module outside the declared surface, when the fast gate imports any runtime module, or when the runtime imports a hook.
- `verdict record` carries `checked`, `not_checked` and per-criterion evidence, a PASS is refused while anything is not checked, the witness may not be the checker, and `--payload` files for `verdict record` and `claim` decode strictly (duplicate keys, unknown fields and trailing data are refused); hook input stays tolerant.
- `remember --kind decision --subject absorb:<item>` validates both verdicts and refuses an adopt or extend verdict that cites no source file, so a surface read can park or skip an item but never fund code.
- `godmode read` records what was opened (path, lines, digest); absorb decisions cite receipts and a README-only reading is refused as surface-only; `parity --sources` shows files opened per source.
- A hypothesis or incident whose falsifier was never run ages into a preflight finding after two days; `verify --falsifiers` runs the due ones and attests them.
- An obligation can name what blocks it; `status remaining` lists it under its blocker, and phantom or circular blockers are refused.
- `atlas graph rebuild|query|verify` derive a typed, time-valid evidence graph from the archive; `atlas closure` refuses to decide against an unverified graph.
- `atlas loop advance` refuses a third identical failure signature and records a halt; `atlas loop resume` reopens only with evidence from a different actor.
- `evals --ratchet` fails on any skill whose routing score drops below the committed baseline (`evals/baseline.json`, which only rises), and `evals --determinism` runs the offline harness twice and names any case whose route differs; both run in CI.
- The eval report carries one row per skill per declared model and flags a skill that passes only under its authoring model; with no per-model measurements declared, every row replays the same run.
- The flaky-test retry runner records every isolated rerun, `trends` ranks flakes by frequency, and the preflight reports a flake retried three or more times that carries no lesson.
- The flaky retry runner trips a breaker: an id that fails N isolated retries in a window is parked with a reason and re-admitted only after cooldown.
- Preflight findings carry a failure class (a blank or unknown class is itself a finding), each preflight record counts findings per class, and `trends` shows a class that recurs across rounds.
- `metrics` reports plan adherence, tool-selection rate and execution efficiency as exact ratios over the archive's own records, and `trends` carries the three per runtime version.
- The PostToolUse edit hook now records one `edit-recorded` bookkeeping action per edit-shaped tool call (path plus a distinguishing operation digest) - the real source `plan_adherence` checks against the plan's declared fence - and every detector that reasons about repeated or unattested operations (the loop, watchdog, and action-transparency checks) treats it as bookkeeping, never as an operation of its own.
- `selftest` fails on any CLI verb that no test, no public doc, or no skill names, so a verb cannot ship untested or unfindable.
- `docs/COMMAND-REFERENCE.md` is generated from the CLI's own parser (`scripts/dev/build_command_reference.py`) and listed in the README's docs index, so the public command reference cannot drift from what `--help` actually says; `tests/test_command_reference_drift.py` fails the build if the generated file and the parser disagree.
- Release notes carry the gate's measured p95 line, and the notes check refuses notes without it.
- Branches declare a role: maintained branches get the plan-and-test discipline, spikes do not, and only the operator (`--as-operator`) can declare a branch a spike.
- A 5-Whys record must validate its chain backwards, name immediate, preventive and detection countermeasures, and cannot end at a person or "human error".
- Competing hypotheses are records with a kill experiment; a fix may cite only a hypothesis whose kill ran and did not fire.
- A test per host proves that installing a new version over an old one leaves exactly the new payload.
- PDCA, OODA and the research read order are recorded SOPs with a verb per phase; metrics shows cycle time per phase.
- Commands are parsed once under their shell's semantics before classification, so Bash and PowerShell get the same decision; a corpus differential reports any decision flip between two commits.
- The first Edit or Write that makes an unplanned change span a second file now asks for confirmation (it is an ask, not a refusal) until a plan is recorded and approved; the agent can approve its own plan, so this enforces the planning step, not operator consent. Single-file edits and edits of 40 lines or fewer stay free, and shell writes (`echo >`, heredocs, `tee`, `mv`) are outside it.
- The RCA ritual is a checklist template; a record that skips a step is incomplete.
- An incident carries its reproduction command and its red run; a fix claim verifies only against the same command green.
- Six more skills ship with purpose files, routing evals and flow tests: memory-gardener, impact-gate, research, replicate, evidence and triage.

## Changed

- Host capabilities are a closed enum; the host support matrix is generated from it and from each row's reference and replicating test, and can no longer drift.
- The host-reach preflight finding is blocking only for a host that cites neither a replicating test nor a reference still to read; a host whose hook path is replicated and pinned by a test is reported as awaiting live confirmation instead of failing the run.
- `hooks wire --all --host <name>` now refuses (exit 1) instead of silently wiring every host and ignoring the `--host` scope - any script already passing both flags together needs to drop one.
- Generated host manifests take their hook timeouts from the committed gate-latency baseline's recommended values when present, with the previous constants as defaults. A recommendation only raises a timeout above its default, never lowers it, until that hook path is measured directly.
- The stdio MCP adapter is host-generic and opt-in (per request, no port), served to a second host through a generated manifest, with the same four tools on both.
- The fast gate defers its subprocess import to the escalate branch, so the allow path imports nothing beyond the standard library it already used.
- `guard` returns a `brief` with Context, Options, Resolution and Accepted cost so a protected action is decided from what it costs if wrong, and the governance skill presents that brief verbatim.
- The stale-lock advisory now fires only when the archive's write lock is actually held (probed the same way the writer itself acquires it), not merely when its sidecar file is old, since that sidecar can outlive the process that held it.
- `resume` lists declared state before inferred state, names a conflict between the two with the declaration winning, and adds a per-day catch-up section when more than one day passed since the last checkpoint.
- An ask or obligation idle for several turns is re-surfaced once and then left quiet for a cooldown instead of being re-listed every turn.
- The absorption reader's import-verdict vocabulary now matches the write-time gate's: an `exists` verdict grades like a settled `n-a`, and `unread` is accepted as a known token but still grades as half-recorded, since it names a surface read that never opened the source.
- Every skill description names the cases it is not for, near-negative routing rows pin them, and `selftest` fails on a skill whose frontmatter lacks the clause, exceeds its budget or references a path that does not exist.
- The routing and charter eval snapshots now include the release checklist's pre-tag version check, which is an advisory charter rule and ranks first for release preparation.
- The prepublication deny-name check reads its name list from `deny-names.txt` in the Godmode state home when `GODMODE_DENY_NAMES` is unset, so the class is measured without a per-shell variable.
- The session brief caps each section, names what it trimmed, and, like every gate message, leads with the rule, then the detail, then a checklist.
- The investigation skill runs the postmortem flow: validated 5-Whys, competing hypotheses, reproduce-first and the RCA checklist.
- `version --reconcile` now lists each drifted surface with a remedy, and reports a hand-edited manifest description; the root `plugin.json` description and version are generated by `bindings --write` from `packaging/hosts.json`, so that text is written in one place.

## Fixed

- Archive appends are serialized by an operating-system advisory lock that is released when the writer exits, so a crashed writer no longer blocks the next append until an age-out; the previous exclusive-create path remains as a fallback where no locking module exists.
- A checkout copied together with its `.git` (a moved clone, a test harness copy) keeps reading its own archive: the project key the archive was created under counts as its own identity, so records past the read index no longer fail verification as a project identity mismatch.
- `export` writes records in canonical order with a seal line, so two exports of the same archive are byte-identical regardless of directory listing order.
- `context-status`, `doctor` and the archive's chain check report the first broken record's sequence, file and line instead of a bare failure, and a missing archive verifies as an intact empty one.
- `law compile` no longer reverts the Code of Law skill's own text. Its embedded template had fallen behind the reviewed wording, so every compile silently rewrote the skill to claim the law file is always present, dropping the correction that a project with no guarded lessons legitimately has no file. The template now carries the reviewed text, and a compile is idempotent against it.
- A lesson recorded with `--standing` keeps that flag and is always delivered in the session brief, ahead of the newest guarded lessons, instead of falling off once newer lessons arrive.
- Every hook event degrades to exit 0 with a recorded reason when its bookkeeping fails; the PreToolUse deny path stays fail-closed, and a test per event proves it.
- The Windows hook launcher derives the plugin root from its own location and tries `py -3` before `python` and `python3`, and passes gate exit codes through unchanged.
- `bin/godmode.cmd` now probes `py -3` before `python` and `python3`, and calls every shimmed interpreter (a pyenv-win shim or a venv activation-style `.bat`/`.cmd` wrapper needs `call` to return control), matching the fix already proven in `hooks/run-hook.cmd`.
- A prompt that is a subagent's hand-back message no longer mints an operator request, and a subagent's stop never evaluates the parent session's open requests: a subagent's scope is its own dispatch.
- The stop hook, status, preflight and history read open asks through one reader with one window, so a closed ask never reappears on one surface while another shows it closed.
- A pinned lesson caps a claim's grade only when the lesson names a path or command stem the claim cites; lessons that merely share vocabulary are listed as advisory and no longer block a verified grade.
- `claim --verify` grades exit-bearing forms (`--quiet`, `-q`, `cmp -s`, `test`, `merge-base --is-ancestor`) as falsifiable without a wrapper script; state-reporting commands still cap at observed.
- `precheck --preflight` removes stale `.godmode-preflight-*` scratch directories beside the repository before it runs and reports them, so an aborted earlier run no longer leaves worktrees behind that `cleanup: confirmed` never saw.
- The scratch-directory allowance no longer treats an unexpanded `~` or `$VAR` target as a temp path when the process runs under the temp directory; the containment check already refused it.
- `selftest`'s verb-coverage control reads the verb list from the generated command reference instead of the live parser (no import cycle), and the concurrency scenario's documented lock shape is versioned so the registry can tell drift from intent.
- CI now initializes the archive and opens a session before running the skills' behaviour probes, which a fresh checkout never had; the dispatch run had only been green because the unit tests initialized the repository as a side effect.
- The prepublication citation check also covers documents under tests/, which ship to every reader like any other tracked file.
- An empty or whitespace-only pre-tool payload is refused before it is counted against the project's tool-call budget.
- The false-green rate counts every verified claim on record instead of only the newest 500.
- Hooks are much faster, most of all in projects where Godmode was never initialized. There, every hook now checks for Godmode state with a few file lookups and exits silently without loading the runtime: the pre-tool gate no longer starts a second interpreter, and Stop, SessionEnd and prompt events no longer load the archive or run git. A host's own diagnostics should no longer see these hooks time out or suggest disabling the plugin.
- The hook launcher finds Python once and stores its path in the Godmode application directory, so later hooks start one interpreter instead of two. On Windows it tries `python`, then `py`, then `python3`, and uses the slow Microsoft Store alias only when nothing else is installed.
- In a project without Godmode, exiting no longer prints `SessionEnd hook ... failed: Hook cancelled`. In an initialized project, SessionEnd does less at exit: a transcript over 1 MiB is measured at the next session start instead.
- In an initialized project that is not a git repository, hooks no longer run git calls that were bound to fail on every Stop and every archive lookup.
- In a project with a large archive, hooks no longer check every record file one at a time on each call. On a 20,000-record archive, a gated tool call that goes to the full hook dropped from about 20 s to about 2 s, and Stop from about 8 s to about 2 s.
- The publication name check now also scans test files for names it must not publish. Forge-URL fixtures in tests/ are still not reported, since testing forge-URL detection needs them.
- The publication checks now read commit messages. A push publishes every message in its range, and until now no check read one. The name check and the prepublication check scan each unpushed message for private paths, names it must not publish, and outside forge links. A `--message-file` mode serves a local commit-msg hook.
- A stalled test no longer costs a release check its full hour. Each shard runs under a per-test watchdog that re-arms at every test boundary. A test or class fixture that runs past ten minutes has every thread's stack dumped, and the check reports the stuck frames by name instead of a bare timeout.
- The compiled law file keeps citation text out of the shared file: a law whose lesson subject cites a paper is titled from its guard, and its reason omits the cited text; the lesson itself keeps the citation in the local archive.
- The oracle-tamper checks no longer link a test through a name that appears only in a comment, no longer read a changed exact count as a reduced bound, and no longer hide a neutered checker line because a different line of the same workflow dropped a test.
- The release preflight no longer refuses a tree whose only changes are untracked files. It never validated those files, so stray scratch output only blocked runs; the report still names them as not validated.
- `observe`, the would-have counts, `authorize stage --from-last-refusal` and the flaky-test ranking now read every record on file instead of the newest 500, so a long history no longer hides or undercounts entries.
- The no-terminal password message and the irreversible-command refusal name the launcher by its real path instead of a placeholder or a bare `godmode` command.
- Uninstalling from the install manifest now also drops the removed files from the manifest, so `hooks status` no longer reports them missing and the next install does not inherit them.
- `godmode evals` no longer fails the code-of-law behaviour assertion on a project that has no laws yet: the `law show` probe now checks that the verb reports its laws list rather than requiring a guard to already exist in the archive.
- `hooks wire` names every target project-relative in its report, even when the project path was given through an alias or an unnormalised spelling; it used to print the absolute resolved path in that case.
- `law amend` no longer makes an operator's law vanish when an agent rewords it: an amendment written without operator trust is recorded as pending, the last authorised guard stays in force, and `law compile`, `law show` and the compiled file mark the pending sequence; the operator amends in place with `law amend --as-operator`.
- An agent can no longer lift an operator's law with `remember --kind lesson --status superseded`: for a lesson, `superseded` is a close the single-writer guard refuses below the creator's trust, and `law compile` treats any lift written below the standing law's trust as pending rather than as a retirement.
- `reanchor` commit snapshots and remaps write again: the fingerprint kept the commit subject line under a key the archive now reads as a semantic decision, so every snapshot before a history rewrite was refused; snapshots taken before this change still remap.

## Security

- Every path Godmode resolves from a record, a manifest or a host payload is contained to the project or the state home after symlink resolution; an escape is refused or skipped, never followed.

## Limits

- **Laws inherited from before this release are marked grandfathered: they bind, and
  nobody has ever approved them.** `law compile` now requires a second actor's approval
  before a guard becomes law, and every guard your project recorded before that rule
  existed would otherwise disappear on the first compile. Instead the migrating compile
  records one chained migration naming its cutoff and marks those laws `[GRANDFATHERED]`
  in the compiled file. The file itself carries the steps to convert one into an approved
  law or to retire it, and `godmode law hygiene` counts the ones still unconverted.
- **A second actor is only as separate as the agent id it runs under.** The approval
  pipeline compares agent ids, so a single process that renames its id can promote a guard
  and then approve its own promotion. Treat approval as a guard against accident, not
  against a determined self-promotion; an operator's own guard is the second actor
  already and needs no promotion at all.
- **One skill routes at 0.8, and the baseline records 0.8 rather than rounding up.**
  `godmode-host-sync` still answers one near-negative case - "explain what one specific
  hook event does without checking any host's wiring state" - because the negative
  phrasing donates the skill's own vocabulary. The eval ratchet is registered at the
  measured 0.8, so it guards the real value; raising it needs a reword across the shared
  routing corpus rather than a one-line change. Every other skill measures 1.0.
- **`godmode recurring` misses its three-second budget on a large archive.** On a full
  archive it costs about 4.4 seconds, most of that in the pass that mines repeated asks.
  The answer is correct; it is slower than the budget it is held to. Run it when you are
  not waiting on it.
- **A skill proposal's evidence is checked for existence and distinctness, not for
  relatedness.** `godmode skill forge --success-evidence seq:<n>` needs three citations,
  refuses fewer than three *distinct* sequences, and refuses a sequence nothing was ever
  appended at. Nothing checks that the cited records are successes of the task type the
  skill is for: no record shape here carries a task type to match against, so relatedness
  would be a guess dressed as a guard. That judgement stays yours, and the skill says so.
- **Live hook proof exists for two hosts.** Claude Code and Grok are proven by a
  chronicled live session. Codex has a replicating test and a read reference but no live
  session yet; Cursor, Gemini and Antigravity each have a reference still to read and
  neither a replicating test nor live proof. OpenCode, Pi and Goose reach the pre-tool
  gate only (Goose also a handful of on-demand verbs) by the shape of their adapter, which
  is design rather than a gap. Every non-`yes` cell in the generated feature-reach table
  states its own reason; read that table before trusting a host to stop anything.
- **The per-host CI job proves installation per host, not dispatch per host.** Each
  generated job installs the plugin that host's way, but the firing half exercises one
  shared launcher nine times, so only the install half is genuinely per-host. The job also
  treats any non-zero launcher exit as a failure, so a host whose deny protocol answers
  with a non-zero status would read as red even when it is behaving correctly.
- **In an initialized project, hook cost is still mostly starting Python.** In a project
  where Godmode is not initialized every hook now exits after one interpreter start, and a
  large archive no longer costs a stat per record. In an initialized project each call still
  starts Python and compiles the runtime from source, because hooks run with bytecode writing
  off. Shipping precompiled bytecode would remove most of that and is planned next.

- **A latency baseline is only as honest as the machine it was recorded on.** The
  committed baseline that `benchmarks/gate_latency.py --check` compares against, and that
  generated host manifests take their hook timeouts from, carries no record of how loaded
  that machine was. A baseline captured under load reads high, which makes the 20%
  regression trip harder to reach and the recommended timeouts more generous than they
  need to be. Re-record with `--write-baseline` on a quiet machine before treating any
  number in it as a target.
- **A mixed-version install misreports a busy archive.** An installed 0.3.27 CLI and this
  release's runtime disagree on the name of the archive's write-lock file, so once both
  have touched the same archive the older CLI reports "archive is busy" instead of naming
  the version mismatch. Until both sides agree, drive the archive through the versioned
  runtime rather than through a separately installed older CLI.
- **The archive holds its write lock for a whole preflight run.** A full `precheck
  --preflight` can run for tens of minutes and holds the lock throughout, so nothing else
  can record a claim, a lesson or a checkpoint meanwhile. Record what you need before you
  start one.
- **Identity is proven at the tail of the archive, not across the read index.** A record
  in the verified tail is checked against the project it belongs to; for records served
  from the trusted prefix the read index covers, the identity check was done when that
  prefix was verified and is not repeated on an ordinary read. A checkout copied together
  with its version-control metadata now reads its own archive correctly, but it still
  cannot append to it - write from the original location.
- **A refusal on the edit and write target-loop path leaves no refusal record.** Four
  deny boundaries refuse the call correctly and write nothing, so those refusals are
  missing from the refusal history and from the digest's gate counts. Read a refusal count
  as a floor, not a total.
- **An install-manifest write failure is silent.** The installer records every path it
  creates, but a transient failure to record one is swallowed, so `hooks status` can
  under-report a launcher path with nothing saying why. `doctor` still flags a manifest
  entry pointing at a missing file; it cannot flag an entry that was never written.
- **The unattended policy row is covered by a job-wide setting, not per test.** The CI job
  runs attended by design with one directed check for the unattended row, and 47 existing
  test modules still build their own raw environments; those are held only by that
  job-wide setting and by a regression ratchet that baselines them. A module run outside
  the job picks up whatever signal its own environment happens to carry.
- **The done bar can read plain status prose as a claim.** A progress sentence that names
  no file, commit or test is still classified as claim-shaped at the Stop boundary and
  blocked. There is no "this is a status report" marker yet: rephrase to name what was
  actually run, or record the claim the sentence is making.
- **The decision ontology added here is inert.** Nothing yet writes the key that opts a
  record into it, and its stated consumer groups by a different subject, so the ontology
  ships without reaching anything. Nothing depends on it either.
- **The skill faces ship partial.** Twelve new skills landed with purpose files, routing
  evals and flow tests, along with the method contracts, the SOPs, reproduce-first incidents,
  the hypothesis ledger, the RCA checklist and the plan-first gate. Eight further skill faces
  (loop-warden, release, host-probe, handoff, budget, ci, law and self-review) are carried to
  the next release.
- **Plan-first asks rather than refuses, and it watches edits only.** An unplanned change
  that reaches a second file is asked about, not denied, and a plan the agent approved itself
  satisfies it: it is a ritual, not consent. Shell writes (redirection, heredocs, `tee`, `mv`,
  `cp`) never reach it, and a new session or a checkpoint starts a new change.
- **Some ways of spelling a command still reach the gate unexamined.** `$'git'` and
  `${x:-git}` under Bash, `& (Get-Command git)` and dot-sourcing under PowerShell, a quoted
  sub-command or flag, and a terminal wrapper such as `script -qc` around an operator verb are
  not yet resolved to the program they run. The common quoted, escaped, called and full-path
  forms are.
- **The frozen-region guard watches edits, not shell writes.** It checks every Edit and Write
  that touches a marked region; a shell redirection or a rename goes around it.
- **The session brief is about 1,600 tokens against a 1,000-token goal.** The per-section caps
  keep it inside the host's limit, so it now parses where it used to be cut off mid-way, but
  the fixed guidance sections are added after the budget is applied and are not counted.

- **Twelve of the gate's twenty-one category floors equal the fallback tier.** Removing one of
  those rows from the tier table would change nothing observable, so a regression there cannot
  be caught by a test today. Each floor is to be pinned explicitly, or the fallback made distinct,
  in a later release.
- **Tool-call counts are kept per recorded session, not per agent.** The pre-tool gate
  charges each call to the most recently opened session on record, or to `unsessioned` when
  none is open, and by design no hook opens a session. Two agents working in one repository
  at once (worktrees share one archive) are counted together against whichever session was
  opened last, so a tool-call ceiling can trip early for one and late for the other, and two
  calls landing at the same moment can each miss the other's count. Open a session per agent
  with `godmode session open` when the counts matter.

## Benchmarks

Gate latency (p95, n=21): fast_allow 162 ms, escalate 624 ms

## Verifying

- Memory and the archive: `python -m unittest tests.test_forget tests.test_memory_contract tests.test_supersession tests.test_verified_checkpoints tests.test_writer_trust tests.test_untrusted_marker tests.test_pattern_records tests.test_evidence_fingerprint tests.test_state_home_acl tests.test_usage_ledger tests.test_archive_lock_kernel tests.test_archive_copy_identity tests.test_export_determinism tests.test_verify_names_break`
- Law, approval and grandfathering: `python -m unittest tests.test_law_approval tests.test_law_bond tests.test_law_enforce tests.test_law_hygiene tests.test_lesson_schema tests.test_standing_law_pinned tests.test_law`
- Skills and evals: `python -m unittest tests.test_godmode_second_look tests.test_godmode_changelog tests.test_godmode_host_sync tests.test_godmode_codegraph tests.test_godmode_skill_eval tests.test_godmode_spec_lifecycle tests.test_purpose_lint tests.test_skill_frontmatter tests.test_routing_stability tests.test_eval_ratchet tests.test_evals_models`
- Hosts, wiring and installation: `python -m unittest tests.test_host_manifests tests.test_host_matrix_is_generated tests.test_hooks_wire tests.test_hook_contract tests.test_ci_host_jobs tests.test_launcher_pair tests.test_launcher_root_fallback tests.test_doctor_wired_hooks tests.test_codex_premise tests.test_mcp_stdio tests.test_ownership tests.test_manifest_timeouts`
- The gate, the hooks and what they refuse: `python -m unittest tests.test_gate_corpus tests.test_gate_fast tests.test_gate_latency_check tests.test_meta_gate tests.test_hook_never_raises tests.test_failure_semantics tests.test_refusal_lint tests.test_unattended_tier tests.test_dependency_direction tests.test_path_containment tests.test_governance_preview`
- Claims, verdicts and the done bar: `python -m unittest tests.test_verdict_strict tests.test_claim_calibration tests.test_absorb_requires_code_read tests.test_read_receipts tests.test_falsifier_aging tests.test_donebar_roles tests.test_two_reversals tests.test_closure_precommit tests.test_pin_relevance tests.test_obligation_dag tests.test_graph tests.test_atlas_loop`
- Preflight, flakes, trends and the published surfaces: `python -m unittest tests.test_flake_ranking tests.test_retry_breaker tests.test_finding_class tests.test_agentic_metrics tests.test_preflight_scratch_sweep tests.test_reach_reference_required tests.test_verb_coverage tests.test_command_reference_drift tests.test_version_drift_precommit tests.test_subagent_scope tests.test_request_reader tests.test_silence_reinjection tests.test_session_precedence tests.test_docs_lint tests.test_release_notes tests.test_workflow_hardening`
- `python -m unittest discover -s tests` for the whole suite.
