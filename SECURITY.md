# Security Policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository
(Security tab, "Report a vulnerability"). Do not open a public issue
for anything exploitable.

You can expect an acknowledgment within 7 days. Please include the
godmode version, the host (Claude Code, Codex, or other), and a
minimal reproduction.

## Supported versions

The latest released version receives security fixes. Older versions
are not patched; upgrade to the current release.

## Threat model

Godmode's design assumptions - what input it distrusts, how it treats
repository content, and what its gate refuses to evaluate - are
documented in [GODMODE_SECURITY.md](GODMODE_SECURITY.md).
