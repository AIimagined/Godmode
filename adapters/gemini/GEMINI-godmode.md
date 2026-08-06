# Godmode adapter for Gemini CLI

Append this file's contents to the project's `GEMINI.md` (or reference it from
there). Gemini CLI drives Godmode through the same CLI protocol; no extension
is required.

## Session contract

Open substantive work with `python scripts/godmode.py --project . session open
--label <task>` — the handshake includes the enforcement table; record it in
your first message so capability negotiation is visible, not assumed. Close
with `session close`; a non-zero exit blocks completion. Set
`GODMODE_HOST=gemini` and `GODMODE_ENFORCEMENT=HARD`.

Run checks through `verify`, record claims with `claim --cite ...` (uncited
claims are stored as hypotheses), gate mutations behind `planmode`, and
preview protected operations with `guard`.

## Enforcement on this host

Keep the default approval mode: the confirmation prompt on mutating actions is
what makes authorization HARD here. Auto-approval modes demote it to SOFT —
if enabled, say so in the session report.

| Control | Level |
| --- | --- |
| attestation_gate | HARD |
| claim_downgrade | HARD |
| plan_mode_mutation_gate | HARD |
| status_reopen_guard | HARD |
| authority_claim_detection | HARD |
| interactive_authorization | HARD |
| tool_call_interception | UNAVAILABLE |

tool_call_interception is UNAVAILABLE: GEMINI.md context is advisory and no
pre-tool boundary is exposed, so nothing intercepts a call the agent does not
route through the CLI.
