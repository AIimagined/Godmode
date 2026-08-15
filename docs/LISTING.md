# Marketplace listing kit

Copy-ready listing text per marketplace, sourced from the shipped manifests
and this repository's own doctrine (no comparisons, no unverified claims,
numbers cite the command that reproduces them). A manifest audit closes
the document: what each manifest already carries and what a follow-up task
needs to add.

## Claude Code (plugin marketplace)

**Short description** (one line, from `.claude-plugin/plugin.json`):

> Local-first context continuity and evidence governance for coding agents.

**Long description**:

> Godmode is a deterministic, stdlib-only runtime that keeps the parts of a
> coding session a model should not have to remember: what actually
> happened, whether a claimed fix ever saw the failure it claims to fix,
> and whether a protected action ran only under a scoped, single-use local
> capability. It holds an append-only, hash-chained record of tool calls,
> claims, and verdicts, and computes gate decisions from that record rather
> than from prompted carefulness. On Claude Code the gate answers at the
> pre-tool boundary itself, before a protected command runs. Nothing
> leaves the machine: no telemetry, no network calls, no runtime
> dependencies.

**Keywords**: `context-continuity`, `evidence-governance`, `local-first`,
`developer-tools`, `governance gate for coding agents` (new: the bare
`governance` and `evidence-governance` terms are crowded, and this phrase
is the disambiguating addition, not yet in the shipped manifest).

**Category**: Productivity / Developer Tools.

**Logo / assets**: `assets/godmode-logo.png` (icon), `assets/godmode-social-preview.jpg`
(social card). Neither is referenced from `.claude-plugin/plugin.json` today;
see the manifest audit below.

**Submission steps**:

1. Confirm `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
   are valid JSON and agree with `packaging/hosts.json` (`godmode bindings
   --write` regenerates both from the one source; a plain run with no diff
   is the check).
2. Push to the public `AIimagined/Godmode` GitHub repository. No
   application or review queue sits in front of this step: Claude Code's
   marketplace is a client pointed at a repository, not a curated store.
3. A user installs directly:
   ```text
   /plugin marketplace add AIimagined/Godmode
   /plugin install godmode@aiimagined
   ```
4. If a curated, first-party Anthropic plugin directory exists alongside
   this self-hosted model, listing there is a separate application this
   repository has no local record of. Confirm the current process on the
   operator's own Anthropic account before claiming a listing exists.

## Codex (OpenAI plugin ecosystem)

**Short description** (one line, from `.codex-plugin/plugin.json`):

> Local-first context continuity and evidence-governance skills for coding agents.

**Long description** (from the manifest's own `interface.longDescription`,
already doctrine-compliant, reused verbatim rather than rewritten):

> Godmode reconstructs repository reality from local evidence, preserves
> private continuity, diagnoses failures without looping, previews
> protected actions, and can forge validated project skills when a
> reusable gap is proven.

**Keywords**: `codex-plugin`, `skill-authoring`, `context-continuity`,
`evidence-governance`, `local-first`, `developer-tools`,
`governance gate for coding agents` (new, same rationale as the Claude row).

**Category**: Productivity (`interface.category` in the manifest).

**Logo / assets**: `interface.logo` already points at
`./assets/godmode-logo.png`, the one manifest of the three that carries a
logo pointer today.

**Submission steps**:

1. Confirm `.codex-plugin/plugin.json` matches `packaging/hosts.json`
   (`godmode bindings --write`).
2. **Gap**: no `.codex-plugin/marketplace.json` exists in this repository;
   Claude and Grok both carry one. Whether Codex's plugin distribution
   needs one, and what its schema is, is not established here. Confirm
   against Codex's own current plugin documentation before drafting one.
3. Whatever submission flow Codex's plugin ecosystem uses, whether a
   self-hosted pointer or an application to a curated directory, needs the
   operator's own Codex/OpenAI developer account to execute; this
   repository holds no credential or prior submission record for it.

## Grok

**Short description** (one line, from `.grok-plugin/plugin.json`):

> Local-first context continuity and evidence governance for coding agents.

**Long description**:

> Godmode is a deterministic, stdlib-only runtime for Grok sessions that
> keeps continuity, claim evidence, and protected-action approval outside
> chat history, in an append-only local record the runtime computes gate
> decisions from. Skills route by task shape; enforcement stays outside
> model output, in exit codes a session cannot reason its way past. Nothing
> leaves the machine: no telemetry, no network calls, no runtime
> dependencies.

**Keywords**: `context-continuity`, `evidence-governance`, `local-first`,
`developer-tools`, `governance gate for coding agents` (new, same rationale
as the other two rows).

**Category**: `productivity` (top-level `category` field in the manifest).

**Logo / assets**: `assets/godmode-logo.png` is not referenced from
`.grok-plugin/plugin.json` today; see the manifest audit below.

**Submission steps**:

1. Confirm `.grok-plugin/plugin.json` and `.grok-plugin/marketplace.json`
   match `packaging/hosts.json`.
2. `.grok-plugin/marketplace.json` already declares a git-URL source
   (`https://github.com/AIimagined/Godmode.git`), the same self-hosted
   shape Claude's marketplace uses. Pushing to the public repository is
   the only step this repository can confirm.
3. **Gap**: no command syntax for adding a Grok plugin marketplace or
   installing a plugin is recorded anywhere in this repository (checked:
   `GODMODE.md`, `OPERATOR.md`, `adapters/README.md`, `CONTRIBUTING.md`).
   Confirm the actual client command against Grok's own current docs, on
   the operator's own account, before publishing an install snippet that
   claims to work.

## Manifest audit

Checklist against the five fields this task asked for: `name`,
`description`, `version` (expected `0.2.12`), an icon/logo path, and
`keywords`. Read-only: these gaps are a follow-up task, not fixed here.

| Manifest | `name` | `description` | `version` | icon/logo path | `keywords` |
|---|---|---|---|---|---|
| `.claude-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | **missing**, no `icon` or `logo` field despite `assets/godmode-logo.png` shipping | present (5 entries) |
| `.codex-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | present, but nested under `interface.logo`, not a top-level field | present (6 entries) |
| `.grok-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | **missing**, no `icon` or `logo` field | present (4 entries) |

Two follow-ups this audit surfaces, neither actioned here because this
task's manifests are read-only:

1. Claude's and Grok's manifests carry no pointer to `assets/godmode-logo.png`
   at all; Codex's pointer is nested under `interface.logo` rather than a
   field a generic manifest reader would look for at the top level. Whether
   `packaging/hosts.json` (the one source `godmode bindings --write`
   regenerates every manifest from) should gain a shared top-level `icon`
   field is a design decision for that follow-up, not this one.
2. None of the three manifests yet carries the
   `governance gate for coding agents` keyword this document recommends
   above. Adding it is a `packaging/hosts.json` edit plus a
   `godmode bindings --write` regeneration, the same path every other
   manifest field change already takes.
