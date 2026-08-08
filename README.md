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
  <img alt="Tests: passing" src="https://img.shields.io/badge/tests-passing-brightgreen">
  <img alt="Hosts: Claude Code, Codex, Grok, +3 adapters" src="https://img.shields.io/badge/hosts-6-blue">
</p>

---

## In one minute

Your coding agent says *"Fixed it — all tests pass."* Godmode is what checks
whether that sentence is true, before you believe it.

**Without Godmode**

```text
agent: I fixed the auth bug and the suite is green. Done.
you:   (is it? which test covered it? did the old fix survive? did anything leak?)
```

**With Godmode**

```console
$ godmode claim "the auth bug is fixed" --grade verified
{ "grade": "hypothesis", "reason": "no citation" }        # not warned — downgraded

$ godmode integrity
{ "verdict": "blocked",
  "findings": [ "1 assertion removed and not replaced: assert token.expired()" ] }

$ godmode session close
{ "closed": false, "unattested_hard_rules": ["a guard must be seen failing"] }
```

Nothing here asks the agent to be careful. Each answer is computed from a
tamper-evident record of what actually happened, and returned as an exit code
the agent cannot argue with.

## The problem

Coding agents write code well and lose everything around it. Across a context
window, a session, or a model switch, the same failures repeat:

- a capability gets built twice because the first one was named differently;
- a test goes green because an assertion was quietly deleted;
- a fix from last week is reverted by a refactor that never re-ran its guard;
- "done" is claimed on evidence nobody checked, and the backlog grows phantoms;
- a secret reaches a commit because the scan ran after the write, not before.

Prose in a prompt does not stop any of these. An agent that is asked to be
careful is careful exactly until it is under pressure, which is the moment it
matters.

## What Godmode does

Godmode is a **deterministic local runtime** that holds the parts that must not
depend on a model remembering them. It keeps an append-only, hash-chained record
of what actually happened, computes decisions from that record, and returns exit
codes. The agent supplies judgment; Godmode supplies the parts judgment is bad at
under pressure.

Concretely, it does four things:

1. **Remembers** — reconstructs what is true about the project right now (branch,
   worktree, unfinished merges, open obligations, protected fixes, what the last
   session said to do next) from records, not from chat history.
2. **Checks** — runs the gates a change must pass: tests not weakened, guards
   seen failing, claims backed by citations that resolve, secrets caught before
   the commit, no repeat of a loop you are already in.
3. **Gates** — refuses. A protected action needs a scoped, single-use local
   capability; on hosts with a pre-tool boundary the refusal lands before the
   tool runs. Godmode never performs the operation itself.
4. **Reports** — a completion report whose status is derived from the record,
   with every field labelled by how well it is known.

It ships as a plugin for **Claude Code**, **Codex**, and **Grok**, as instruction
adapters for **OpenCode**, **Cursor**, and **Gemini CLI**, and as a **GitHub
Action** so the same gates run in CI.

## How it is different

**Enforcement lives outside model output.** A gate is a non-zero exit code
computed from records, not an instruction the model can reason around. When a
host exposes a pre-tool boundary, Godmode answers there and the tool does not
run.

**It refuses to overstate itself.** `godmode capabilities` prints what this host
can actually hold — HARD, SOFT, or UNAVAILABLE, per control. An uncited claim is
not warned about, it is **stored as a hypothesis**. A guard that has never been
observed failing is reported as a suggestion, not a guard. An absence claim
without the search that would disprove it is refused.

**Its own record is the evidence.** Every record is hash-chained and carries the
host, model, and effort that wrote it, so a step that quietly stopped happening
after a model switch is reported at the next session open.

## Install

<details open>
<summary><b>Claude Code</b></summary>

```text
/plugin marketplace add AIimagined/Godmode
/plugin install godmode@aiimagined
/reload-plugins
```

Invoke with `/godmode:godmode`. The bundled hooks load a bounded continuity brief
at session start and decide mutating tool calls at the pre-tool boundary.
</details>

<details>
<summary><b>Codex</b></summary>

```text
codex plugin marketplace add AIimagined/Godmode
codex plugin add godmode@aiimagined
```
</details>

<details>
<summary><b>OpenCode · Cursor · Gemini CLI</b></summary>

No plugin system is required — each adapter is one instruction file that drives
the same CLI over shell, JSON, and exit codes. See
[`adapters/`](./adapters/README.md); enforcement per host is declared in
`packaging/hosts.json` and a test fails if a document overstates it.
</details>

<details>
<summary><b>CI (any repository)</b></summary>

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: AIimagined/Godmode@v0.2.8
  with:
    base: origin/${{ github.base_ref }}...
    gates: integrity,changelog,grid,config,locale
