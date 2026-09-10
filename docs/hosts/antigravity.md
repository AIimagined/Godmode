# Antigravity

**Current grade:** pre-tool gate `HARD` (confirmed live in the tenth field report); every other feature `PARTIAL` or `SOFT`; Stop hooks reported unreliable on Windows. `godmode capabilities --host antigravity` prints the grade from records, never from this page.

## Intercept events wired (`.antigravity-plugin/hooks-fragment.json`, `.agents/hooks.json`)

| Antigravity event | Godmode hook | Feature | Grade |
|---|---|---|---|
| `PreToolUse` | `godmode_gate_fast.py` | pre-tool gate | HARD (live refusal chronicled) |
| `PreInvocation` | `godmode_session_hook.py user-prompt` | prompt nudges, claim echo, request recording | PARTIAL |
| `PostToolUse` | `godmode_post_edit.py` | post-edit findings | PARTIAL |
| `Stop` (`{"decision": "continue"}` spelling) | `godmode_session_hook.py stop` | done-bar, stop notices | SOFT; not firing on Windows is field-confirmed |
| no session event in its five-event list | none | continuity brief | not reachable |

## Known host issues (working list)

- Fast "finished" declarations with the playable surface unverified. The scope gate (0.3.24) blocks a completion claim while this session's asks, plan steps, or criteria are open, on hosts whose Stop reaches the model.
- Sandbox-escape class findings bundled with Cursor, Codex, and Gemini CLI research.
- Headless stdout historically leaked to the TTY; adapters must not treat "the model said it ran" as a run. `claim --verify` and `verify --command` record the runner's exit code, not the narrative.
- `.agents/hooks.json` wiring: a project-level hook file pointing at a stale install path is dead wiring; `godmode doctor --host antigravity` names it.

## Proof recipe

1. `godmode init` in a repository, plugin installed, `gate_mode` not `observe`.
2. From the agent, run a protected command that must be refused (a forced push to a throwaway remote).
3. `godmode history --kind refusal --limit 1` shows the refusal with `observed: false` and the Antigravity host name: that is the pre-tool-gate proof, and it exists (tenth field report).
4. For the Stop path on Windows: a done-shaped reply must be blocked once and the block chronicled. Until that record exists, the done-bar grade stays `SOFT` here and the README says so.
