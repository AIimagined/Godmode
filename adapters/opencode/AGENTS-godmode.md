# Godmode adapter for OpenCode

Append this file's contents to the project's `AGENTS.md` (or reference it from
there). It drives Godmode through the CLI. The pre-tool gate is a separate,
optional shim: copy `adapters/opencode/godmode.opencode.js` to
`.opencode/plugins/godmode.js` (project) or `~/.config/opencode/plugins/`
(global) and set `GODMODE_PLUGIN_ROOT` to the directory that contains
`hooks/godmode_gate_fast.py`. The shim runs the real gate on every `bash`,
`write`, `edit` and `patch` call through OpenCode's `tool.execute.before`
hook and throws on a deny - OpenCode's documented way to stop a tool - so
it fails closed: an `ask` folds to deny naming the staged-capability
remedy, and a missing interpreter or root refuses the call.

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
| tool_call_interception | SOFT |

tool_call_interception is SOFT: with the shim installed, every gated tool
call runs through the real gate and a deny throws before the tool runs;
without it, nothing intercepts a call the agent does not route through the
CLI. It becomes HARD only when a live OpenCode session's block is
chronicled as a proof (`hooks status`). State which of the two applies in
the first session report.
