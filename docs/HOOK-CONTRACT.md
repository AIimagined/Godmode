# Hook Contract

One contract every host hook manifest is built from and tested against. It
answers four questions the same way for every host: what a hook receives on
stdin, which host-specific variable it can read its own name from, what a
launcher looks like, and what an exit code or a stdout key is allowed to
mean. `tests/test_hook_contract.py` parses this file's own tables and checks
every generated manifest against them, so the doc and the generator cannot
drift apart silently.

`hooks/GODMODE_HOOKS.md` describes what Godmode's adapter does once a hook
fires; this file describes the wire format every host manifest speaks to get
there. Read both together.

## 1. Event names

An event name is the key a host's own hook configuration groups handlers
under (`PreToolUse`, `sessionStart`, `BeforeTool`, ...). Godmode never emits
a name that is not traceable to a host's own documented dialect or a live
capture of that host's real hook payload; an unverifiable name is left out
rather than guessed (`scripts/godmode_runtime/godmode_host_manifests.py`'s
own governing rule, unchanged by this contract).

### Emitted events per host

| Host key | Manifest shape | Events (closed set) |
|---|---|---|
| `claude` | shared `hooks/hooks.json` | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`, `Stop`, `SubagentStop` |
| `codex` | merged into the shared file; the project projection (`hooks wire --host codex`) additionally carries `PermissionRequest` | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`, `Stop`, `SubagentStop` |
| `grok` | merged into the shared file | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`, `Stop`, `SubagentStop` |
| `cursor` | dedicated manifest, camelCase dialect | `sessionStart`, `preToolUse`, `beforeShellExecution`, `stop`, `beforeSubmitPrompt`, `afterFileEdit`, `preCompact`, `sessionEnd`, `subagentStop` |
| `gemini` | dedicated settings fragment (merge target, not auto-discovered) | `SessionStart`, `BeforeTool`, `AfterTool`, `AfterAgent` |
| `antigravity` | dedicated fragment | `PreToolUse`, `Stop`, `PreInvocation`, `PostToolUse` |
| `copilot` | dedicated manifest (`.github/hooks/godmode.json`) | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PreCompact`, `SessionEnd`, `Stop`, `SubagentStop` |
| `kiro` | dedicated manifest (`.kiro/hooks.json`), declarative rule metadata only | `toolCall` |

