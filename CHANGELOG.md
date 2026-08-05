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
