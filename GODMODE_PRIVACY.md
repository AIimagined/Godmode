# Godmode Privacy Contract

Godmode runs on demand and performs no network access. It does not collect telemetry,
usage analytics, crash reports, prompts, conversations, tool transcripts, source-code
bodies, environment dumps, API keys, passwords, or authentication tokens.

The local continuity store contains only structured operational facts intentionally
submitted through Godmode plus file metadata and hashes produced by explicit inspection.
The request ledger records each operator ask as a digest and up to 24 keywords drawn from
it - never the sentence itself - so an ask stays reviewable without the prompt being stored.
Secret-shaped values are rejected before persistence. Repository remote addresses are
represented only by one-way hashes.

`privacy` scans the local store for secret-shaped material. `export` emits a bounded,
sanitized summary rather than the raw record archive. Removing the state directory
removes Godmode's local memory; no remote copy exists.
