# Godmode v0.2.0 — release notes

Status: RELEASED 2026-08-06 (tag v0.2.0), on explicit owner instruction.
Every claim below is enforced by the acceptance suite
(`python -m unittest discover -s tests`), the staged-failure catalogue
(`godmode scenarios`), and the runtime's own gates — not asserted.

## What v0.2.0 is

The first tagged public preview of a local-first continuity and evidence-governance
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

1. `changelog merge --set-version 0.2.0` folded 35 fragments into CHANGELOG.md
2. Full suite (195 tests) plus every gate green at tag time
3. Annotated tag `v0.2.0` with the checksum manifest recorded; GPG signing
   remains an owner step (SEC-008) — sign the tag when a key is configured:
   `git tag -s v0.2.0-signed v0.2.0`
