<h1 align="center">
  <img src="./assets/godmode-logo.png" alt="Godmode" width="260">
</h1>

<p align="center">
  <b>Local-first context continuity and evidence governance for coding agents.</b><br>
  Zero runtime dependencies · zero network use · nothing leaves your machine.
</p>

<p align="center">
  <a href="./LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="Runtime dependencies: zero" src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen">
</p>

---

Your agent says "fixed it, the tests pass," and the same bug is back within
the week because the fix it typed over never re-ran the guard that would
have caught the regression. A number lands in a status report and nobody,
the agent included, can point to where it came from. A `git push` gets
approved because the message sounds confident, not because anything checked
what the command itself does.

## Install

```text
/plugin marketplace add AIimagined/Godmode
/plugin install godmode@aiimagined
/reload-plugins
```

That installs Godmode for Claude Code. Every `godmode ...` command shown
below runs through Claude Code's own Bash tool: installing a plugin adds
its `bin/` directory to that tool's PATH for the session, so pasting a
command into a Claude Code conversation, or asking Claude to run it,
works with no setup. Outside Claude Code, in your own terminal, call the
installed copy directly once you know its cached version directory
(`ls ~/.claude/plugins/cache/aiimagined/godmode/` lists it):

```console
$ python ~/.claude/plugins/cache/aiimagined/godmode/<version>/scripts/godmode.py init
```

