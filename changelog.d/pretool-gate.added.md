A `PreToolUse` gate decides mutating tool calls in the host's own contract:
protected operations without a capability, reached run ceilings, and a
three-skip pattern all return `permissionDecision: "deny"` with the reason.
Tool calls and elapsed time are now measured by the runtime instead of
reported to it (tokens stay host-declared and are labelled as such), and
`tool_call_interception` reports `HARD` only where the gate is actually
installed.
