<h1 align="center">
  <img src="./assets/godmode-logo.png" alt="Godmode" width="260">
</h1>

<p align="center">
  <b>A local, tamper-evident record of what a coding agent did, what it claimed, and what was verified.</b><br>
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
`.grok-plugin/`). On Grok:

```console
$ grok plugin marketplace add AIimagined/Godmode
$ grok plugin install godmode --trust
```

Codex installs the same package through its own plugin flow; its CLI
ignores plugin-bundled hooks (see the host table), so after installing run
`godmode hooks wire` inside each project. [Host support](#host-support)
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

This is declared from your own editor or terminal, outside a governed
session — that's the point: `.godmode-authorization-policy.json` is itself a
protected surface once a session is governed. A `Write`/`Edit` tool call
from inside a governed session targeting that file asks/denies the same as
one targeting `.git/` or `.env`; the gate cannot be told to stop watching by
the thing it watches. Entering or leaving observe mode is also chronicled
the moment it's next observed, so the posture change leaves a durable
record, not only the per-call advisory above.

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

The record carries the product; the gate is one consumer of it. Each
mechanism below has a command that shows its own current state, not a
claim about it.

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

### The gate

The gate is one consumer of the record: it computes its decision from what
the archive holds and writes its own decision back as a record, beside the
host's. The pre-tool boundary reads a command's own structure, not its vocabulary:
argument text, unrecognized binaries, and stream tools no longer read as
mutations by default. A vetted read-only call resolves in-process with no
subprocess spawned; anything else escalates to the full classifier.

```console
$ godmode capabilities
```

`tool_call_interception` reports one of five levels
(`UNAVAILABLE`/`SOFT`/`PARTIAL`/`HARD`/`DEGRADED`), never a claim the
evidence cannot back. `HARD` needs a fresh, live, chronicled proof: a host
that actually calls the gate and honors its exit code. Run from a bare
terminal, outside any hook, the command above reports `PARTIAL` in this
repository's own checkout (the shipped manifest wires the boundary, but
nothing just proved it live) — the honest middle answer, not a guess in
either direction.

### Fleet

More than one agent on a project shares one chronicle. Each declares an
identity (`GODMODE_AGENT_ID`, else derived), takes exclusive leases on the
paths it is working, and records who dispatched whom. A lease held by
another agent and a delegation that would make an agent its own ancestor
are both refused at write time, with a failing exit code. Leases carry a
term and lapse by the clock, so a stopped agent does not hold a path.

```console
$ godmode fleet show
```

### Citation drift

A claim graded against a file keeps that grade after the file changes.
`reanchor` names citations that came loose: cited files committed over
since the record was written, and `commit:` citations whose object the
repository no longer has. It reports and does not regrade — a stale
citation and an unsupported claim are different facts.

```console
$ godmode reanchor
```

### Restore points

A green is attested rather than inferred from prose: the command, its exit
code, and the commit it ran against. A failing run cannot mark a commit
green. The plan names the last green, what changed since, and what is
uncommitted, then hands over a non-destructive command; it runs nothing.

```console
$ godmode rollback plan
```

### Forecast and replay

`forecast` classifies an operation before it runs and reports how many
distinct operations in the same category this project already refused.
`replay` re-classifies recorded operations under today's rules and
separates tightenings from relaxations, since direction is what the
ratchet is about.

```console
$ godmode forecast --operation "git push --force origin main"
$ godmode replay
```

### Host approvals

Every host ships approval controls of its own. Where a host tells the hook
what it decided, that is recorded next to what godmode decided, and the
rows where the two differ are reported in both directions. Neither
boundary is read to satisfy the other; the operation is stored as a
digest, not as text.

```console
$ godmode approvals
```

### Project governance

Rules proposed from this project's own record: a refusal category with
enough distinct operations behind it, an obligation restated without being
discharged, an ask recurring across sessions. Each candidate carries the
records supporting it, their count and their window. Nothing is installed:
reading the surface performs no write, and `governance promote` — which
takes a person, a candidate id and a reason — is what records an adoption.

