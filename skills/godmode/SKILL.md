---
name: godmode
description: Coordinate local context continuity, evidence, and guarded coding workflows. Use when starting or resuming substantive repository work, when current reality is uncertain, or when a request spans multiple Godmode capabilities.
---

# Godmode

## Outcome

Establish what is true now, choose one bounded workflow, and leave locally verifiable
continuity without placing operational memory in tracked project files.

## Entry sequence

1. Identify the project root and read its active instructions.
2. Resolve the bundled `scripts/godmode.py` from the plugin root: use `$GROK_PLUGIN_ROOT`
   if set, else `$CLAUDE_PLUGIN_ROOT` if set, else the directory two levels above this
   skill file. Do not assume the user's project contains this script.
3. If Godmode is initialized, run `python <plugin-root>/scripts/godmode.py --project <root> context status`.
4. For a new or uncertain session, use `resume --refresh`; otherwise use `resume`.
5. Separate observed facts, declared intent, assumptions, conflicts, and open obligations.
6. Route to the narrowest specialist below.

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

## Session gates

Open substantive work with `session open` (the handshake states identity, dirty
files, active plan, obligations, invariants, and the host's enforcement table),
compile the project's rules with `charter`, and close through `session close` —
an unattested HARD rule, an uncited claim, or a half-done pair blocks closure.
`config check`, `roles`, and `operator` validate the project's declared
configuration; `locale check` validates translated guidance.

Read [godmode-command-surface.md](references/godmode-command-surface.md) only when the
requested operation needs exact CLI syntax.