Each row is the exact set a manifest builder is willing to emit today
(`godmode_host_manifests.HOOK_ARTIFACTS[<host>]["allowed_events"]`, or the
shared file's own top-level keys for `claude`). Proof: every host's builder
output equals its own allowlist exactly, never a superset —
`tests/test_host_manifests.py::EventAllowlistTraceabilityTests::test_codex_emitted_events_equal_the_allowlist`,
`test_cursor_emitted_events_equal_the_allowlist`,
`test_gemini_emitted_events_equal_the_allowlist`,
`tests/test_host_manifests.py::AntigravityArtifactTests::test_emitted_events_equal_the_allowlist`,
and `tests/test_host_manifests.py::CopilotManifestTests::test_emitted_events_equal_the_allowlist`
/ `KiroManifestTests::test_emitted_events_equal_the_allowlist`; the project
projection's added `PermissionRequest` key is pinned by
`tests/test_codex_windows_hooks.py`. `tests/test_hook_contract.py` reads
this table's host set from `godmode_host_manifests.HOOK_ARTIFACTS` itself
(plus `claude`, the one host in this table with no `HOOK_ARTIFACTS` entry
of its own) rather than a second, hand-typed host list, so a new dedicated
host manifest with no matching row here fails that test immediately.

## 2. The stdin JSON envelope

Every hook reads one JSON object on stdin. Field names arrive in at least
two casings across hosts (`tool_name` / `toolName`); Godmode reads either
through one lookup table rather than one branch per host.

| Field (canonical name) | Known aliases | Carries |
|---|---|---|
| `hook_event_name` | `hookEventName` | the event key that fired |
| `tool_name` | `toolName` | the tool the host is about to run or just ran |
| `tool_input` | `toolInput` | that tool's own argument object |
| `session_id` | `sessionId` | the host's session identifier |
| `cwd` | `workspaceRoot`, `workspace_root` | the project directory the call is scoped to; the operation is always read from this field, never from the process's own working directory |
| `request_id` | `requestId`, `toolUseId`, `tool_use_id` | a per-call identifier, used for metering |
| `transcript_path` | `transcriptPath` | a best-effort path to the host's own transcript file, read only for `session-end`'s counts-only measurement pass, never for content |

Proof: `tests/test_hostevent.py::FieldDualCasingTests::test_camel_and_snake_both_resolve`;
absence handling by `tests/test_hostevent.py::FieldDualCasingTests::test_absent_field_is_none_not_a_raise`.

A bare `{"operation": "..."}` object (no `tool_name` at all) is also
accepted — the host-neutral shape CLI probes and test harnesses use, pinned
by `tests/test_hostevent.py::BareOperationTests::test_a_bare_operation_string_is_carried_through_untouched`.

### `Bash` and `PowerShell` read the same field, one way

Both tool names extract the command text from the same `tool_input.command`
field, through the same function
(`scripts/godmode_runtime/godmode_guardrails.tool_operation`), before either
one reaches the classifier. There has never been a second, PowerShell-shaped
read of that field: `tests/test_hostevent.py::ClaudeAdapterTests::test_bash_powershell_carry_the_command_text`
pins that both names carry the command text identically today.

`scripts/godmode_runtime/godmode_sentinel.classify_action` — the function
that turns that command text into a protected/not-protected verdict — takes
an explicit `tool_name` keyword (default `None`). Since G-5 it selects one
thing only: the shell dialect the text is written in
(`scripts/godmode_runtime/godmode_parseview.dialect_for_tool`: `Bash` is
Bash, `PowerShell` is PowerShell, a `cmd` tool is cmd.exe, a shell tool whose
host does not declare its shell is read as both Bash and PowerShell on
Windows with the stricter verdict kept, and no tool name is Bash). The text
is parsed once under that shell's rules and lowered to the Bash spelling the
classifier reads (`godmode_parseview.lower`); from there every dialect runs
the same code path. So a command that means the same thing in both shells
reaches the same verdict whichever tool carried it -
`tests/test_hook_contract.py::ToolNameParseViewTests` calls `classify_action`
with both tool names (and with none) against the same text and asserts
byte-identical verdicts, and `tests/fixtures/gate_corpus.json` carries
`git commit` pairs annotated `"tool": "Bash"` and `"tool": "PowerShell"`
that expect the same decision. A command the two shells read differently is
judged by what its own shell would run: under PowerShell a backslash is
literal, so `Get-Content "C:\dir\"; git push --force` closes its string
and force-pushes, and is refused. The verdict's `operation_digest` is always
of the text as submitted. `python scripts/dev/corpus_differential.py --base
<sha>` classifies every corpus row at two commits and fails on any decision
flip that is not a `by-design` row with a note.

## 3. Matcher precedence

Three precedence rules apply, in this order, whenever more than one thing
could answer a question about a payload:

1. **Field-casing precedence.** When a payload names the same field under
   both a camelCase and a snake_case key, the camelCase spelling always
   wins, at every call site that reads that field
   (`godmode_hostevent.field`, the fast gate's own local lookup, and the
   full hook's `host_field` shortcut agree). Proof:
   `tests/test_hostevent.py::FirstAliasWinsTests::test_tool_name_camelcase_wins_over_snake_case`
   and `test_tool_input_camelcase_wins_over_snake_case`.
2. **Host-detection precedence.** Which dialect a payload is read as is
   decided by a fixed chain: the `GODMODE_HOST` environment variable, then
   `GROK_AGENT`, then `CLAUDE_CODE_ENTRYPOINT`, then the payload's own
   shape, then `"unknown"`. Proof:
   `tests/test_hostevent.py::HostDetectionChainTests::test_godmode_host_wins_over_everything`
   and `test_payload_shape_is_the_last_resort`.
3. **Tool-matcher precedence.** Godmode never ships two `PreToolUse`
   entries for the same host whose matchers could both fire on the same
   tool name: the shared file's `PreToolUse` block is one entry with one
   union-of-tool-names regex
   (`tests/test_host_manifests.py::SharedHooksFileTests::test_the_pretooluse_matcher_unions_every_host_tool_the_adapter_recognises`),
   and where a manifest legitimately needs more than one matcher block for
   one event (the shared file's `PostToolUse`, split between the edit
   family and the fetch family), the blocks' matchers are disjoint tool
   sets, so evaluation order never changes the outcome — there is nothing
   for the host's own matcher engine to disagree with Godmode about.

## 4. Env-var contract

| Variable | Set by | Read by |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` | the host, at hook-invocation time | the shared file's command strings (Claude, Codex, Grok) |
| `${PLUGIN_ROOT}` | not a real environment variable — a portable placeholder token the dedicated Cursor manifest carries, resolved at `hooks wire` time to an absolute path, the same way `${godmodePluginRoot}` and `${extensionPath}` below are | the dedicated Cursor manifest |
| `${godmodePluginRoot}` | placeholder, resolved by `hooks wire --host antigravity` | the dedicated Antigravity fragment |
| `${extensionPath}` | placeholder, resolved by whatever installs the Gemini fragment | the dedicated Gemini fragment |
| `CURSOR_PROJECT_DIR` | Cursor itself, per its own documented convention | Cursor's MCP manifest args only, never a hooks command string |
| `GODMODE_PYTHON` | the operator, optionally | both launchers, ahead of every interpreter probe |
| `GODMODE_HOST` | the operator, or a manifest's own `commandWindows` entry (Codex's project projection sets it explicitly) | the host-detection chain (rule 2 above), at the highest precedence |
| `GROK_AGENT`, `CLAUDE_CODE_ENTRYPOINT` | the host process itself | the host-detection chain, as fallbacks below `GODMODE_HOST` |

`${CLAUDE_PLUGIN_ROOT}`/`${PLUGIN_ROOT}` going unexpanded (a host that hands
the literal token to the shell rather than substituting it) is a pinned
corpus case, not a hypothetical: the launcher still resolves its own root
from its own path rather than trusting the variable, proven by
`tests/test_launcher_root_fallback.py::LauncherTests::test_windows_root_without_variable`
and `tests/test_launcher_root_fallback.py::ShLauncherTests::test_root_without_variable_still_answers_a_concrete_decision`.

## 5. Per-host launcher shape (generic families)

Every hook command Godmode ships routes through one of two generated
launcher files — `hooks/run-hook.cmd` or `hooks/run-hook.sh` — never a bare
interpreter invocation. Across the shapes a hook-bearing plugin can take,
three generic families recur, independent of which project uses which:

- **A single polyglot file**, valid as both a Windows `.cmd` and a POSIX
  shell script at once, so one committed file serves every shell a hook
  command runs under. This is the family Godmode ships
  (`hooks/run-hook.cmd`); `tests/test_launcher_pair.py::LauncherTemplateByteIdentityTests::test_cmd_launcher_matches_the_committed_polyglot_byte_for_byte`
  pins it byte-for-byte against its own generator.
- **A parallel native file per platform**: a second, OS-specific manifest,
  or a per-entry Windows-specific command field alongside the POSIX one.
  Godmode's own Codex project projection uses the second shape
  (`commandWindows` beside `command` on every entry, because Codex runs a
  project-level hook under PowerShell on Windows and under the user's
  detected shell everywhere else).
- **Explicit non-support**: no native Windows launcher at all, requiring a
  POSIX-capable shell (Git Bash, WSL) to run the hook body. Godmode does
  not take this path — both `hooks/run-hook.cmd` and `hooks/run-hook.sh`
  are generated for every install — but a host or a plugin that does is not
  reporting a defect; it is a documented, narrower floor.

macOS handling is thin across the ecosystem this contract generalizes from,
and Godmode's own launchers follow the same shape: the POSIX branch of the
polyglot (or the plain `.sh` sibling) is the whole of macOS support, with no
separate macOS-only branch, proven end-to-end by
`tests/test_launcher_pair.py::ShLauncherRunsEndToEndTests::test_sh_launcher_runs_a_hook_end_to_end`.

stdin-JSON-in, JSON-or-exit-code-out is the near-universal contract shape a
hook body speaks to its host once the launcher hands off to it; the
opposite design choice — fail-open on any hook error or timeout, so a
broken hook never blocks the call it was meant to gate — is a real,
documented alternative to Godmode's own default, which fails a *protected*
`PreToolUse` call closed and everything else open. Both defaults are stated
here rather than left implicit, because the difference is a design axis,
not a defect in either direction.

## 6. Exit-code and stdout semantics

Exit code `0` is used for every decided response, including a deny: this
is Claude's own tested contract (JSON on stdout signals the decision, not
the exit code), and every other documented dialect either matches it or
accepts it as an alternative to a nonzero exit. Exit code `3` never
appears in anything Godmode emits, proven by
`tests/test_hostevent.py::RenderDecisionTests::test_exit_code_is_never_three`.
Silence (`{}`, exit `0`) always means allow, on every host:
`tests/test_hostevent.py::RenderDecisionTests::test_allow_is_silent_on_every_host`.

`ask` is a real, separate decision only on hosts whose own documented
contract has one. Elsewhere it folds to `deny`, with a reason naming the
staged-capability remedy so the fold is never silent:
`tests/test_hostevent.py::RenderDecisionTests::test_claude_and_cursor_keep_ask_as_ask`
and `test_hosts_without_ask_receive_deny_naming_the_staged_remedy_style`.

### Decision-channel keys per host

Every field name below is the real, dotted path inside the JSON body a
decided response carries; whether the base decision arriving there is
`ask` or `deny` is stated in prose beside it, never inside the backticks,
so the backtick-quoted tokens are exactly the paths a parser can check
against the field names `render_decision` actually emits.

| Host key | deny/ask key(s) | additionalContext-analog | systemMessage-analog |
|---|---|---|---|
| `claude` | `hookSpecificOutput.permissionDecision`, `hookSpecificOutput.permissionDecisionReason` (ask is real here) | `hookSpecificOutput.additionalContext` | `systemMessage` |
| `codex` | `hookSpecificOutput.permissionDecision`, `hookSpecificOutput.permissionDecisionReason` on the PreToolUse gate; `hookSpecificOutput.decision.behavior` on its own PermissionRequest ask surface | `hookSpecificOutput.additionalContext` | not confirmed |
| `grok` | `decision`, `reason`, `hookSpecificOutput.permissionDecision`, `hookSpecificOutput.permissionDecisionReason` (ask folds to deny) | `hookSpecificOutput.additionalContext` (its docs call the shared dialect "largely compatible"; carried alongside its own keys) | not confirmed |
| `cursor` | `permission`, `user_message`, `agent_message` (ask is real here) | `agent_message` | `user_message` |
| `antigravity` | `decision`, `reason` (ask is real here) | not confirmed | not confirmed |
| `gemini` | not positively detected by the decision renderer today — falls to the same union-of-every-key fallback as an undetected host below (ask folds to deny) | not confirmed (fragment merge only) | not confirmed |
| `copilot` | not positively detected by the decision renderer today — falls to the same union-of-every-key fallback as an undetected host below (ask folds to deny); host detection itself has no branch for this host either, per HOOK_ARTIFACTS's own copilot gap text | not confirmed (top-level additionalContext is documented for it, but not yet what render_decision emits) | not confirmed |
| `kiro` | not positively detected by the decision renderer today — falls to the same union-of-every-key fallback as an undetected host below (ask folds to deny); host detection has no branch for this host at all | not confirmed | not confirmed |
| undetected host (`gemini`, `copilot`, `kiro` included, today) | `decision`, `reason`, `hookSpecificOutput.permissionDecision`, `hookSpecificOutput.permissionDecisionReason`, `permission`, `user_message`, `agent_message` — the union of every dialect's key, since detection failed and there is no dialect to narrow to | — | — |

Proof: `tests/test_hostevent.py::RenderDecisionTests::test_a_known_host_receives_only_the_keys_its_contract_documents`
for the `claude`/`codex`/`grok`/`cursor` rows, `test_an_undetected_host_still_receives_every_dialects_key`
for the undetected-host row (and `gemini`'s, `copilot`'s and `kiro`'s, which
this contract states share it), and `tests/test_hostevent.py::AntigravityAdapterTests::test_the_decision_dialect_is_decision_reason_and_ask_survives`
for the `antigravity` row. A cell marked "not confirmed" is a stated gap,
not a claim — the same posture `godmode_host_manifests.HOOK_ARTIFACTS`'s own
`gap` fields already take, never silently upgraded to a channel this
project has not verified.

## 7. Channel-absence policy

When a feature's advisory would ride a channel a host's own dialect does
not carry (no `ask`, no additional-context-shaped key, no operator-only
message key), Godmode's stated behavior is: never invent a channel a host
does not document, fold `ask` to `deny` naming the staged-capability remedy
(section 6), drop a pure advisory silently rather than mis-deliver it on a
key the host ignores, and never let a missing channel escalate a claim
about interception past what a live proof actually backs — `hooks status`'s
five-level scale (`HARD`/`DEGRADED`/`PARTIAL`/`SOFT`/`UNAVAILABLE`) exists
precisely so an absent channel reads as a stated gap rather than a silently
softened claim. Proof: `tests/test_failure_semantics.py::FiveLevelScaleTests::test_soft_registration_grades_soft`
and `test_partial_registration_with_no_proof_grades_partial`.

The per-feature, per-host cross of "this host lacks channel X, so feature Y
reads as Z" is generated data, not hand-maintained prose, once the typed
capability enum lands. Until then this section carries the placeholder
below, verbatim, between its own markers — a later generator replaces only
the table between them, never the surrounding prose:

<!-- GENERATED:HOST-CHANNEL-ABSENCE-MATRIX:BEGIN (filled by godmode_host_manifests.HOST_CAPABILITIES once it exists; do not hand-edit between these markers) -->

| Host | Channel absent | Godmode's behavior |
|---|---|---|
| _pending: generated by the typed capability enum_ | | |

<!-- GENERATED:HOST-CHANNEL-ABSENCE-MATRIX:END -->

## 8. Command routing and timeouts

Every command string any manifest builder emits routes through
`run-hook.cmd` or `run-hook.sh` — never a bare interpreter path — so root
resolution, the `GODMODE_PYTHON` override, and the interpreter probe stay
in one generated place regardless of which host loads the manifest. Every
hook entry carries an explicit timeout (seconds for every host except
Gemini, whose own documented unit is milliseconds), with one stated
exception: Codex's own project-level projection (`hooks wire --host codex`)
drops the timeout (and any `async` key) entirely, because Codex's bundled
hooks carry neither and its 600-second default exceeds every other budget
this contract declares. Proof:
`tests/test_host_manifests.py::SharedHooksFileTests::test_every_timeout_is_explicit_and_bounded`
for the general requirement, `tests/test_host_manifests.py::CodexProjectFallbackTests::test_projection_carries_every_event_with_absolute_commands`
for the stated exception, and the `run-hook.cmd`/`run-hook.sh` substring
checks `tests/test_hook_contract.py::LauncherRoutingTests` runs against
every builder's live output (never a hand-copied second list of the
commands, so a new builder that forgets the launcher fails the same test
the existing ones already pass).

## 9. What this contract's own test checks

`tests/test_hook_contract.py` reads this file's own tables (section 1's
event sets and section 6's channel-key table) and, for every host manifest
`godmode_host_manifests` can build today, asserts:

- the manifest's emitted event set is a subset of this file's declared set
  for that host (never a superset — an event this contract does not name
  is not one Godmode is willing to emit);
- every command in the manifest routes through the launcher (section 8);
- every hook entry carries a timeout;
- the host's decision-channel keys used anywhere in this codebase
  (`godmode_hostevent.render_decision`'s own per-host key sets) are exactly
  the keys section 6 declares for that host, so a new key added to one
  without the other fails the test instead of drifting silently.

A host manifest that is added to `godmode_host_manifests.HOOK_ARTIFACTS`
without a matching row in section 1 and section 6 of this file fails
`tests/test_hook_contract.py` immediately, by construction, rather than
shipping undocumented.
