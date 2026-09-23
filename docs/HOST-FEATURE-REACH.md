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

<!-- godmode:matrix:begin -->

### Declared capabilities

Read straight from `godmode_host_manifests.HOST_CAPABILITIES` - a closed enum, not prose; `tests.test_host_manifests` fails a manifest that declares a channel or OS outside it.

| Host | Tier | Declared events | Declared stdout channels | OS |
|---|---|---|---|---|
| claude | hook | PostToolUse, PreCompact, PreToolUse, SessionEnd, SessionStart, Stop, SubagentStop, UserPromptSubmit | additionalContext, ask, deny, systemMessage | Linux, macOS, Windows |
| codex | hook | PostToolUse, PreCompact, PreToolUse, SessionEnd, SessionStart, Stop, SubagentStop, UserPromptSubmit | additionalContext, ask, deny | Linux, macOS, Windows |
| grok | hook | PostToolUse, PreCompact, PreToolUse, SessionEnd, SessionStart, Stop, SubagentStop, UserPromptSubmit | additionalContext, deny | Linux, macOS, Windows |
| cursor | hook | afterFileEdit, beforeShellExecution, beforeSubmitPrompt, preCompact, preToolUse, sessionEnd, sessionStart, stop, subagentStop | additionalContext, ask, deny, systemMessage | Linux, macOS, Windows |
| gemini | hook | AfterAgent, AfterTool, BeforeTool, SessionStart | deny | Linux, macOS, Windows |
| antigravity | hook | PostToolUse, PreInvocation, PreToolUse, Stop | additionalContext, ask, deny, systemMessage | Linux, macOS, Windows |
| copilot | hook | PostToolUse, PreCompact, PreToolUse, SessionEnd, SessionStart, Stop, SubagentStop, UserPromptSubmit | additionalContext, deny | Linux, macOS, Windows |
| kiro | hook | toolCall | additionalContext, deny | Linux, macOS, Windows |
| opencode | shim | none | deny | Linux, macOS, Windows |
| pi | none | none | deny | Linux, macOS, Windows |
| goose | mcp | none | additionalContext | Linux, macOS, Windows |

### Replication provenance

Every hook host cites the source read, or names the source still to read, and/or the test that replicates its mechanism - or the matrix generator itself refuses (`validate_reach_citations`) rather than printing a bare "unverifiable" row. A host whose Live proof column is not "(none)" is exempt from that citation requirement instead (`MATRIX_CITATION_HOSTS`, derived from this same table, never a hardcoded host name): it is proven by a chronicled live session - the interception-proof record cited there - rather than by replication.

| Host | Reference (read / still to read) | Replication test | Next live probe | Live proof |
|---|---|---|---|---|
| claude | (not required - live proof) | (none) | (none scheduled) | live proof, 2026-09-13, hook 0.3.26 |
| codex | (read) | `tests.test_launcher_root_fallback.LauncherTests.test_windows_prefers_py_launcher_with_3_flag` | post-0.3.28 | (none) |
| grok | (not required - live proof) | (none) | (none scheduled) | live proof, 2026-08-19, hook 0.3.0 |
| cursor | (still to read) | (none) | (none scheduled) | (none) |
| gemini | (still to read) | (none) | (none scheduled) | (none) |
| antigravity | (still to read) | (none) | (none scheduled) | (none) |
| copilot | (read) | `tests.test_host_manifests.CopilotManifestTests.test_replicates_the_shared_hooks_json_shape` | post-0.3.28 | (none) |
| kiro | (read) | `tests.test_host_manifests.KiroManifestTests.test_replicates_the_declarative_rule_shape` | post-0.3.28 | (none) |

### Feature reach

Legend: **yes** = event wired, channel declared, live proof; **partial** = wired, channel unverified or proof missing; **no** = the feature cannot fire on that host today - including a feature whose one needed channel the host's own capability enum does not declare (unreachable before any probe). Every non-`yes` cell's reason is stated in the reasons table below.

| Feature | claude | codex | grok | cursor | gemini | antigravity | copilot | kiro | opencode | pi | goose |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pre-tool-gate | yes | yes | yes | partial | partial | yes | partial | partial | partial | partial | no |
| advisories | yes | partial | yes | partial | no | partial | partial | partial | no | no | no |
| continuity-brief | yes | partial | yes | partial | no | no | partial | no | no | no | partial |
| prompt-nudges | yes | partial | no | partial | no | partial | partial | no | no | no | no |
| claim-echo | yes | partial | yes | partial | no | partial | partial | no | no | no | no |
| request-recording | yes | yes | yes | partial | no | partial | partial | no | no | no | no |
| post-edit-findings | yes | partial | no | partial | no | partial | partial | no | no | no | no |
| done-bar | yes | partial | yes | partial | no | partial | partial | no | no | no | no |
| stop-notices | yes | partial | partial | partial | no | partial | partial | no | no | no | no |
| auto-checkpoint | yes | yes | yes | partial | no | no | partial | no | no | no | partial |
| subagent-stop | yes | partial | yes | partial | no | no | partial | no | no | no | no |
| ask-decision | yes | partial | no | partial | no | yes | no | no | no | no | no |

