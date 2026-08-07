# Godmode v0.2.1 — release notes

Status: RELEASED 2026-08-07 (tag v0.2.1), on explicit owner instruction.
Every claim below is enforced by the acceptance suite
(`python -m unittest discover -s tests`), the staged-failure catalogue
(`godmode scenarios`), and the runtime's own gates — not asserted.

## What v0.2.1 is

The second tagged preview of a local-first continuity and evidence-governance
runtime for coding agents, shipping as a plugin for Claude Code, Codex, and
Grok, plus a composite GitHub Action.

## Guarantees (each with its proof surface)

- **Zero collection** — no telemetry, network call, daemon, or cloud memory
  (privacy suite; differential network-capture gate in CI).
- **Zero runtime dependencies** — Python standard library only
  (`godmode sbom --gate`, enforced in CI).
- **Local-only state** — hash-chained records below Git metadata or the OS
  application-data directory (chronicle tamper test).
- **Protected actions stay mediated** — scoped, expiring, single-use local
  capabilities the model cannot mint (sentinel suite; forged-capability
  scenario).

## What changed since v0.2.0

- **Enforcement became real on Claude Code.** A `PreToolUse` gate decides
  mutating tool calls in the host's own contract; `tool_call_interception`
  reports HARD only where that gate is installed.
- **Measurement replaced assertion.** `metrics` computes the twelve product
  measures locally, reporting insufficient-data rather than a flattering zero;
  `fuzz` feeds seeded garbage to every classifier and config reader.
- **Two real defects found by the new tools and fixed**: four config readers
  crashed on a file containing `null`, and duplicate detection was counting
  naming conventions (499 pairs down to 33).
- **The session now reports what the gates did** — refusals counted with their
  record sequences, silent when nothing fired, switched off with
  `.godmode-report.json`.
- **`docs --lint`** holds public prose to the standard claims are held to.
- Chronicle appends are O(1) with an auditable `expunge` for leaked secrets;
  the task-completion report, derived SQLite index, database manager, stage
  machine, RCA SOP, and semantic parity dimensions all shipped.

## Highlights

- Session kernel: compiled charters, attestation gates, claim–citation binding
  with automatic downgrade, model-independent handshake and closing gate.
- Continuity: bounded deterministic briefs (byte-identical across models),
  typed compression with declared masks, removal memory, plan/spec chain that
  survives model handoffs.
- Anti-loop and mistake-class detectors over the archive's own records.
- Test-integrity monitors (nine, per PRD §16.2), changelog fragment gate,
  documentation trigger table, version reconciler, environment classifier.
- Evaluation: 15 staged golden failures bound to acceptance IDs, adversarial
  control grid, routing eval runner with snapshots, local benchmark.
- Distribution: three host manifests generated from one source, composite CI
  action, Hindi guidance variant with structural validation, SPDX/CycloneDX
  SBOMs, reproducible checksums.

## Known limits (stated, not hidden)

- Enforcement is HARD only where a host invokes the gate adapter; `godmode
  capabilities` prints the honest per-host table.
- Cross-agent live resume and host-marketplace listings require real hosts and
  owner actions; tracked as open items, not claimed.

## How this release was cut

1. `changelog merge --set-version 0.2.1` folded 17 fragments into CHANGELOG.md
2. Full suite (387 tests) plus every gate green at tag time
3. Annotated tag `v0.2.1` with the checksum manifest recorded; GPG signing
   remains an owner step (SEC-008) — sign the tag when a key is configured:
   `git tag -s v0.2.1-signed v0.2.1`

## Verifying

```
python -m unittest discover -s tests        # 387 tests at this tag
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . version --reconcile --brief
```

This section was added retroactively. The document-linter contract that
requires it did not exist when this release was cut, and every check the linter
carried at the time asked only whether a document contained something it should
not — so a release note with no verification instructions was reported clean.