```
</details>

## Quick start

**Mostly you type nothing.** Once installed, three hooks carry the product:

| Hook | What it does |
| --- | --- |
| Session start | Loads a bounded continuity brief — branch, obligations, open checks, decisions — reconstructed from records rather than remembered. |
| Pre-tool | Decides mutating tool calls. A protected operation is refused with its category and tier before it runs. |
| User prompt | Records what was asked, so a request made while the agent was already working cannot quietly vanish. |

Five skills route by the shape of the work — continuity, governance,
investigation, skill forging — so the agent reaches for the right one without
being told which.

The first thing you will notice is a refusal. Three ways to answer one:

```powershell
godmode authorize setup                        # once, sets a password
godmode authorize stage --operation "<exact command>"   # spent once, expires
```

…or run the command yourself, or narrow it. Godmode never executes the
operation on your behalf.

When you do drive it directly, it is usually one of these:

```powershell
godmode init                  # one-time, zero config
godmode resume                # what is true here right now
godmode checkpoint --review   # obligations, and asks nothing answered
godmode verify --check "..."  # run a check, and record that it ran
godmode integrity             # what a change did to the tests
```

The command surface is large and you are not meant to learn it; the skills
surface what a task needs. `godmode --help` lists everything.

Three flags apply everywhere: `--brief` for one line, `--json` for machines, and
`GODMODE_MODE=guided|standard|expert` to change how much is explained — exposure
changes, enforcement never does.

## What it enforces

| Area | What actually happens |
| --- | --- |
| **Continuity** | Branch, worktree, obligations, decisions, invariants and open checks reconstructed from records; an in-progress merge or rebase is named rather than hidden behind "dirty". |
| **Claims** | A claim citing nothing, or citing a record that does not resolve, is stored as a hypothesis. Citations are checked for position, not just existence. |
| **Tests** | Nine integrity monitors block a change that removes an assertion, adds a skip, or edits a protected test without a recorded rationale. |
| **Guards** | A guard counts only after it is observed failing against a planted violation — green, red, green. |
| **Plans** | A plan needs a spec, a complete contract, and approval before mutation; work outside declared scope is reported as drift; an approved plan survives a model handoff. |
| **Protected actions** | Preview, blast-radius classification (unknown fails closed as production), and a scoped, expiring, single-use local capability. Godmode never executes the operation. |
| **Loops** | Repeated actions, reapplied patches, A→B→A oscillation, and a spent hypothesis are detected from the records and block the next repetition. |
| **Secrets** | Scanned before a record is written and before a commit; a leak that slips through can be expunged and the chain re-sealed with an auditable tombstone. |
| **Release** | Changelog fragments, version reconciliation across every surface, SPDX/CycloneDX SBOM, reproducible checksums, and a differential network capture that proves zero connections. |

## Proving it, rather than claiming it

```powershell
python scripts/godmode.py --project . selftest    # each control refuses something, with evidence
python scripts/godmode.py --project . scenarios   # 21 staged golden failures; what caught each
python scripts/godmode.py --project . grid        # 13 adversarial attacks on the controls
python scripts/godmode.py --project . fuzz        # seeded garbage; every classifier must fail closed
python scripts/godmode.py --project . netgate     # run the CLI under a socket audit
python scripts/godmode.py --project . metrics     # does the product work, not just its tests
```

`metrics` is the uncomfortable one on purpose: it reports `insufficient-data`
rather than a flattering zero, and its first run against this repository
reported that **0 of 5 HARD rules had been attested** — the product catching its
own author.

## Privacy by construction

No telemetry, analytics, update ping, cloud sync, background daemon, network
listener, inference proxy, or idle model use. No raw prompts, conversations,
tool transcripts, source bodies, credentials, or environment dumps are stored.
Remote addresses appear only as one-way hashes. State lives below Git metadata
or the OS application-data directory — never in your working tree.

This is gated, not promised: `sbom --gate` fails the build on a runtime
dependency, and the CI network-capture job proves the detector can see a planted
connection before an empty result counts as evidence.

## Uninstall

```text
/plugin uninstall godmode@aiimagined
```

Delete `.git/godmode-state/` (Git projects) or `%LOCALAPPDATA%\Godmode` /
`~/.local/state/godmode` (everything else) to remove every record. Nothing is
written anywhere else.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Godmode is not initialized for this project` | `python scripts/godmode.py --project . init`, once per project. |
| A gate blocks and you disagree | The payload names the missing step. Gates encode failures that actually recurred; satisfy it rather than bypassing it. |
| History seems lost after `git init` | `godmode adopt` relinks records stranded by the identity change. |
| Output is too terse or too noisy | `--brief`, `--json`, or `GODMODE_MODE=guided`. |
| Hook seems silent | By design before `init`; it activates only for initialized projects. |

## FAQ

**Does anything leave my machine?** No — and `netgate` captures the CLI under a
socket audit to show it rather than assert it.

**Does it work without Git?** Yes. Non-Git projects get a salted local identity
under the OS application-data directory.

**Can the model talk its way past a gate?** No. Decisions are computed by the
runtime from records and exit codes; repository text is classified as untrusted
data.

**What happens on a model or host switch?** Every record names its author, and
`drift` reports mandated steps that silently stopped happening.

**Is it slow?** Read-only work is untouched. The pre-tool gate costs about 0.7s
on a mutating call (resolving repository identity) and is skipped entirely for
read-only tools.

## Documentation

| Document | Covers |
| --- | --- |
| [GODMODE.md](./GODMODE.md) | Product guarantees, gates, and the start sequence |
| [GODMODE_PRIVACY.md](./GODMODE_PRIVACY.md) | What is stored, where, and what never leaves |
| [GODMODE_SECURITY.md](./GODMODE_SECURITY.md) | Protected actions and the capability model |
| [THREAT-MODEL.md](./THREAT-MODEL.md) | Threats, controls, and stated non-goals |
| [GODMODE_ACCEPTANCE.md](./GODMODE_ACCEPTANCE.md) | Every gate and the command that proves it |
| [GOVERNANCE.md](./GOVERNANCE.md) | Changing a protected guarantee |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Local validation and the zero-dependency budget |
| [CHANGELOG.md](./CHANGELOG.md) | Released changes |
| [adapters/](./adapters/README.md) | Per-host enforcement and wiring |
| [llms.txt](./llms.txt) | Machine-readable front door |

## Development

```powershell
python -m unittest discover -s tests      # 359 tests
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . scenarios --brief
```

The runtime is 40 standard-library modules under `scripts/godmode_runtime/`.
Contributions must keep the dependency budget at zero — see
[CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Licensed under the [Apache License 2.0](./LICENSE). Attribution and project
identity notices are preserved in [NOTICE](./NOTICE).

Developed by AIimagined.