### Feature reach reasons

The reason behind every non-`yes` cell above, `reach_table()`'s own per-cell text - the authored note, or, for a capability-driven downgrade, the enum-derived "unreachable: <host> does not declare the <channel> channel" statement.

| Host | Feature | Status | Reason |
|---|---|---|---|
| codex | advisories | partial | additionalContext documented on its PreToolUse wire; delivery to the model unproven live |
| codex | continuity-brief | partial | SessionStart fired live 2026-09-09 (session anchor recorded); whether Codex feeds its stdout to the model is unproven |
| codex | prompt-nudges | partial | UserPromptSubmit fired live 2026-09-09 (prompt-shape nudge recorded); stdout channel to the model unproven |
| codex | claim-echo | partial | UserPromptSubmit fires; stdout channel to the model unproven |
| codex | post-edit-findings | partial | PostToolUse declared since 2026-09-08; additionalContext documented; unproven live |
| codex | done-bar | partial | Stop declared since 2026-09-08; unproven live |
| codex | stop-notices | partial | Stop declared since 2026-09-08; unproven live |
| codex | subagent-stop | partial | SubagentStop declared since 2026-09-08; unproven live |
| codex | ask-decision | partial | PreToolUse ask accepted by its wire; PermissionRequest deny dialect projected; unproven live |
| grok | prompt-nudges | no | an allowing UserPromptSubmit hook's stdout is discarded by Grok; only parked echoes re-route |
| grok | post-edit-findings | no | PostToolUse stdout ignored by Grok |
| grok | stop-notices | partial | operator text only; the model copy rides the next allowed call |
| grok | ask-decision | no | no ask in its dialect; folds to deny |
| cursor | pre-tool-gate | partial | preToolUse and beforeShellExecution wired, failClosed; plugin-root expansion by its loader unverified |
| cursor | advisories | partial | agent_message on its own contract; unverified |
| cursor | continuity-brief | partial | sessionStart wired; channel unverified |
| cursor | prompt-nudges | partial | beforeSubmitPrompt wired since 2026-09-09; payload field names unverified |
| cursor | claim-echo | partial | beforeSubmitPrompt wired since 2026-09-09; unverified |
| cursor | request-recording | partial | beforeSubmitPrompt wired since 2026-09-09; unverified |
| cursor | post-edit-findings | partial | afterFileEdit wired since 2026-09-09; unverified |
| cursor | done-bar | partial | stop wired with followup_message under loop_limit 1; unverified |
| cursor | stop-notices | partial | stop wired; parked echo rides beforeSubmitPrompt; unverified |
| cursor | auto-checkpoint | partial | preCompact and sessionEnd wired since 2026-09-09; unverified |
| cursor | subagent-stop | partial | subagentStop wired since 2026-09-09; unverified |
| cursor | ask-decision | partial | permission ask is documented; unverified |
| gemini | pre-tool-gate | partial | BeforeTool fragment; fail-open host; no proof |
| gemini | advisories | no | fragment only; channel unverified - unreachable: gemini does not declare the additionalContext channel |
| gemini | continuity-brief | no | SessionStart fragment; channel unverified - unreachable: gemini does not declare the additionalContext channel |
| gemini | prompt-nudges | no | no prompt event in the fragment; Gemini's hooks list no prompt event godmode wires |
| gemini | claim-echo | no | no prompt event wired |
| gemini | request-recording | no | no prompt event wired |
| gemini | post-edit-findings | no | AfterTool fragment since 2026-09-09; unverified - unreachable: gemini does not declare the additionalContext channel |
| gemini | done-bar | no | AfterAgent is not a stop block; Gemini's hooks cannot block a reply, so the done-bar cannot fire |
| gemini | stop-notices | no | AfterAgent fragment since 2026-09-09 carries the notices as text; unverified - unreachable: gemini does not declare the systemMessage or additionalContext channel |
| gemini | auto-checkpoint | no | no session-end or compact event wired |
| gemini | subagent-stop | no | no subagent event in Gemini's list |
| gemini | ask-decision | no | no ask in its dialect; folds to deny |
| antigravity | advisories | partial | reason on an allow; delivery unverified |
| antigravity | continuity-brief | no | no session event in its five-event list; PreInvocation is wired as the prompt boundary, and the brief needs a start |
| antigravity | prompt-nudges | partial | PreInvocation wired since 2026-09-09 as the prompt boundary; unverified |
| antigravity | claim-echo | partial | PreInvocation wired since 2026-09-09; unverified |
| antigravity | request-recording | partial | PreInvocation wired since 2026-09-09; unverified |
| antigravity | post-edit-findings | partial | PostToolUse wired since 2026-09-09; unverified |
| antigravity | done-bar | partial | Stop wired; not firing on Windows is field-confirmed |
| antigravity | stop-notices | partial | Stop wired; Windows gap as above |
| antigravity | auto-checkpoint | no | no session-end or compact event in its five-event list |
| antigravity | subagent-stop | no | no subagent event in its list |
| copilot | pre-tool-gate | partial | PreToolUse wired in .github/hooks/godmode.json; render_decision has no dedicated copilot branch yet, so the exact deny shape it emits is unconfirmed |
| copilot | advisories | partial | top-level additionalContext documented for Copilot-shaped hosts; _advisory_body emits it nested-only (hookSpecificOutput.additionalContext), never top-level - a known gap, not merely unverified delivery |
| copilot | continuity-brief | partial | SessionStart wired; the emitter prints only the nested hookSpecificOutput.additionalContext there, not the top-level shape documented for Copilot-shaped hosts - a known gap, not merely unverified delivery |
| copilot | prompt-nudges | partial | UserPromptSubmit wired; delivery unverified |
| copilot | claim-echo | partial | UserPromptSubmit wired; delivery unverified |
| copilot | request-recording | partial | UserPromptSubmit wired; whether the event fires at all on Copilot is unconfirmed |
| copilot | post-edit-findings | partial | PostToolUse wired; delivery unverified |
| copilot | done-bar | partial | Stop wired; block delivery unverified |
| copilot | stop-notices | partial | Stop wired; notice delivery unverified |
| copilot | auto-checkpoint | partial | SessionEnd and PreCompact wired; unverified |
| copilot | subagent-stop | partial | SubagentStop wired; unverified |
| copilot | ask-decision | no | no ask in the documented Copilot-shaped dialect; folds to deny |
| kiro | pre-tool-gate | partial | a toolCall rule is wired in .kiro/hooks.json, routed through the launcher; Kiro's own event-name vocabulary beyond 'rule metadata that matches' is unread, so the trigger name is inferred, not confirmed |
| kiro | advisories | partial | HookResult's inject_context/modify factory is the plausible channel; unconfirmed |
| kiro | continuity-brief | no | no session-start rule declared; the read documentation names no session-boundary event |
| kiro | prompt-nudges | no | no prompt rule declared |
| kiro | claim-echo | no | no prompt rule declared |
| kiro | request-recording | no | no prompt rule declared |
| kiro | post-edit-findings | no | no post-tool rule declared |
| kiro | done-bar | no | no stop rule declared |
| kiro | stop-notices | no | no stop rule declared |
| kiro | auto-checkpoint | no | no session-end rule declared |
| kiro | subagent-stop | no | no subagent rule declared |
| kiro | ask-decision | no | ToolHookResult distinguishes a hard-security deny from a stateful-policy deny, not a documented ask; folds to deny |
| opencode | pre-tool-gate | partial | tool.execute.before shim relays a deny as a throw; one live block chronicled |
| opencode | advisories | no | no channel from the shim to the model |
| opencode | continuity-brief | no | no session event in the shim |
| opencode | prompt-nudges | no | no prompt event in the shim |
| opencode | claim-echo | no | no prompt event in the shim |
| opencode | request-recording | no | no prompt event in the shim |
| opencode | post-edit-findings | no | no post-tool event in the shim |
| opencode | done-bar | no | no stop event in the shim |
| opencode | stop-notices | no | no stop event in the shim |
| opencode | auto-checkpoint | no | no session-end event in the shim |
| opencode | subagent-stop | no | no subagent event in the shim |
| opencode | ask-decision | no | a deny is a throw; no ask surface |
| pi | pre-tool-gate | partial | tool_call extension; pi has no permission surface, so a deny is advisory |
| pi | advisories | no | no channel |
| pi | continuity-brief | no | no session event |
| pi | prompt-nudges | no | no prompt event |
| pi | claim-echo | no | no prompt event |
| pi | request-recording | no | no prompt event |
| pi | post-edit-findings | no | no post-tool event |
| pi | done-bar | no | no stop event |
| pi | stop-notices | no | no stop event |
| pi | auto-checkpoint | no | no session-end event |
| pi | subagent-stop | no | no subagent event |
| pi | ask-decision | no | no permission surface |
| goose | pre-tool-gate | no | MCP server exposes verbs as tools; no hook surface |
| goose | advisories | no | no hook surface |
| goose | continuity-brief | partial | the resume tool is available on demand; nothing fires it |
| goose | prompt-nudges | no | no hook surface |
| goose | claim-echo | no | no hook surface |
| goose | request-recording | no | no hook surface |
| goose | post-edit-findings | no | no hook surface |
| goose | done-bar | no | no hook surface |
| goose | stop-notices | no | no hook surface |
| goose | auto-checkpoint | partial | the checkpoint tool is available on demand; nothing fires it |
| goose | subagent-stop | no | no hook surface |
| goose | ask-decision | no | no hook surface |

