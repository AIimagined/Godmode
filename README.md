<p align="center">
  <img src="./assets/godmode-logo.png" alt="Godmode logo" width="320">
</p>

<h1 align="center">Godmode</h1>

<p align="center">
  Local-first continuity, evidence-led investigation, protected-action previews,
  and on-demand skill forging for Codex, Claude Code, and Grok.
</p>

<p align="center">
  <a href="https://github.com/AIimagined/Godmode/actions/workflows/godmode-verify.yml"><img src="https://github.com/AIimagined/Godmode/actions/workflows/godmode-verify.yml/badge.svg" alt="verification status"></a>
  <img src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen" alt="zero runtime dependencies">
  <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache 2.0">
</p>

Godmode helps a coding agent recover what is true about a project before it acts. It
builds bounded context from inspectable local evidence, records operational continuity
outside tracked project files, detects repeated failed approaches, and makes risky
operations explicit. It does not run protected operations itself.

Godmode is an early preview. Its safety controls are advisory unless the host invokes
the bundled gate adapter before tool execution.

## Why

Coding agents produce code but lose causal history: what was decided, what was
removed and why, which fixes must never be reversed, and what a passing test
actually proved. Godmode keeps that record outside the model's memory — in
hash-chained local files a next session (or a different model) reconstructs
deterministically — and turns the recurring failure modes of agent-driven work
(test weakening, fix oscillation, phantom backlog items, secret leaks, silent
scope drift) into gates that exit non-zero instead of lessons that get re-read.

## What it provides

- **Continuity:** reconstructs branch, revision, worktree, obligations, decisions,
  checks, incidents, and recent changes from local evidence.
- **Investigation:** separates observations, hypotheses, contradictions, and unproven
  claims while stopping repeated failed approaches.
- **Action governance:** classifies operations, previews impact and recovery, and issues
  scoped, expiring, single-use local capabilities for protected actions.
- **Skill forging:** proposes a project-specific skill only after a reusable capability
  gap is evidenced, then scaffolds and validates the result.
- **Honest limits:** reports stale or missing evidence and adapter boundaries instead of
  claiming perfect memory or universal enforcement.

## Privacy by construction

Godmode runs only from an explicit command, an invoked skill, or an enabled host
lifecycle hook. It has no telemetry, analytics, update ping, cloud sync, background
daemon, network listener, inference proxy, or idle model use. It does not store raw
prompts, conversations, tool transcripts, source bodies, credentials, or environment
dumps. Repository remote addresses are represented only by one-way hashes.

See [GODMODE_PRIVACY.md](./GODMODE_PRIVACY.md) and
[GODMODE_SECURITY.md](./GODMODE_SECURITY.md) for the complete boundaries.

## Requirements

- Python 3.11 or newer
- Codex with plugin support or Claude Code with plugin marketplace support
- Git is optional; non-Git projects use a salted local project identity

The runtime uses only the Python standard library.

## Install in Claude Code

Add the repository as a marketplace, install Godmode, then reload plugins:

```text
/plugin marketplace add AIimagined/Godmode
/plugin install godmode@aiimagined
/reload-plugins
```

Invoke the main skill with `/godmode:godmode`. Claude Code also loads a bounded local
continuity brief at `SessionStart` after Godmode has been explicitly initialized for
that project. Before initialization, the hook is silent. It performs no network access
and does not read the Claude transcript.

## Quick start

From the repository root:

```powershell
python scripts/godmode.py --project . init
python scripts/godmode.py --project . inspect
python scripts/godmode.py --project . resume
```

Explore the complete command surface:

```powershell
python scripts/godmode.py --help
```

The repository root is both the Codex and Claude Code plugin root. Codex uses
`.codex-plugin/plugin.json`. Claude Code uses `.claude-plugin/plugin.json` and the
co-located `.claude-plugin/marketplace.json`. Godmode does not alter a user's
marketplace or agent configuration automatically.

## Bundled skills