```console
$ godmode governance show
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

### Quality, freshness, and the watchdog

Three detectors already produced quality findings in three shapes;
`quality` folds them into one severity-ranked list, worst first, and
executes none of the remedies it proposes. `--format editor` prints one
`path:line: severity: message` per line for an editor's problem matcher;
`--format sarif` prints a SARIF 2.1.0 document.

```console
$ godmode quality --format editor
```

`freshness` asks whether the sources standing records cite are still what
was graded: a cited file committed over since is stale, a cited commit no
longer reachable is gone, and a `url:` citation is reported unverifiable,
never fresh, because nothing here touches the network. `partial` names
what was not checked and is not a failure.

```console
$ godmode freshness
```

`watchdog` reads the newest window of the record on demand — no daemon —
and names a repeated operation, a burst of refusals, or a run of actions
with no attestation behind them. `--interrupt` writes the operator-stop
flag the stop algebra already honours.

```console
$ godmode watchdog --interrupt
```

`arbitrate` scores competing plan files on what a plan can be held to and
returns `undecided` on a tie rather than breaking it. `examples --check`
reproduces every worked example against the real console. `extensions`
lists what sits under the private state home and runs one only when the
project's policy names it. `claim --scan` lists every claim-shaped sentence
on a public surface whose line names no reproduction.

```console
$ godmode arbitrate --plan a.md --plan b.md
$ godmode examples --check
$ godmode extensions list
$ godmode claim --scan
```

Per-edit feedback is opt-in. With `"post_edit_quality": true` in
`.godmode-authorization-policy.json`, every Write or Edit runs the same
detectors over the one file just written and returns the findings as an
advisory; without it the hook exits at once with nothing to say. The
structure index (`context structure`) now carries who calls what across
files, names only, and its outline shows each file's dependencies as
`-> other.py`.

`experiment holdout` takes observations from two arms and one metric and
computes the verdict from medians: `treatment`, `control`,
`indistinguishable` within epsilon, or `underpowered` below two
observations per arm. The last two exit non-zero, because "cannot tell"
must never read as "yes".

```console
$ godmode experiment holdout --name terse-brief --metric tokens --epsilon 5 \
    --control 100 --control 110 --treatment 70 --treatment 72 --lower-is-better
