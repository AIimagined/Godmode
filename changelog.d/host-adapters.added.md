Instruction-file adapters for OpenCode (`AGENTS.md`), Cursor
(`.cursor/rules/godmode.mdc`), and Gemini CLI (`GEMINI.md`) drive the CLI over
shell, JSON, and exit codes; each host's enforcement is declared in
`packaging/hosts.json`, `capabilities --host X [--record]` prints and records
the negotiated table, and a test fails if an adapter document's stated levels
drift from the declaration.
