# Godmode v0.3.20

The channel release. Most of what this release fixes was already built and
never arrived: advisories the model could not see, a brief Grok discarded,
an allow Antigravity read as a denial, a done-bar Cursor never ran. A sweep
of the research ledger's hook-bearing plugins on 2026-09-07 showed where
each host actually reads its hooks, and every finding ships here with the
field reports that named the cost.

## What the model reads

`systemMessage` is shown to the operator only; the model never sees it. The
allowed-call advisories (evidence pipe, checkpoint pressure, verify
promotion, observe) and the post-edit findings now also ride
`hookSpecificOutput.additionalContext` on Claude, Codex and Grok, or
`agent_message` on Cursor, never a decision key. Stop-time notices are
parked beside the claim echo and reach the model at the next prompt
boundary. On Grok, whose guide says SessionStart stdout is ignored and an
allowing prompt hook's stdout is discarded, every parked context rides the
first allowed tool call as PreToolUse `additionalContext`. Pinned live on
Grok 1.0.13 Windows: the model's reply quoted the hook-tagged continuity
brief verbatim.

The prompt nudge names the verb at the moment of demand: a plan-shaped ask
names `godmode plan`, a reversal names `verify --command` and
`differential`, the fix shape names `atlas closure`, the ship shape names
`precheck --about` for work that never leaves the machine. The done bar
reads the session's recent tool output, so a readout the reply repeats is
not a claim, and names the `--verify` recording first.

## What the hosts actually do

- **Grok.** The live SessionStart payload carries `hook_event_name:
  SessionStart`, so the hook read Grok as a Claude session and never parked
  the brief; fixed. Its session_start hook measured 14.8 s and 18.2 s live
  against a shipped 10 s timeout, on a hook that runs in under a second
  when called directly and a cold `pwsh` of 3.3 s; SessionStart now gets 30
  s, Grok's own default.
- **Antigravity.** Its CLI treats a PreToolUse response without a decision
  as a denial. Both the fast gate and the full hook now speak
  `{"decision": "allow"}` there, and the CLI's own tool vocabulary
  (view_line_range, propose_code, create_file and the rest) is mapped.
- **Cursor.** `beforeShellExecution` was adapted but not counted as a
  pre-tool event, so a Cursor shell call never received a `permission` key;
  it now denies a forced push in Cursor's dialect. The Cursor manifest had
  no stop hook, so the done-bar never fired there; it now declares `stop`
  with `loop_limit: 1` and answers with a `followup_message`.
- **Every host.** Hooks return on the first complete JSON payload instead
  of waiting for EOF (a Windows host's pipe close can lag past the
  timeout). The launcher starts every interpreter with `-I -B`, isolated
  from `PYTHONPATH` and the user site. `SubagentStop` routes to the done
  bar, advisory only.

## Gates that see more, ask less

- `verify --offline` runs a check under the netgate socket audit with every
  proxy variable pointed at a closed local port; any connection seen
  attests the check `blocked`, with the audit's stated gap.
- `"inline_interpreter": "scan"` in the authorization policy reads a Python
  `-c` or heredoc payload with `ast` and clears it only under a read-only
  module allowlist with no exec, dynamic import, dunder access or
  open-for-write; each clearance leaves a record; the default posture is
  unchanged.
- A paid-iteration tripwire counts checks blocked for dialling out against
  a declared `paid_iterations` ceiling; every prompt records a git baseline
  and a Stop names files changed since it when no check and no claim landed
  in between.
- `atlas map` on this repository dropped from 137.5 s to 30.5 s, and every
  atlas verb takes `--budget`; a stopped build states its gap. A dormant
  family whose ledger is a bound role document is named as that document.

## Verifying

- `python -m unittest tests.test_advisory_channel` - the advisory rides
  `additionalContext` on Claude and `agent_message` on Cursor; a Cursor
  forced push is denied in Cursor's dialect.
- `python -m unittest tests.test_grok_brief_delivery` - the brief survives
  the prompt boundary and rides the first allowed call, once.
- `python -m unittest tests.test_antigravity_allow tests.test_cursor_stop` -
  the spoken allow, the bridge vocabulary, the Cursor `followup_message`.
- `python -m unittest tests.test_hook_stdin tests.test_launcher_isolation` -
  each hook exits with the pipe held open; a poisoned `PYTHONPATH` never
  reaches the gate.
- `python -m unittest tests.test_verify_offline tests.test_turn_tripwires
  tests.test_inline_interpreter_scan tests.test_atlas_registry` - the
  offline audit, the tripwire and baseline, the scan posture, the atlas
  ceiling.
- CI: dispatch `godmode-verify.yml` on main and on the tag; every leg must
  be green before the GitHub release is published.

Full detail per change: `CHANGELOG.md`.