```

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
| New fast-path allow (`git status`) | 90.3ms median | 10 timed runs after warm-up, sorted-sample median ([release notes](docs/releases/RELEASE_NOTES_v0.2.11.md)) |
| New escalating call (`git push --force`, refused) | 468.6ms median | same method ([release notes](docs/releases/RELEASE_NOTES_v0.2.11.md)) |

Full two-minute walk-through, every command pinned against the real CLI
parser: [docs/DEMO.md](docs/DEMO.md).

Next: what holds here depends on the host running it.

## Host support

Enforcement tier is computed from what the running environment proves,
never from the host's name. `godmode capabilities` reports one of five
levels for `tool_call_interception`: `HARD` only from a live, chronicled
proof (`godmode hooks probe` sends a marker operation through the real
pre-tool hook, the hook denies it and records the denial, and `godmode
hooks status` reads that record back); `DEGRADED` when a proof that WAS
fresh is now superseded, expired, or drifted; `PARTIAL` when the hook is
structurally registered but not freshly proven; `SOFT` when only the
skills+CLI layer is installed with no hook proven at all; `UNAVAILABLE`
when no compatible boundary exists.

| Host | What's shipped | What's tested |
|---|---|---|
| **Claude Code** | Plugin, hooks (`SessionStart`, `PreToolUse`, `UserPromptSubmit`) | Live: with the plugin enabled, real tool calls made in a session are intercepted and recorded — a protected command writes a `refusal` record and the submitted prompt writes a `request` record, both observable in the archive. This is direct evidence of host wiring, unlike `hooks probe`, which self-injects. |
| **Codex** | Same plugin package (`.codex-plugin/plugin.json`), same hooks convention | **One wiring step needed (Codex CLI host bug).** Codex 0.150.1 ignores plugin-bundled hook manifests entirely - its own bundled plugins' hooks also show `Installed: 0` in `/hooks` - which conflicts with its documented plugin-hook behaviour. Codex does load project-level config, so `godmode hooks wire` writes a `.codex/hooks.json` fallback projecting the shared hooks into absolute commands (`py -3` on Windows); the operator reviews and Trusts each command inside `codex`, then `/hooks` reports the events Installed and Active (verified live 2026-08-28: PreToolUse and SessionStart, 1/1, Trusted - hooks execute outside Codex's sandbox, which is why the trust step is Codex's own and cannot be automated). Skills and the CLI work with no fallback. |
| **Grok** | Same plugin package (`.grok-plugin/plugin.json`), same hooks convention | **Live-proven (2026-08-28 field report, on Windows).** Real tool calls in a live Grok session run the gate: a protected command and an unmapped tool were denied and the host honored the deny (the tools did not run), and `godmode hooks status` reads HARD from a fresh probe whose proof record carries the host's acknowledgement. A second live session (2026-08-29) caught one claim here running ahead of the runtime: the read-only-builtin allowance was pinned under `GROK_AGENT`, a variable Grok's hook subprocess does not set - detection now also keys on `GROK_PLUGIN_ROOT`/`GROK_HOOK_EVENT`, the variables it does inject, pinned exactly so. A third live session (2026-08-29, Grok 1.0.5) then chronicled the pass: the previously denied builtin ran, `grep` and `read_file` pass, and `hooks status` reads HARD with Stop and PostToolUse in the declared events - the claim stands on that chronicle, not on the lab pin that first carried it. Grok expands `${CLAUDE_PLUGIN_ROOT}` through its documented alias and parses the shared shell-form `hooks/hooks.json`. Grok has no `ask` decision, so a would-ask folds to deny with the staged-capability remedy. |
| **OpenCode** | Instruction-file adapter plus an optional Bun plugin shim ([`adapters/`](./adapters/README.md)) | Attestation, claim-downgrade, and plan-gate controls run through the host-independent CLI and hold. With `adapters/opencode/godmode.opencode.js` installed as an OpenCode plugin, every `bash`/`write`/`edit`/`patch` call runs through the real gate and a deny throws before the tool runs (fail-closed); `tool_call_interception` is declared `SOFT` until a live OpenCode block is chronicled as a proof. |
| **Cursor, Gemini CLI** | Instruction-file adapters ([`adapters/`](./adapters/README.md)) plus shipped pre-tool hook manifests (`.cursor-plugin/hooks.json`, `.gemini-plugin/hooks-fragment.json`) | Attestation, claim-downgrade, and plan-gate controls run through the host-independent CLI and hold. `tool_call_interception` reads `PARTIAL` (manifest present, not freshly proven) only when the session explicitly declares itself (`GODMODE_HOST=cursor`/`gemini`); by default neither host sets that, so an ordinary session still reads `UNAVAILABLE`. Neither manifest's wiring is live-probed — neither host is installed on the machine this was developed on — so PARTIAL stays a structural claim about what's shipped, not a proof the host calls it. Both adapters are built from those hosts' own published hook references (tool types and payload field names), and a checked-in test asserts every tool name each shipped manifest subscribes to resolves in the adapter that host uses. |
| **CI (GitHub Action)** | `action.yml`, integrity and changelog gates | Runs the same CLI the rows above do; no hook boundary involved. |

Developed and tested on Windows. The Windows kill path for an overrun run
is exercised for real in the test suite; the POSIX kill path (`os.killpg`)
is pinned by a mocked unit test, not live-probed on a POSIX host.

## Learn more

| Document | Covers |
|---|---|
| [docs/DEMO.md](docs/DEMO.md) | Two-minute terminal walk-through, every command pinned against the real CLI |
| [docs/LADDER.md](docs/LADDER.md) | Four tiers of onboarding, one session each; `godmode guide --tier N` prints one |
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
