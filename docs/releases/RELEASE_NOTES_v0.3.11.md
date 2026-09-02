# Godmode v0.3.11

The reach release. Two new host adapters: a pi extension that becomes the
approval flow pi ships without (pre-execution interception, fail-closed once
configured), and an MCP ledger server offering claim, checkpoint, status, and
resume to goose and any MCP host - honestly graded ledger-only, because MCP
tools are additive and cannot intercept a host's other calls.

The discipline gets a voice: the session brief now opens with the doctrine
block - seven named reflexes (THE RECORD RULE, THE DONE BAR, THE TWO-REVERSALS
LAW, GREEN ADDS NOTHING, SUPERSEDE DON'T RE-LITIGATE, ASK THE RECORD FIRST,
LEAVE A TRAIL) an agent can cite when one decides something. Every notice got
a plain-language pass: action first, the fix command spelled out.

Drip-fed operator requests resurface mid-work when a reply touches their
subject, not only at handover review. Claim resolutions carry a loss-averse
`asymmetric_score` beside the untouched symmetric one. Routing evals gain a
stability snapshot: a case that flips verdict with no rule change is named
config-fragile and decides nothing. `status absorb-docs` learned the
lead-emoji status dialect real files speak.

## Verifying

- `python -m unittest discover -s tests` - the full suite.
- `godmode resume` - the brief opens with the named doctrine block.
- `godmode status absorb-docs <file>` on an emoji-status markdown - the
  mapping shows review/proposed states, nothing writes without `--write`.
- `python -m unittest tests.test_goose_mcp_adapter` - the MCP conversation
  battery drives the server over real stdio.
