# Changelog

All notable changes to Godmode will be documented in this file.

The format follows Keep a Changelog principles, and releases use semantic versioning.

## [Unreleased]

### Added

- `authorize setup --password-stdin` and `authorize issue --password-stdin` for
  non-interactive hosts that pipe the password on standard input.

### Fixed

- Removed the duplicate `hooks` manifest reference that made Claude Code fail to
  load the plugin's hooks.
- `authorize setup` and `authorize issue` now fail immediately with guidance when
  no interactive console is available instead of blocking forever on the password
  prompt (including Windows `NUL` redirection, where `isatty()` reports true).

## [0.2.0] - 2026-08-06

### Added

- `GODMODE_MODE=guided|standard|expert` changes exposure, never enforcement:
  guided appends plain-language guidance to every refusal, expert reports one
  line. `charter --bootstrap` mines candidate invariants from the project's own
  commit history for review, and `godmode operator` validates the typed operator
  profile — which has no name field on purpose and refuses profiles containing
  the OS account name.
- `godmode loop` reads the archive's own records and blocks the repetitions the
  repeating agent cannot see: identical normalised actions, reapplied patches
  (citing the prior attempt), A→B→A oscillation with a rollback point, changes to
  guarded files without re-observing the guard, and zero-output "successes";
  `loop --blame` refuses model-blame until a non-model control is attested.
- `atlas diagnose` now reports per-suffix support — a suffix whose files yield no
  symbols is "counted, not understood" and makes the atlas untrustworthy for
  structural claims — and `atlas duplicates` compares approximate symbol bodies
  as well as names, so one behaviour implemented twice under unrelated names is
  reported with `basis: body`.
- The atlas now dispatches extraction through a suffix registry — a third
  language is one `register_extractor` call, not a core edit — records
  `tested-by` and `documents` edges so `affected` can bound traversal by
  relation kind and bucket its answer into callers / tests / docs, and can be
  persisted with `save_index` / `load_index`, which reports fresh, stale, and
  missing files from content hashes with a derived confidence, never from time.
- `godmode benchmark` measures cold-start and resume brief cost against the
  declared token budgets with timings, computed and printed locally only; and
  `claim --external` downgrades a verified claim about an external API or
  library to hypothesis unless it cites a `doc:`/`url:` primary source actually
  read this session.
- `godmode changelog check` fails when a code change arrives without a
  `changelog.d/` fragment, and `godmode changelog merge --set-version X` folds the
  fragments into CHANGELOG.md at release time.
- A composite GitHub Action (`action.yml`) runs Godmode's gates — the
  test-integrity monitors and the changelog fragment gate — on a pull request with
  only a checkout of this repository; the runtime remains standard-library Python.
- `godmode config check` validates every declared `.godmode-*.json` file against
  its typed contract, failing with a `$.field` schema path instead of a stack
  trace; the extension-model split (S26-01/02) is deferred by recorded decision
  until a second consumer exists.
- `detect_context_issues` gains two staleness inputs — a `stale-lock` warning when
  an archive `*.lock` file has survived ten minutes, and `clock-or-restore-anomaly`
  when a file's mtime moved backward since the recorded baseline; new
  `capacity_checkpoint_due` returns the deterministic pre-compaction signal (due at
  80% of the context-brief token budget) for host hooks, and new `why` answers
  `context why --about X` with evidence-linked decisions, fixes, dependencies, and
  invariants actually recorded about a path or topic.
- README grows the missing front-door sections (badges, why, uninstall,
  troubleshooting, FAQ, documentation index); v0.1.0 release notes exist as an
  explicit draft with an owner checklist and no tag; and
  `scripts/godmode_docs_site.py` renders the repository's own Markdown into a
  self-contained offline HTML site with zero generator dependencies.
- The authored skill evals now execute: a deterministic routing runner scores every
  positive and near-negative prompt leave-one-out with stable tie-breaks, snapshot
  fixtures under `evals/fixtures/` turn any routing change into a field-level diff, and
  an adversarial grid attacks each control with real probes - breaches included.
- Forge output is now diffed against a checked-in golden skill tree, so a
  generator regression fails CI naming the drifted file; the learning loop's
  scanner → analyzer → writer → verifier phases each name their implementation
  in a registry.
