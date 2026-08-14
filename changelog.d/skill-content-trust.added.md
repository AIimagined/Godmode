Trust now reads skill, command, and agent content as untrusted input.

`godmode trust` scanned settings and MCP JSON only. A cloned repository's
`.claude/skills/**/SKILL.md`, `.claude/commands/**/*.md`, and
`.claude/agents/**/*.md` files are prose a host loads and follows the moment
a session starts, and nothing scanned them.

`scan_agent_configuration` now enumerates those files, capped at 400 with the
cap reported, and routes each through the same untrusted-content and secret
checks the repository sweep already applies. A line shaped like an
instruction produces a `skill-directive` finding naming the file, the line,
and the kind. A secret-shaped value produces a `skill-secret` finding. A
settings hook whose command classifies at R4 or above now also produces a
`hook-command-tier` finding, naming the tier, because a hook fires with no
per-call confirmation from the action gate.

Godmode's own six shipped skills are the population check: their SKILL.md
content runs through the new scan as part of the test suite and returns no
findings.
