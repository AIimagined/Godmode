# Godmode adapter for OpenCode

Append this file's contents to the project's `AGENTS.md` (or reference it from
there). It drives Godmode through the CLI; OpenCode needs no plugin.

## Session contract

Before substantive work: `python scripts/godmode.py --project . session open
--label <task>` and read the handshake. Before completion: `session close` —
a non-zero exit means an unattested step, an uncited claim, or a half-done
pair; resolve it, never summarize past it. Set `GODMODE_HOST=opencode` and
`GODMODE_ENFORCEMENT=HARD` in the environment so records attribute this host.

Run checks through `verify` (the runner records the exit code), record state
claims through `claim --cite ...`, gate mutations through
`planmode specify|start|approve`, and preview protected operations with
`guard` — execution stays with the operator.

## Enforcement on this host

Configure OpenCode's permission model to `ask` for shell and edit tools; that
prompt is what makes authorization HARD here.

| Control | Level |
| --- | --- |
| attestation_gate | HARD |
| claim_downgrade | HARD |
| plan_mode_mutation_gate | HARD |
| status_reopen_guard | HARD |
| authority_claim_detection | HARD |
| interactive_authorization | HARD |
| tool_call_interception | UNAVAILABLE |

tool_call_interception is UNAVAILABLE: a pre-tool hook is possible via an
OpenCode JS plugin, but no shim ships, so nothing intercepts a tool call the
agent chooses not to route through the CLI. State this limit in the first
session report.
