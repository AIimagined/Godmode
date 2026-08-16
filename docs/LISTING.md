# Marketplace listing kit

Copy-ready listing text per marketplace, sourced from the shipped manifests
and this repository's own doctrine (no comparisons, no unverified claims,
numbers cite the command that reproduces them). A manifest audit closes
the document: what each manifest carries, the one gap this document could
verify and close (a missing keyword, added via `packaging/hosts.json` and
`godmode bindings --write`), and what stays a stated gap because no
in-repo or published schema could verify it.

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

**Keywords**: `claude-code-plugin`, `context-continuity`,
`evidence-governance`, `local-first`, `developer-tools`,
`governance gate for coding agents` (the bare
`governance` and `evidence-governance` terms are crowded, and this phrase
is the disambiguating addition; added to the shipped manifest in this fix
round via `packaging/hosts.json`'s shared `identity.keywords` plus
`godmode bindings --write`, so all three manifests carry it identically).

**Category**: Productivity / Developer Tools.

**Logo / assets**: `assets/godmode-logo.png` (icon), `assets/godmode-social-preview.jpg`
(social card). Neither is referenced from `.claude-plugin/plugin.json`;
confirmed against the manifest's own `$schema`
(`https://json.schemastore.org/claude-code-plugin-manifest.json`) that no
icon/logo property exists at any level of this format, so nothing was
added here. See the manifest audit below.

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

**Short description** (one line, from `.codex-plugin/plugin.json`'s
top-level `description` field, distinct from the nested
`interface.shortDescription` the same manifest also carries; see the note
below):

> Local-first context continuity and evidence-governance skills for coding agents.

