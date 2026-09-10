# Cursor

**Current grade:** `PARTIAL` until a live protected command writes a refusal record; `UNAVAILABLE` when the host has not declared the plugin. `godmode capabilities --host cursor` prints the grade from records, never from this page.

## Intercept events wired (`.cursor-plugin/hooks.json`)

| Cursor event | Godmode hook | Feature |
|---|---|---|
| `sessionStart` | `godmode_session_hook.py session-start` | continuity brief |
| `beforeSubmitPrompt` | `godmode_session_hook.py user-prompt` | prompt nudges, claim echo, request recording |
| `preToolUse`, `beforeShellExecution` (failClosed) | `godmode_gate_fast.py` | pre-tool gate |
| `afterFileEdit` | `godmode_post_edit.py` | post-edit findings |
| `stop` (followup_message, loop_limit 1) | `godmode_session_hook.py stop` | done-bar, stop notices |
| `preCompact`, `sessionEnd`, `subagentStop` | matching subcommands | recovery point, session end, subagent done-bar |

Every row above is *wired*, not *proven*: the plugin-root expansion by Cursor's loader and the payload field names were read from Cursor's documentation, not observed from a Cursor session on this machine.

## Known host issues (working list)

- Sandbox escapes reported via workspace hook config, virtualenv interpreter edits, and alternate git metadata paths (Pillar / Bleeping Computer, Jul 2026). Godmode's `hook-as-code-write` category (0.3.24) asks on writes to `.cursor/hooks.json`.
- Background agents show higher n+1, regression, and missing-test rates in one agent-PR defect study; the dirty-diff ask (0.3.24) is the local control.
- Permission `ask` is documented; whether a deny decision reaches the tool call has not been observed here.

## Proof recipe (how HARD gets earned)

1. Install the plugin in Cursor and open a repository with `godmode init` done and `gate_mode` not set to `observe`.
2. From the agent, run a protected command that must be refused, for example `git push --force origin main` on a throwaway remote.
3. Run `godmode capabilities --host cursor` and `godmode history --kind refusal --limit 1`: a refusal record with `observed: false` and the Cursor host name is the proof. Until it exists, the grade stays `PARTIAL`.
4. Record it: `godmode attest host-proof-cursor --status ran --result "refusal seq <n>" --evidence rec:<hash>`.

No page, README row, or reach table may print `HARD` for Cursor before step 3 has a record.