Codex and Grok carry the same plugin package (`.codex-plugin/`,
`.grok-plugin/`) through their own marketplace flow. [Host support](#host-support)
states exactly what each host enforces, and what's verified about its own
`bin/` exposure, before you rely on it.

Next: run it for a week before you trust it for anything.

## Try it with no risk: observe mode

Godmode is a local, deterministic runtime that checks each of the three
problems above from a tamper-evident record of what actually happened,
computed into exit codes an agent cannot argue past. Enforcement is
opt-in and reversible: in observe mode, every gate that would deny or ask
instead records what it *would* have done and lets the command through.

1. Initialize the project once:

   ```console
   $ godmode init
   ```

2. Turn on observe mode with one file:

   ```console
   $ echo '{"gate_mode": "observe"}' > .godmode-authorization-policy.json
   ```

3. Work a normal week. Nothing is blocked.

4. Read what it would have caught:

   ```console
   $ godmode roi --digest
   ```

Every line in that digest is a would-have-denied or would-have-asked count,
by category, with the sessions it happened in. None of it merges with real
enforcement numbers, because none of these events were blocked. Delete
`.godmode-authorization-policy.json` (or remove its `gate_mode` key; an
empty `{}` file and no file at all are treated identically) to turn
enforcement on for real.

Next: pick a starting profile before you do.

## Starting profile

`godmode init --profile <name>` sets a starting posture on a ratchet that
only ever tightens. No profile removes an approval category an operator
already set on record.

```console
$ godmode init --profile novice     # asks before an ordinary file edit or a new branch
$ godmode init --profile standard   # today's defaults; writes nothing
$ godmode init --profile strict     # also asks before a release-affecting write
```

Next: see what each posture enforces.

## What it does

Six mechanisms carry the product. Each one below has a command that shows
its own current state, not a claim about it.

### The gate

The pre-tool boundary reads a command's own structure, not its vocabulary:
argument text, unrecognized binaries, and stream tools no longer read as
mutations by default. A vetted read-only call resolves in-process with no
subprocess spawned; anything else escalates to the full classifier.

```console
$ godmode capabilities
```

`tool_call_interception` reports `HARD` only when a host calls the gate
and honors its exit code. Run from a bare terminal, outside any hook, it
reports `UNAVAILABLE` for the command above, which is the honest answer.

### Verdicts

A "confirmed" claim needs a witness and an independent checker that
recomputes from the witness alone, never from what the claim's author
asserts. A refuting checker or a missing witness never folds into
"false." It reads `refuted` or `witness-malformed` instead, kept apart
from a claim nobody checked at all.

```console
$ godmode verdict record --claim "<claim>" --value <value> \
    --witness file:<path> --checker "<command>"
```

Full walk-through with both dispositions:
[docs/DEMO.md](docs/DEMO.md#4-one-verdict-walk-through-record-a-claim-watch-it-get-checked).

### Register

Findings, fixes, and rejected approaches outlive the session that produced
them. A disposition (`established`/`superseded`/`refuted`/
`worse-than-baseline`/`rejected-precedent`/`open`) needs a real citation to
leave `open`, and a closed one only reopens through a record that names
exactly what it supersedes.

```console
$ godmode register show --domain <domain>
```

### Measurement

A session-log pass counts tool calls, commands, test runs, and token
totals from a host transcript, using a closed vocabulary of names,
content-free by construction. The ROI report folds that beside gate
activity and verdict dispositions, held to a denylist that refuses
attribution language it never measured.

```console
$ godmode roi
```

### Trust

`skills/`, `commands/`, `agents/`, settings, and MCP configuration are
scanned for instruction-shaped and secret-shaped text before a session
trusts any of it. That content is prose a host loads and follows the
moment a session starts, not configuration a host merely parses.

```console
$ godmode untrusted --brief
```

### Run governance

A composable stop algebra (`MaxRecords`, `MaxWall`, `OperatorStop`,
`MetricPlateau`) replaces ad hoc loop conditions. A run that overruns its
wall-clock budget is killed, tree and all, and marked `truncated`, a shape
the verdict seam refuses to let anyone call `confirmed`.

```console
$ godmode ceilings --spent tokens=1200,tool_calls=40,seconds=90
```

Next: the numbers behind these mechanisms, each with its own reproduce
command.

## The numbers

Every row below was run against this repository to write this document.

| Claim | Reproduce it |
|---|---|
| 23 staged failure and attack shapes, all caught | `godmode scenarios --brief` → `all-caught \| total=23` |
| 13 adversarial attacks on the controls, all held | `godmode grid --brief` → `controls-held \| passed=13` |
| 81 capability entries reconciled, 0 dead pointers either direction | `godmode capabilities --reconcile` |
| 142-command gate regression corpus, zero regressions | `python -m unittest tests.test_gate_corpus -v` |
| Repository text scanned clean of instruction-shaped strings | `python scripts/godmode.py untrusted --brief` → `data-only` |

Two numbers below are a historical measurement, not a re-assertion of this
checkout's current state, and they carry their own basis instead:

| Measurement | Value | Basis |
|---|---|---|
| Old gate, median latency per gated call | 3.9s | 50-session window, measured 2026-08-14 ([release notes](docs/releases/RELEASE_NOTES_v0.2.11.md)) |
| New fast-path allow (`git status`) | 90.3ms median | 10 timed runs after warm-up, sorted-sample median, same source |
| New escalating call (`git push --force`, refused) | 468.6ms median | same method |

Full two-minute walk-through, every command pinned against the real CLI
parser: [docs/DEMO.md](docs/DEMO.md).

Next: what holds here depends on the host running it.

## Host support

Enforcement tier is computed from what the running environment proves,
never from the host's name. `godmode capabilities` reports `HARD` for
`tool_call_interception` only when a host sets `GODMODE_PRETOOL_GATE` by
calling the gate and honoring its exit code.

| Host | What's shipped | What's tested |
|---|---|---|
| **Claude Code** | Plugin, hooks (`SessionStart`, `PreToolUse`, `UserPromptSubmit`) | Live: the pre-tool gate and session hook run under this host every session this repository is worked in. |
| **Codex** | Same plugin package (`.codex-plugin/plugin.json`), same hooks convention | Packaged and unit-tested against the classifier; not independently live-probed under Codex itself. Whether Codex's own tool sandbox adds `bin/` to a command's PATH the way Claude Code's does isn't established here. |
| **Grok** | Same plugin package (`.grok-plugin/plugin.json`), same hooks convention | Packaged, same as Codex: not independently live-probed, `bin/` exposure unconfirmed. |
| **OpenCode, Cursor, Gemini CLI** | Instruction-file adapters ([`adapters/`](./adapters/README.md)), no plugin system | Attestation, claim-downgrade, and plan-gate controls run through the host-independent CLI and hold; `tool_call_interception` is declared `UNAVAILABLE` on all three, because none of them exposes a pre-tool boundary the adapter can call into. |
| **CI (GitHub Action)** | `action.yml`, integrity and changelog gates | Runs the same CLI the rows above do; no hook boundary involved. |

Developed and tested on Windows. The Windows kill path for an overrun run
is exercised for real in the test suite; the POSIX kill path (`os.killpg`)
is pinned by a mocked unit test, not live-probed on a POSIX host.

## Learn more

| Document | Covers |
|---|---|
| [docs/DEMO.md](docs/DEMO.md) | Two-minute terminal walk-through, every command pinned against the real CLI |
| [docs/CAPABILITY-COVERAGE.md](docs/CAPABILITY-COVERAGE.md) | What's `covered`, `partial`, or `not-claimed`, and at what grade |
| [docs/releases/](docs/releases/) | Release notes; every number in them carries its own basis |
| [docs/LISTING.md](docs/LISTING.md) | Marketplace listing text and manifest audit |
| [GODMODE.md](GODMODE.md) | Product guarantees, gates, and the start sequence |
| [GODMODE_PRIVACY.md](GODMODE_PRIVACY.md) | What is stored, where, and what never leaves |
| [THREAT-MODEL.md](THREAT-MODEL.md) | Threats, controls, and stated non-goals |
| [CHANGELOG.md](CHANGELOG.md) | Released changes |

Run `python -m unittest discover -s tests` to see today's pass count for
yourself rather than trust a number printed here that could go stale on
the next commit.

## License

Apache License 2.0 ([LICENSE](./LICENSE)); attribution and project identity
notices in [NOTICE](./NOTICE). Developed by AIimagined.