Note: `.codex-plugin/plugin.json` carries a second, shorter description
under `interface.shortDescription` ("Local continuity and guarded coding
workflows."). Which field Codex's own marketplace UI actually renders as
the listing's short description is not established here; the quote above
is the top-level `description` verbatim, picked because it is the field
every other host's manifest also carries under that exact name. Confirm
against Codex's current listing UI before treating this as final copy.

**Long description** (from the manifest's own `interface.longDescription`,
already doctrine-compliant, reused verbatim rather than rewritten):

> Godmode reconstructs repository reality from local evidence, preserves
> private continuity, diagnoses failures without looping, previews
> protected actions, and can forge validated project skills when a
> reusable gap is proven.

**Keywords**: `codex-plugin`, `skill-authoring`, `context-continuity`,
`evidence-governance`, `local-first`, `developer-tools`,
`governance gate for coding agents` (added in this fix round, same
mechanism as the Claude row).

**Category**: Productivity (`interface.category` in the manifest).

**Logo / assets**: `interface.logo` already points at
`./assets/godmode-logo.png`, the one manifest of the three that carries a
logo pointer today. Codex's own manifest schema is not published or
otherwise verifiable in this repository, so whether it supports a
top-level `icon` field as well can't be confirmed; the existing nested
pointer is left as-is rather than moved without evidence.

**Submission steps**:

1. Confirm `.codex-plugin/plugin.json` matches `packaging/hosts.json`
   (`godmode bindings --write`).
2. **Gap**: no `.codex-plugin/marketplace.json` exists in this repository;
   Claude and Grok both carry one. Whether Codex's plugin distribution
   needs one, and what its schema is, is not established here. Confirm
   against Codex's own current plugin documentation before drafting one.
3. **Resolved**: Codex's own developer portal is the submission path, and
   it accepts a skills-only plugin (no hook/gate surface is required for
   acceptance; a plugin that ships hooks, as this one does, is not
   penalized for also shipping them). The portal form asks for per-tool
   annotations, a short description of what each exposed tool does, plus
   "five positive and three negative test cases with expected outcomes."
   The test-case-mapping table below is that requirement, filled with real,
   runnable tests rather than hand-written examples. Submitting still needs
   the operator's own Codex/OpenAI developer account; this repository holds
   no credential or prior submission record for it.

### Codex submission kit: test-case mapping

The OpenAI portal's own listing requirements (developer docs, verified
fetch, recorded in
`docs/superpowers/specs/2026-08-16-codex-compat-design.md`'s Addendum 2)
ask for "five positive + three negative test cases with expected outcomes,"
and name directly that "the test-case requirement maps onto CX-6 scenarios
(reuse them)." This section is that mapping — every row names a real,
runnable test in `tests/e2e/test_host_e2e.py`, not a hand-written example;
`python -m unittest tests.e2e.test_host_e2e.<ClassName> -v` reproduces each
one.

**Five positive cases** (expected outcome: the operation proceeds):

| # | Case | Test | Expected outcome |
|---|---|---|---|
| 1 | A read-only command (`git status`) | `ReadOnlyFastPathTests` | Allowed, fast path, exit 0, no envelope |
| 2 | An ordinary in-tree file edit | `NormalEditAllowedTests` | Allowed; the file's own content changes |
| 3 | An edit inside a plan's declared fence | `OutOfScopeEditDeniedTests.test_an_edit_inside_the_declared_fence_still_proceeds` | Allowed; the in-scope file changes |
| 4 | A staged, password-authorised capability's first use | `StagedCapabilityScenarioTests.test_a_staged_capability_is_consumed_exactly_once` (first call) | Allowed exactly once |
| 5 | An in-scope edit sent in every documented host dialect | `PerHostDialectReplayTests.test_every_documented_host_dialect_allows_an_in_scope_edit` | Allowed on Claude/Grok/Cursor/Gemini's own wire shapes |

**Three negative cases** (expected outcome: the operation is refused):

| # | Case | Test | Expected outcome |
|---|---|---|---|
| 1 | A force-push, every documented host dialect | `ForcePushFourPlaneAllHostsTests` | Denied; the remote ref never moves (independent git-level backstop also refuses it) |
| 2 | A destructive command (hard reset / recursive delete / `DROP TABLE`) | `ProtectedCommandDenialTests` | Denied or asked; the target state is provably unchanged |
| 3 | A hook with no live proof (or one marked uninstalled) | `DisabledHookScenarioTests` | Never grades `HARD` — the negative control `docs/CAPABILITY-COVERAGE.md`'s interception row and `tests/e2e/test_release_gate.py` both require |

Host names above are factual (which dialect a test replays), not a
comparison between hosts.

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
`developer-tools`, `governance gate for coding agents` (added in this fix
round, same mechanism as the other two rows).

**Category**: `productivity` (top-level `category` field in the manifest).

**Logo / assets**: `assets/godmode-logo.png` is not referenced from
`.grok-plugin/plugin.json`. This manifest carries no `$schema` pointer
(Claude's does), and no published schema for it was found; a field name
can't be verified, so none was invented and none was added. See the
manifest audit below.

**Submission steps**:

1. Confirm `.grok-plugin/plugin.json` and `.grok-plugin/marketplace.json`
   match `packaging/hosts.json`.
2. `.grok-plugin/marketplace.json` already declares a git-URL source
   (`https://github.com/AIimagined/Godmode.git`), the same self-hosted
   shape Claude's marketplace uses. Pushing to the public repository is
   the only step this repository can confirm.
3. **Resolved**: Grok's own install command is
   `grok plugin install godmode --trust`. Listing in Grok's official
   marketplace catalog is a separate step from a self-hosted git-URL
   source: it is a pull request against the official catalog repository's
   `external_plugins/` directory, and the catalog requires that PR to pin
   the plugin source to an exact commit SHA rather than a branch or tag
   reference. This repository holds no submitted or merged PR against that
   catalog; the git-URL source in `.grok-plugin/marketplace.json` above
   remains the self-hosted path, usable today with no submission or
   review step.

## Manifest audit

Checklist against the five fields this task asked for: `name`,
`description`, `version` (expected `0.2.12`), an icon/logo path, and
`keywords`.

| Manifest | `name` | `description` | `version` | icon/logo path | `keywords` |
|---|---|---|---|---|---|
| `.claude-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | **confirmed absent from the format**: the manifest's own `$schema` (`https://json.schemastore.org/claude-code-plugin-manifest.json`) defines no icon/logo property at any level | present (6 entries, includes `governance gate for coding agents`) |
| `.codex-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | present, nested under `interface.logo`; whether a top-level field is also supported is unverified (no published schema found) | present (7 entries, includes `governance gate for coding agents`) |
| `.grok-plugin/plugin.json` | present (`godmode`) | present | present (`0.2.12`) | **unverified**: no `$schema` pointer and no published schema found, so no field name could be confirmed and none was added | present (5 entries, includes `governance gate for coding agents`) |

What this fix round changed and what it deliberately left alone:

1. **Closed**: all three manifests now carry `governance gate for coding
   agents` in `keywords`, added once to `packaging/hosts.json`'s shared
   `identity.keywords` and propagated by `godmode bindings --write`
   (verified: `godmode bindings` reports `"verdict": "current"` for all
   three afterward, meaning the manifests and the source agree).
2. **Confirmed, not a gap**: Claude's plugin manifest format has no
   icon/logo field at any level, checked directly against the schema its
   own `$schema` key names. Adding one to `packaging/hosts.json` would
   invent a key the format doesn't define, so nothing was added.
3. **Still a stated gap**: Codex's manifest already carries a working
   nested `interface.logo` pointer; whether its schema also accepts a
   top-level field is unverified, so it stays where it is. Grok's manifest
   carries no schema reference at all, published or otherwise found, so no
   icon/logo field was added there either. Both are gaps for whoever can
   check against each host's actual current documentation, not decisions
   made here without evidence.