| Skill | Responsibility |
| --- | --- |
| `godmode` | Routes work to the smallest applicable Godmode workflow |
| `godmode-continuity` | Reconstructs and explains bounded project context |
| `godmode-investigation` | Runs evidence-led diagnosis and loop detection |
| `godmode-governance` | Previews and gates protected operations |
| `godmode-skill-forge` | Creates validated local skills for proven reusable gaps |

## Protected actions

Read-only work stays friction-light. A protected or unknown mutation fails closed until
the user authorizes its exact project, category, action fingerprint, and expiry. The
resulting capability is local, password-backed, scoped, expiring, and single use.
Godmode only evaluates and records the decision; it never performs Git, database,
release, deployment, external-write, or destructive operations.

## Development checks

```powershell
python -m compileall scripts hooks tests
python -m unittest discover -s tests -v
python scripts/godmode.py --version
claude plugin validate . --strict
```

The acceptance requirements and their proof surfaces are documented in
[GODMODE_ACCEPTANCE.md](./GODMODE_ACCEPTANCE.md).

## Uninstall

```text
/plugin uninstall godmode@aiimagined
/plugin marketplace remove AIimagined/Godmode
```

Local state lives below Git metadata (`.git/godmode-state/`) or the OS
application-data directory (`%LOCALAPPDATA%\Godmode` on Windows,
`~/.local/state/godmode` elsewhere). Delete those directories to remove every
record; nothing else is written anywhere.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `Godmode is not initialized for this project` | Run `python scripts/godmode.py --project . init` once per project. |
| `adopt` reports no stranded archive after `git init` | The archive may never have existed here; `init` fresh. `doctor` shows health. |
| Commands print nothing useful | Add `--brief` for one line or `--json` for compact output; `GODMODE_MODE=guided` explains every refusal. |
| A gate blocks and you disagree | Every blocking payload names the missing step; gates encode recurring failures and are satisfied, not bypassed. |
| Hook seems silent at session start | By design before `init`; it activates only for initialized projects. |

## FAQ

**Does anything leave my machine?** No. No telemetry, no network calls, no cloud
memory. `godmode sbom --gate` and the CI network-capture job prove it rather than
promise it.

**Does it work without Git?** Yes — non-Git projects get a salted local identity
under the OS application-data directory.

**Can the model talk its way past a gate?** No. Protected decisions are computed
by the runtime from records and exit codes; repository text and model output are
classified as untrusted data (`godmode untrusted`).

**What happens on a model or host switch?** Every record carries its author's
fingerprint; `godmode drift` reports steps that silently disappeared, and an
approved plan survives the handoff.

## Documentation index

| Document | Covers |
| --- | --- |
| [GODMODE.md](./GODMODE.md) | Product guarantees and start sequence |
| [GODMODE_PRIVACY.md](./GODMODE_PRIVACY.md) | What is stored, where, and what never leaves |
| [GODMODE_SECURITY.md](./GODMODE_SECURITY.md) | Protected actions and the capability model |
| [GODMODE_ACCEPTANCE.md](./GODMODE_ACCEPTANCE.md) | Acceptance criteria the suite enforces |
| [THREAT-MODEL.md](./THREAT-MODEL.md) | Threats, controls, and stated non-goals |
| [GOVERNANCE.md](./GOVERNANCE.md) | Changing a protected guarantee |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Local validation and the zero-dependency budget |
| [CHANGELOG.md](./CHANGELOG.md) | Released changes; unreleased ones live in `changelog.d/` |
| [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) | Community standards |
| [RELEASE_NOTES_v0.1.0-draft.md](./RELEASE_NOTES_v0.1.0-draft.md) | Draft notes and the owner release checklist |
| [llms.txt](./llms.txt) | Machine-readable front door |
| `locales/` | Validated guidance translations (`locale check`) |
| `scripts/godmode_docs_site.py` | Renders these documents into an offline HTML site |

## Contributing and security

Read [CONTRIBUTING.md](./CONTRIBUTING.md) before proposing a change. Please follow
[.github/SECURITY.md](./.github/SECURITY.md) for vulnerability reports and never place
secrets or private repository content in a public issue.

## License

Licensed under the [Apache License 2.0](./LICENSE). Attribution and project identity
notices are preserved in [NOTICE](./NOTICE).

Developed by AIimagined.
