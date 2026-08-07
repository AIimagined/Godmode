# Godmode Host Adapter

`godmode_session_hook.py` is a bounded stdin/stdout adapter for hosts that support
lifecycle or pre-action hooks. Claude Code registers only its non-blocking
`SessionStart` path through `hooks/hooks.json`. That path is silent until the current
project has been explicitly initialized, then emits a structured continuity brief as
additional context. It does not read the Claude transcript.

Supported explicit events are `session-start`, `pre-compact`, `session-end`, and
`pre-action`. Lifecycle checkpoints accept only the structured fields `summary`,
`status`, `next`, `hypothesis`, `outcome`, and `evidence`; unknown fields, prompts,
messages, and tool transcripts are ignored. Pre-action mode classifies an exact
operation and denies protected work unless a matching one-use capability is supplied.

## The pre-tool gate

`PreToolUse` is registered for mutating tools (`Bash`, `PowerShell`, `Write`,
`Edit`, `NotebookEdit`). On each such call the adapter derives an operation from
the tool payload, meters the call, and answers in the host's own contract:
silence allows, and a refusal returns `permissionDecision: "deny"` with the
reason. Three things can refuse:

1. a protected operation with no matching one-use capability;
2. a declared run ceiling already reached;
3. a skip pattern — three mandated steps skipped this session.

This is the boundary that makes `tool_call_interception` real. The control
reports `HARD` only when `GODMODE_PRETOOL_GATE` is set, which the installed hook
sets; without a host calling the gate it reports `UNAVAILABLE`, because a control
nobody invokes is not a control.

**Costs and limits, stated.** The check resolves repository identity, which costs
several `git` calls — about 0.7s per mutating call on Windows, against about
0.1s for a read (read-only tools return before any of that work). Narrowing or
widening the matcher narrows or widens the meter with it: as shipped, the
`tool_calls` ceiling counts mutating calls, not every tool call. Tokens remain
the host's figure and are labelled `declared`, never `measured`, in the ceiling
report. An uninitialized project is never blocked, and an internal failure never
blocks the host — a broken gate must not brick a session.

The remaining events are not registered automatically because enforcement guarantees
vary by host. The adapter creates no listener, watcher, daemon, or background process.
A host must invoke a gate event and honor its exit code for enforcement to exist.