<!-- godmode:matrix:end -->

## The verb layer

The CLI has 120 top-level verbs. Measured on 2026-09-08 against the skills
shipped with the plugin, the hook nudges, and the public docs:

| Named by | Verbs |
|---|---|
| a shipped skill | 5 |
| a hook nudge (prompt shape, done-bar, advisory) | 26 |
| public docs only | 34 |
| nothing | 57 |

A verb nothing names is reachable on every host and fires on none: the model
has no reason to run it. The utilization census (`godmode_census.py`) did not
see this, because it counts record kinds, and every kind has been written at
least once here; it reports "every tracked surface has been used" over the
same archive. The unit it counts is the wrong one for this question.

## Adapters without hooks

| Host | Surface | Reach |
|---|---|---|
| OpenCode | a plugin shim on `tool.execute.before` (`adapters/opencode`) | the pre-tool gate only, relayed as a throw; no session, prompt, edit or stop feature can fire |
| pi | an extension on `tool_call` (`adapters/pi`) | the pre-tool gate only; pi has no permission surface, so a deny is advisory |
| Goose | an MCP server exposing four verbs as tools: `claim`, `checkpoint`, `status_remaining`, `resume` (`adapters/goose`) | those four verbs on demand; no hook-borne feature at all |

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

## Why twenty releases did not catch it

