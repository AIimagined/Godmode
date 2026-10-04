---
name: godmode
description: Coordinate local context continuity, evidence, and guarded coding workflows. Use when starting or resuming substantive repository work, when current reality is uncertain, or when a request spans multiple Godmode capabilities. Not for a single-file edit with no continuity, evidence or gating concern.
---

# Godmode

## Outcome

Establish what is true now, choose one bounded workflow, and leave locally verifiable
continuity without placing operational memory in tracked project files.

## Entry: one path

1. If the session hooks already delivered a brief (identity, last checkpoint, open
   obligations, standing laws, the host's enforcement table), that IS the entry: consume
   it. Do not run `context status`, `resume` or `session open` again for what it gave.
2. Run a verb only for what is missing or task-specific: `resume --refresh` after a
   compaction, a branch switch or an identity-drift finding; `session open` when no brief
   arrived (a host whose reach is not HARD, read from `hooks status`); `context status
   --scan` when filesystem drift matters; `charter` when the project's rules changed.
3. The CLI is the bundled `scripts/godmode.py` under the plugin root (`$GROK_PLUGIN_ROOT`,
   else `$CLAUDE_PLUGIN_ROOT`, else two levels above this file), called through
   `<plugin-root>/bin/godmode` (`bin\godmode.cmd` on Windows); it probes `python3`,
   `python`, `py` and honours `GODMODE_PYTHON`. Never write a bare `python` into a command.
4. Separate observed facts, declared intent, assumptions, conflicts and open obligations,
   then route to the narrowest specialist below.

On a host whose reach is PARTIAL or SOFT, the path is six verbs: `init` once, `session
open`, `resume`, `remember`, `claim`, `checkpoint`; stage a protected operation with
`authorize stage` before it. On Grok a brief rides the next allowed call and a refusal
reaches the model after the call; both are advisories.

## Routing

- Use `godmode-continuity` for session recovery, inventory drift, checkpoints, handoffs,
  decisions, fixed invariants, or missing context.
- Use `godmode-investigation` for bugs, failures, regressions, evidence gathering,
  root-cause work, or repeated unsuccessful attempts.
- Use `godmode-governance` before Git history changes, branch/worktree mutation,
  database changes, releases, deployments, destructive filesystem work, or external writes.
- Use `godmode-repair` when the operator says an answer did not land, asks for clarity,
  repeats a question, or asks what is being waited on.
- Use `godmode-skill-forge` only after a repeated reusable capability gap is proven.
- Use `godmode-second-look` to independently recheck a change, session, PR, or diff that
  already carries an accepted claim or verdict, before it is relied on.
- Use `godmode-changelog` to check the changelog-fragment gate, merge fragments for a
  version, and build and check that version's release notes.
- Use `godmode-code-of-law` at the start of every session and before every new task, when
  `GODMODE-CODE-OF-LAW.md` exists at the project root.
- Use `godmode-host-sync` to check whether every installed host still has the hooks wired
  and to reconcile a drifted or newly detected host's manifest.
- Use `godmode-codegraph` to rebuild or read the local code dependency graph: blast radius
  of a change, who calls a symbol, which tests a change must retest.
- Use `godmode-skill-eval` to score a skill's routing and behaviour against its baseline
  and to ratchet a regression rather than write it into the snapshot.
- Use `godmode-spec-lifecycle` to take a spec from draft through review, reconciliation and
  approval without approving its own plan or hand-editing the compiled law.
- Use `godmode-memory-gardener` at session close to list duplicate or contradicting
  lessons, preview expiry before it runs, and promote a ripe lesson with a cited rationale.
- Use `godmode-impact-gate` before committing a multi-module edit: fan-out, import
  direction, fence and paired artifacts, with a recorded decision as the escape hatch.
- Use `godmode-research` to survey an outside codebase: licence first, receipted source
  reads, and both verdicts, never adopt or extend from a surface read.
- Use `godmode-replicate` to rebuild a studied mechanism under Godmode names, pinned by
  a test proven able to fail and cited on its host row.
- Use `godmode-evidence` when a claim keeps being downgraded or cited evidence drifted:
  exit-bearing cites, falsifiers, stale-citation repair, one resolution.
- Use `godmode-triage` to work open asks down to closed, promoted, mapped or parked.
- Use `godmode-loop-warden` to cap a fix-and-retry cycle and cut it off when it repeats.
- Use `godmode-budget` to check a session's or a release's spend against its ceilings.
- Use `godmode-ci` to run CI's checks locally in CI's order before a PR, by shard.

Do not invoke every specialist. One specialist owns each overlapping capability; use a
second only when the request genuinely crosses its boundary.

## Working contract

Before editing, state the active objective, relevant repository identity, current
evidence, unresolved conflict, material assumption, and next safe action. Inspect before
mutating. Preserve unrelated user changes. Keep the implementation surface as small as
the complete solution allows.

Before reporting completion, run fresh verification that directly proves the claim.
Then record a checkpoint with evidence and remaining obligations. Never convert a
passing test, agent report, or plausible inference into a broader claim than it proves.

## Privacy boundary

Never submit prompts, transcripts, source bodies, credentials, environment dumps, or
private instructions to the archive. Store structured facts, hashes, relative paths,
statuses, and evidence references only. Godmode is on demand: do not start a watcher,
listener, proxy, daemon, update ping, or background process.

## Enforcement honesty

Before saying that "the gate blocked" a tool, read `hooks status`. HARD
means the host called the hook and a live deny was chronicled. PARTIAL,
DEGRADED, SOFT or UNAVAILABLE means the host is not proven to call the
hook: say that the CLI refused, or that the preview would refuse, and
never that the host stopped the tool.

## Closing

Close substantive work through `session close` once. An unattested HARD rule, an
uncited claim, a half-done pair, a regression (a step green earlier this session and red
since), or a declared perimeter check that never ran (`perimeter add|run`) blocks it.
A check already run on this HEAD this hour is evidence: `claim --verify` reuses its
attestation instead of running it again. `config check`, `roles` and `operator`
validate declared configuration; `locale check` validates translated guidance.

Read [godmode-command-surface.md](references/godmode-command-surface.md) only when the
requested operation needs exact CLI syntax. On a host with no godmode hook
support, read [godmode-generic-adapter.md](references/godmode-generic-adapter.md)
for the manual wiring path.
