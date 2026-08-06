# Generic adapter: any agent, shell and JSON only

An agent whose host is not Claude Code, Codex, or Grok can still drive Godmode.
The contract is three things the poorest host already has: a shell, JSON on
stdout, and exit codes. Nothing here requires a plugin system.

## Enforcement honesty

On an unlisted host every control is **SOFT**: Godmode evaluates and reports,
but nothing forces the agent to consult it before acting. State this in the
first session report. `python scripts/godmode.py --project . capabilities`
prints the exact table; do not claim HARD enforcement the host cannot hold.

## Protocol

1. **Open** — `session open --label <task>`; keep the returned session id.
   The handshake in the response is the model-independent opening state.
2. **Act through commands** — every consequential step maps to one command:
   `verify` to run checks (the runner records the exit code, not your report),
   `attest` for steps without a command, `claim` for statements about project
   state (cite `rec:`/`file:`/`cmd:` evidence or the grade downgrades),
   `planmode specify|start|approve` before mutation, `guard` before protected
   operations.
3. **Read exit codes** — `0` proceed, non-zero stop and read the JSON payload;
   in `GODMODE_MODE=guided` every refusal carries `guidance` naming what was
   missing and the next action.
4. **Close** — `session close`; an unattested HARD rule, uncited claim, or
   half-done pair blocks closure. Report the block verbatim, not a summary.

## Output discipline

All commands accept `--json` (compact, sort-keyed) for machine parsing and
`--brief` for one-line human relay. Identify the agent via environment:
`GODMODE_HOST`, `GODMODE_MODEL`, `GODMODE_EFFORT`, `GODMODE_ENFORCEMENT=SOFT`
— every record is attributed, so a later host can audit what this one did.

## Minimal loop (any language)

```sh
python scripts/godmode.py --project . --json session open --label task
python scripts/godmode.py --project . --json verify tests --command "python -m unittest"
python scripts/godmode.py --project . --json claim "tests pass" --grade verified --cite "cmd:python -m unittest"
python scripts/godmode.py --project . --json session close
```