- Gates deepen: egress `scan_staged`/`scan_paths` find secret-shaped values
  (masked, never repeated) in staged and untracked content before a commit exists;
  `loop` blocks after three non-green checkpoints under one unchanged hypothesis and
  demands a reset; scope `minimality` reports size pressure by name without blocking.
- A generic adapter reference lets any agent drive Godmode with shell, JSON, and
  exit codes alone — enforcement honestly labelled SOFT on unlisted hosts
  (S9-01); the LICENSE appendix names the copyright owner. Live install tests
  passed on both Claude Code (5 skills + hook inventoried) and Codex (installed,
  enabled, five skills discoverable).
- The scenario harness grows from 10 to 15 staged golden failures, each bound to
  its PRD acceptance ID (E-nn / CTX-nn): fix oscillation (E-03), test weakening
  (E-05), wrong environment (E-16), removal forgotten (CTX-03), and undocumented
  change (CTX-07) join the catalogue; `explain-context` now states the token
  cost of loading before anything loads.
- Instruction-file adapters for OpenCode (`AGENTS.md`), Cursor
  (`.cursor/rules/godmode.mdc`), and Gemini CLI (`GEMINI.md`) drive the CLI over
  shell, JSON, and exit codes; each host's enforcement is declared in
  `packaging/hosts.json`, `capabilities --host X [--record]` prints and records
  the negotiated table, and a test fails if an adapter document's stated levels
  drift from the declaration.
- Session open now performs the fixed model-independent handshake (identity,
  branch, dirty state, active plan, obligations, invariants, required-source
  count, and the host's enforcement table); a pair rule attested with one
  artefact blocks closure naming the missing half; `charter --decay N` surfaces
  rules no session touched; and the context brief ranks by freshness and states
  "read N of M required sources".
- `skill lifecycle`/`skill retire` give every skill a state and a recorded
  reason; `godmode lessons` runs the promote-or-retire pipeline (a lesson either
  gets its guard observed running or is retired — never appended forever); and
  `godmode experiment` executes the bounded loop declared in
  `.godmode-experiment.json`, recording every run and refusing to pass the bound.
- `godmode locale check` validates `locales/<lang>/` guidance variants against
  their English sources — heading structure must match and fenced code blocks must
  be byte-identical — and a Hindi `GODMODE.md` ships as the first variant.
- `godmode mistakes` runs the mistake-class detectors distilled from the lesson
  corpus: a status label used as evidence must trace to its assigning record, a
  regenerated-but-never-cited artefact is a box-tick, a generalized guard citing
  one surface blocks, bundled claims must split, and `--process-started` blocks
  an RCA against a process older than the code it runs.
- `netgate` differential capture proves the runtime dials nothing: each CLI
  surface runs against a throwaway project under a socket audit hook, any
  connection fails, and a detector that cannot catch a planted attempt raises
  instead of reporting clean; CI adds a `pip-audit` scan of the CI tooling
  environment (the runtime has zero dependencies) with `security`-labelled
  issue triage against THREAT-MODEL.md.
- `godmode_parity` turns comparison into decisions: `parity_matrix` scores a local
  reference across eleven named dimensions, attaching a verdict+action pair to each
  and labelling stale references; `absorption_check` rejects synced-but-unwired
  files until a reader and a ran guard both cite them; `schema_ladder` exhausts
  existing columns and tables before allowing a reviewed new table.
- `planmode specify` records the what/why before any plan states a how — a plan
  without a spec is refused; the contract gains `parity`, `steps`, and `points`
  fields; and an approved plan now survives a session handoff: a different model
  resumes it (it appears in the resume brief) instead of re-deriving it.
- `godmode method --check-method X --check-record file.json` gates an RCA on its
  method's completion contract: fault-tree cut sets are derived from the tree (not
  typed from memory), timelines need three instruments with ordered events and
  declared holes, fishbone spines are project-configurable via `.godmode-rca.json`,
  and an "unknown" root without a shipped instrument is refused for every method.
