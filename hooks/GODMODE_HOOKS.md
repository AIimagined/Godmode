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

The remaining events are not registered automatically because enforcement guarantees
vary by host. The adapter creates no listener, watcher, daemon, or background process.
A host must invoke a gate event and honor its exit code for enforcement to exist.