Each release was driven by a single reported symptom on one host; the fix
repaired that channel on that host; the done-bar verified the fix's own
evidence and passed it. The gap for the gate on Codex and Grok was
recorded on 2026-08-29 (the Codex adapter's README and the capability
coverage table both say so), and it was never generalised to the other
hosts or the other features, because no artefact joined features to hosts
and no gate turned "unverifiable" red. The census was green for the wrong
unit. Obligations were closed one at a time without a same-class check
after each; the Grok brief fix proved the channel pattern and still
repaired only that channel.

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
6. The preflight gate treats "unverifiable" on a declared host as a finding,
   and the census counts verbs against what names them, so the two
   instruments that were green over this gap turn red over the next one.
7. Every verb nothing names gets a demand path (a skill line, a nudge, or
   retirement); the count of unnamed verbs is a doctor metric with a
   ceiling.

## Status, 2026-09-09

| Item | State |
|---|---|
| 1. Reach table in code | done: `scripts/godmode_runtime/godmode_reach.py`; `hooks status` carries the host's row, `doctor --host` names what cannot fire; a test holds every feature to a status on every host |
| 2. Output-channel table | the per-host dialects stay in `render_decision` and `_advisory_body`; the reach table states each channel's status per feature |
| 3. Wire the hosts' own events | done: Cursor `beforeSubmitPrompt`, `afterFileEdit`, `preCompact`, `sessionEnd`, `subagentStop`; Antigravity `PreInvocation`, `PostToolUse`; Gemini `AfterTool`, `AfterAgent`; Codex every shared event plus `PermissionRequest` in the project projection, with `commandWindows` for PowerShell |
| 4. Live proof per host | Codex: proven 2026-09-09 (0.153.4, Windows 11, PowerShell 7) through `codex exec --enable hooks`: SessionStart, UserPromptSubmit, PreToolUse and SessionEnd fired, a forced push was refused and Codex reported "Command blocked by PreToolUse hook". Cursor and Gemini are not installed on the development machine; Antigravity's new events await a probe |
| 5. Install-time reach report | done: `doctor --host <name>` returns `reach.cannot_fire` and `reach.partial` |
| 6. Gate and census turn red | done: the preflight gate raises `host-reach` for every declared host with no interception proof on the archive; `doctor` reports `verb_reach` |
| 7. Demand path per verb | done: 120 verbs, 100 named by a skill line, 34 by a nudge, 0 by nothing, 0 without a demand path; ceilings pinned at zero |

The Codex column of the reach table now reads `yes` for the pre-tool gate,
request recording and the auto checkpoint, `partial` for the rest with the
reason stated per cell. Codex also gained an ask: its PreToolUse wire
accepts `permissionDecision: ask`, and on `PermissionRequest` a godmode
deny answers in Codex's own `{behavior: deny, message}` dialect while an
ask or allow stays silent so Codex's approval flow decides.
