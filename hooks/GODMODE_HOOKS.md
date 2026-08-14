# Godmode Host Adapter

`godmode_session_hook.py` is a bounded stdin/stdout adapter for hosts that support
lifecycle or pre-action hooks. Claude Code registers only its non-blocking
`SessionStart` path through `hooks/hooks.json`. That path is silent until the current
project has been explicitly initialized, then emits a structured continuity brief as
additional context. It does not read the Claude transcript; neither does `pre-compact`
or `pre-action`.

Supported explicit events are `session-start`, `pre-compact`, `session-end`, and
`pre-action`. Lifecycle checkpoints accept only the structured fields `summary`,
`status`, `next`, `hypothesis`, `outcome`, and `evidence`; unknown fields, prompts,
and messages are ignored. `session-end` is the one exception: it also reads
`transcript_path`, if the host supplies one, for a best-effort, counts-only
measurement pass (tool names from a closed enum, command shapes, and token
totals from the transcript's own usage blocks) - never transcript content, and
a missing or unreadable transcript is recorded as a stated gap rather than an
error. Pre-action mode classifies an exact operation and denies protected work
unless a matching one-use capability is supplied.

## The pre-tool gate

`PreToolUse` is registered for mutating tools (`Bash`, `PowerShell`, `Write`,
`Edit`, `NotebookEdit`), but the script the host actually calls is
`godmode_gate_fast.py`, not `godmode_session_hook.py` directly. The fast gate
is a zero-import table lookup against `gate_table.json`: a command whose every
segment head lands on a vetted, host-parity, read-only floor (`git status`,
`git log`, `git diff`, ...) is allowed silently, in-process, with no
subprocess spawned. Anything else — a real mutation, an unrecognized command,
a fenced tool (`Edit`/`Write`/`NotebookEdit`), or any ambiguity the table
can't resolve — escalates: the fast gate re-feeds the exact request bytes to
`godmode_session_hook.py pre-action` unchanged and mirrors its stdout, stderr,
and exit code verbatim. Every ambiguous path resolves to escalate, never to
allow; the fast gate never itself decides `ask` or `refuse`.

On escalation, the full hook derives an operation from the tool payload,
meters the call, and answers in the host's own contract: silence allows, and a
refusal returns `permissionDecision: "deny"` with the reason. Three things can
refuse:

1. a protected operation with no matching one-use capability;
2. a declared run ceiling already reached;
3. a skip pattern — three mandated steps skipped this session.

This is the boundary that makes `tool_call_interception` real. The control
reports `HARD` only when `GODMODE_PRETOOL_GATE` is set, which the installed hook
sets; without a host calling the gate it reports `UNAVAILABLE`, because a control
nobody invokes is not a control.

**Costs and limits, stated.** `hooks.json` sets a 3s timeout on `PreToolUse`
(`SessionStart` gets 10s, `UserPromptSubmit` gets 30s). Measured directly
against `godmode_gate_fast.py` on Windows (2026-08-14, `python
hooks/godmode_gate_fast.py < payload.json`, 10 timed runs after one unmeasured
warm-up, median of the sorted sample): a fast-path allow (`git status`) has a
median wall time of **90.3ms** (range 82.8-108.2ms) — the table lookup plus
one Python interpreter start, no subprocess. An escalating call (`git push
--force origin main`, denied) has a median of **468.6ms** (range
334.6-514.6ms) — the fast gate's own startup plus the subprocess spawn of
`godmode_session_hook.py pre-action`, which resolves repository identity via
several `git` calls. Narrowing or widening the `PreToolUse` matcher narrows or
widens the meter with it: as shipped, the `tool_calls` ceiling counts mutating
calls, not every tool call. Tokens remain the host's figure and are labelled
`declared`, never `measured`, in the ceiling report. An uninitialized project
is never blocked, and an internal failure never blocks the host — a broken
gate must not brick a session.

The remaining events are not registered automatically because enforcement guarantees
vary by host. The adapter creates no listener, watcher, daemon, or background process.
A host must invoke a gate event and honor its exit code for enforcement to exist.