- `godmode environment --target` classifies a mutation target's blast radius
  (unknown fails closed as production, never overridable by repo text);
  `version --reconcile` diffs the version across every surface that states one;
  and `docs --reconcile` enforces the change→documentation trigger table,
  configurable per project via `.godmode-docs.json`.
- Every archive record now carries its author's fingerprint (host, model, effort,
  adapter enforcement level) at the chronicle layer, not only attestations; the
  context brief is proven byte-identical across models in the suite; and a
  handoff test proves agent B resumes agent A's approved plan and next action
  without reading any transcript.
- `godmode removal record` remembers why something was deleted — reason, location,
  replacement, references, restoration path, and authorizer are all required — and
  `godmode removal why` answers from the record instead of archaeology.
- Runtime guardrails inside the no-daemon boundary: `ceilings` checks reported
  spend against declared run limits, `watch` is a per-boundary anomaly scan that
  interrupts on a skip pattern, `rewind --to SEQ` previews a rollback to a
  verified checkpoint (checkpoints now record HEAD; execution stays with the
  operator), and `planmode arbitrate` scores every open plan instead of taking
  the first one stated.
- `status render` emits the status document read-only from the store, `status
  handover` gives one rolling handover view, every pending item is
  existence-checked before presentation (a phantom whose cited artefacts all
  vanished is closed in the same pass with evidence), and `sprint` now routes
  through the single status writer instead of appending a second truth.
- `sbom --format spdx|cyclonedx` emits the zero-dependency claim in standard
  forms, `sbom --gate` fails the build when the declarative dependency policy
  (default budget: zero) is violated, and `checksums` produces a reproducible
  SHA-256 manifest over every tracked file with `--verify` for clean-clone
  comparison; CI enforces the gate and proves the manifest reproducible.
- `godmode integrity` runs the nine test-integrity monitors (assertion-diff,
  skip/quarantine, mock expansion, coverage shape, requirement anchor,
  red-before-green, harness validity, negative control, protected-test gate) over
  the current diff and exits non-zero when a change weakens what the suite proves.
- Over-budget briefs now degrade through typed compression before dropping
  anything: each compressed view declares the fields its mask removed and the
  `seq:` handle that reconstructs the original from the archive; record
  confidence decays with the records written since (not wall time), and baseline
  staleness reports that decay instead of flipping a binary flag.
- `branches --claim` declares this agent active in the worktree and exits
  non-zero when another agent's live claim exists — the collision surfaces before
  mutation; `--release` hands it back. No merge driver ships: per-record
  append-only files make state conflicts structurally impossible (decision
  recorded).

### Fixed

- The two routing-eval positives that misrouted between the router and
  continuity skills were reworded with home vocabulary; routing is now sound at
  10/10 with regenerated snapshots, and the eval gate exits green.
- The completeness sweep's findings closed: the CI action job diffs HEAD~1 on
  push instead of passing vacuously; the verify matrix gains Windows and macOS
  legs plus the full gate battery; the command-surface reference is regenerated
  from the parser (74 commands); the acceptance doc maps every gate to its proof
  command across all three host manifests; each SKILL.md routes to the gates it
  governs; the repository's own charter now compiles 5 HARD rules (Hindi variant
  kept in step); `docs` without flags names the missing flag; and the atlas
  resolves cross-module imports — orphan noise drops from 57% to 38% and
  `diagnose` flags its own resolver when the ratio is implausible.

## [0.1.0] - 2026-08-02

### Added

- Local-first, project-bound continuity archive with atomic hash-chained records.
- Evidence-led inspection, resume, diagnosis, and context explanation commands.
- Protected-action classification, previews, and scoped single-use capabilities.
- Branch, version, plan, checklist, incident, privacy, parity, and export workflows.
- Validated on-demand project skill forging for evidenced reusable gaps.
- Five routed skills for Codex and Claude Code, a bounded Claude `SessionStart` adapter,
  acceptance tests, and release checks.
- Codex and Claude Code manifests plus a Claude plugin marketplace catalog.
- Godmode logo, social-preview artwork, and passive AIimagined project identity metadata.

[Unreleased]: https://github.com/AIimagined/Godmode/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AIimagined/Godmode/releases/tag/v0.1.0
