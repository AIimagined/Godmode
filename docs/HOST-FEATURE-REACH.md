# Host feature reach

Which godmode feature can fire on which host, and why the ones that cannot,
cannot. Written 2026-09-08 after an operator finding: features that work on
Claude Code were assumed to work everywhere the plugin installs, and nobody
had a table that said otherwise. This is that table, read from the code
(`hooks/hooks.json`, the per-host builders in
`scripts/godmode_runtime/godmode_host_manifests.py`, the event branches in
`hooks/godmode_session_hook.py`) and from each host's own documentation of
what its hooks can return. Every "no" here is a stated gap, not a claim of
coverage.

## How a feature reaches a host

Every hook-borne feature needs three things from a host: an **event** the
host fires, a **channel** the host reads the hook's output on, and **live
proof** that the host actually dispatched the hook. A feature is reachable on
a host only when all three hold. The CLI verbs need none of these: they run
wherever the model can run a shell, but nothing points the model at them
except the hook-borne nudges, so on a host without the nudges the verbs are
dormant capacity.

## Events each host is wired for

| Host | Declared events (godmode's own manifest) | Live proof |
|---|---|---|
| Claude Code | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PreCompact, SessionEnd, Stop, SubagentStop | yes: refusals and requests land from a live session |
| Codex | the shared file above; Codex enables SessionStart, UserPromptSubmit, PreToolUse | partial: a `codex exec` session fired PreToolUse once (Sprint 4); the `/hooks` panel has also reported `Installed: 0`; a project-scope probe on 2026-09-08 ran no hook until the project was trusted |
| Grok | the shared file above (all eight) | yes, project-scope: session_start, pre_tool_use and the brief delivery pinned on 1.0.13 Windows on 2026-09-07; plugin-scope hooks do not dispatch in headless `grok -p` |
| Cursor | sessionStart, preToolUse, beforeShellExecution, stop | none: `${PLUGIN_ROOT}` expansion by the hooks loader is unverified; Cursor is not installed on the development machine |
| Gemini CLI | SessionStart, BeforeTool (a fragment an installer merges by hand) | none |
| Antigravity | PreToolUse, Stop | partial: a live session confirmed the gate (tenth field report); Stop not firing on Windows is field-confirmed |
| OpenCode | a plugin shim (`adapters/opencode`) that marks its spawns and relays denies | partial: a live shim block was chronicled once |
| Goose | an MCP server (`adapters/goose`): verbs as tools, no hooks | not applicable: no hook surface |
| pi | an extension (`adapters/pi`); pi has no permission surface | not applicable |
| Copilot CLI | environment detection only; no manifest | none |

## Channels each host reads

| Host | SessionStart stdout | UserPromptSubmit stdout | PreToolUse additionalContext | PostToolUse stdout | Stop block | Ask decision |
|---|---|---|---|---|---|---|
| Claude Code | read (additionalContext) | read | read | read | read | yes |
| Codex | assumed read (Claude-shaped keys documented) | assumed read | assumed read | not enabled | not enabled | no: folds to deny |
| Grok | ignored (its guide) | discarded for an allowing hook (its guide) | read, delivered after the call with its result | ignored (its guide) | read | no: folds to deny |
| Cursor | unverified | no such event wired (Cursor's is `beforeSubmitPrompt`) | `agent_message` on its own contract | no such event wired (Cursor's is `afterFileEdit`) | `followup_message` under `loop_limit` | yes |
| Gemini CLI | unverified | no such event wired | unverified | no such event wired | no such event wired | no: folds to deny |
| Antigravity | no session event (its lifecycle is PreInvocation) | no such event | `{decision, reason}` only | declared by the host, not wired | `{"decision": "continue"}` keeps working; Stop unreliable on Windows | yes |

## Feature reach

Legend: **yes** = event wired, channel read, live proof; **partial** = wired,
channel unverified or proof missing; **no** = the feature cannot fire on
that host today, with the reason.

| Feature (hook branch) | Claude | Codex | Grok | Cursor | Gemini | Antigravity |
|---|---|---|---|---|---|---|
| Pre-tool gate (deny / ask / allow) | yes | partial: proof thin | yes | partial: loader unverified | partial: no proof | yes |
| Allowed-call advisories (evidence pipe, checkpoint pressure, verify promotion, observe) | yes | partial | yes, after the call | partial: `agent_message` unverified | partial | partial: `reason` on an allow, delivery unverified |
| Continuity brief at session start | yes | partial: channel assumed | yes, via the first allowed call | partial | partial | **no**: no session event wired |
| Prompt-shape nudges (plan, fix, ship, reversal, resume, review, done-check, correction) | yes | partial | **no**: prompt stdout discarded; only the parked echo re-routes | **no**: prompt event not wired | **no** | **no** |
| Claim echo and obligation echo at the prompt boundary | yes | partial | yes, via the first allowed call | **no**: parked, never delivered (no prompt event) | **no** | **no** |
| Request recording, correction detector, turn baseline | yes | partial | yes (recorded; nudges lost) | **no** | **no** | **no** |
| Post-edit quality and impact findings | yes | **no**: PostToolUse not enabled | **no**: PostToolUse stdout ignored | **no**: not wired (`afterFileEdit` exists) | **no** | **no** |
| Done-bar (block once on an unrecorded done claim) | yes | **no**: Stop not enabled | yes | partial: shipped 2026-09-08, unverified | **no** | partial: Stop unreliable on Windows |
| Stop notices (investigation nudge, marginal return, tripwires, turn diff) | yes | **no** | yes as operator text; model copy waits for a prompt event that Grok discards, so it rides the next allowed call | **no**: parked for a prompt event Cursor never fires | **no** | **no** |
| SessionEnd auto checkpoint, PreCompact | yes | **no** | yes | **no**: not wired (`sessionEnd`, `preCompact` exist) | **no** | **no** |
| SubagentStop advisory | yes | **no** | yes | **no** | **no** | **no** |
| Grok headless plugin hooks | n/a | n/a | **no**: plugin-scope hooks do not dispatch in `grok -p`; project-scope hooks do | n/a | n/a | n/a |

## Root causes

1. **Claude's event set was the design baseline.** Each feature was built on
   the Claude event that fit it, and the other hosts received the pre-tool
   gate first and everything else only if the shared file happened to be
   read there. No artefact stated per host which features could fire, so
   the gaps were invisible; the utilization census counts records, not
   hosts.
2. **Output channels were assumed, not tabled.** SessionStart,
   UserPromptSubmit and PostToolUse stdout reach the model on Claude only.
   Each discovery was fixed in isolation (the Grok brief, then the Grok
   echo) instead of by a per-host channel table that every emitter reads.
3. **Live proof exists for two hosts.** Claude is proven from live sessions;
   Grok was pinned through project-scope hooks. Codex, Cursor, Gemini and
   Antigravity carry "unverifiable" in `hooks status`, and a Codex
   project-scope hook ran nothing until trusted. A host that never
   dispatched the hook cannot fire any feature, whatever the manifest says.
4. **Host events that exist go unused.** Cursor has `beforeSubmitPrompt`,
   `afterFileEdit`, `preCompact`, `sessionEnd`, `subagentStop`; Antigravity
   has `PreInvocation` and `PostToolUse`; Gemini has `AfterTool` and
   `AfterAgent`; Codex documents Stop, PostToolUse, SessionEnd, PreCompact
   and PermissionRequest. None are wired, so the prompt-, edit- and
   stop-borne features have no path on those hosts.
5. **`doctor --host` reports wiring, not reach.** It says whether the
   artefact and interpreter are present, not which features can fire, so
   an operator installing on Cursor is told the plugin is wired when most
   of it is dormant there.

## The program

Each item is an obligation on the record; this table is the contract the
work is measured against, and `hooks status` will carry the same matrix.

1. A per-host feature-reach table in code, rendered by `hooks status` and
   `doctor --host`, with a test that every hook-borne feature has a stated
   status on every host, so a new feature cannot ship without naming where
   it cannot fire.
2. A per-host output-channel table that every model-facing emitter reads,
   replacing the host checks scattered through the session hook.
3. Wire the events the hosts already have: Cursor's prompt, edit, compact,
   session-end and subagent-stop events; Antigravity's PreInvocation (as
   session start plus prompt) and PostToolUse; Codex's Stop, PostToolUse,
   SessionEnd, PreCompact and PermissionRequest (as the ask surface it
   lacks); Gemini's AfterTool and AfterAgent, with a full extension manifest.
4. Live proof per host, recorded: a protected command and a done-shaped
   reply inside each host's own session, chronicled the way Claude's and
   Grok's are, before any host's row says "yes".
5. An install-time reach report: `doctor --host <name>` names the features
   that cannot fire there and why, so an operator knows on day one.
