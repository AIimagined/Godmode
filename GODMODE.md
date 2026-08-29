# Godmode

Godmode is a local-first plugin for Claude Code, Grok, Codex, OpenCode, and Antigravity - continuity and control during coding work.
It reconstructs repository reality from inspectable evidence, keeps operational
memory outside tracked files, and makes risky actions explicit before they happen.

## Properties

- No telemetry, analytics, update ping, cloud sync, network listener, inference proxy,
  background daemon, or idle token use.
- No raw prompt, conversation, tool-output, environment, credential, or source-code
  capture in the continuity store.
- Git repositories store state below their Git metadata. Non-Git projects use a salted
  identifier below the operating-system application-data directory.
- Records are schema-versioned, hash-chained, and written with atomic replacement.
- Protected operations receive a preview and require a scoped, expiring, one-use local
  capability. Godmode never executes the operation itself.
- Context reports distinguish observed facts, declared intent, assumptions, stale
  evidence, contradictions, and unresolved obligations.
- Godmode does not promise perfect memory or universal enforcement. It reports the
  exact evidence and adapter boundary behind every claim.

## Start

```powershell
python scripts/godmode.py --project . init
python scripts/godmode.py --project . inspect
python scripts/godmode.py --project . resume
```

Run `python scripts/godmode.py --help` for the command surface. The bundled
skills route agent work to continuity, investigation, governance, or skill forging.

## Gates

- Never commit without a changelog fragment and a passing integrity check.
- Never weaken a test without a recorded rationale; a guard must be observed failing before it counts.
- Never claim verified without a citation that resolves; an absence claim requires the search that would disprove it.
- Never mutate production or an unknown environment without an authorized capability.
- Only close a session after every mandated step is attested with evidence.

## Private-by-construction state

Operational plans, checkpoints, handoffs, decisions, lessons, incidents, sprint state,
and evidence are runtime records. They are not written into the working tree unless a
user explicitly exports a sanitized report.

Godmode is developed by AIimagined. The identity is metadata only and has no runtime
or user-interface behavior.
