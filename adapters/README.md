# Host adapters

Claude Code, Codex, and Grok load Godmode as a plugin (manifests generated
from `packaging/hosts.json`). The hosts here have no compatible plugin system,
so their adapter is an instruction file wired into the host's own context
mechanism, driving the same CLI over shell, JSON, and exit codes (see
`skills/godmode/references/godmode-generic-adapter.md` for the protocol).

Enforcement is declared per host in `packaging/hosts.json` under `adapters`,
and each adapter document states the same table — a test fails if they drift.
HARD means decided outside model judgment; SOFT means surfaced and checked
after the fact; UNAVAILABLE means the host cannot hold the control and claims
resting on it stay unverified.

| Host | Wire it via | File |
| --- | --- | --- |
| OpenCode | project `AGENTS.md` (append or include); gate via `.opencode/plugins/godmode.js` | `opencode/AGENTS-godmode.md`, `opencode/godmode.opencode.js` |
| Cursor | `.cursor/rules/godmode.mdc` | `cursor/godmode.mdc` |
| Gemini CLI | project `GEMINI.md` (append or include) | `gemini/GEMINI-godmode.md` |
