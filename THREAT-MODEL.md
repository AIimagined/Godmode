# Threat Model

What Godmode defends against, and the control that does the defending. Each
control is implemented in the runtime or enforced by a gate; none depends on a
language model choosing to comply.

| Threat | Control |
|---|---|
| Malicious repository instruction | Repository text is treated as untrusted data (`godmode untrusted`); only user-approved policy roots may grant authority. |
| Direct or indirect prompt injection | Content is separated from instructions; protected actions are denied regardless of model output — the capability broker, not the model, decides. |
| Excessive agency | Least-privilege tool policy, workspace-scoped operation, and the local password broker (`godmode authorize`) for protected actions. |
| Sensitive-information disclosure | Secret and path classifiers, pre-egress preview (`godmode egress`), and local-only memory below Git metadata or the OS application-data directory. |
| Improper output handling | Generated shell, SQL, paths, code, and config are validated before execution; a preview precedes every protected operation. |
| Plugin / MCP compromise | No MCP servers, listeners, or daemons ship with Godmode; `GOVERNANCE.md` gates any future surface behind an explicit allowlist and permission manifest. |
| Supply-chain package | Zero runtime dependencies (`godmode sbom` publishes the claim; CI enforces it), checksummed releases, and a documented dependency budget in `CONTRIBUTING.md`. |
| Phishing / social engineering | Godmode never requests third-party credentials; the local approval prompt is clearly branded and runs on the user's machine only. |
| Local privilege escalation | No sudo/admin request by default; an operation needing elevation states the exact need and safer alternatives before proceeding. |
| Project memory leak | Continuity state lives outside the working tree; exports pass an allowlist and secret scan; the archive scanner (`godmode doctor`) checks for leaked secrets. |

## Security requirements

| ID | Requirement |
|---|---|
| SEC-001 | Least privilege for filesystem, shell, network, Git, database, and MCP tools. |
| SEC-002 | All protected decisions mediated outside model output. |
| SEC-003 | Untrusted-input validation at command, path, SQL, HTML, API, and persistence boundaries. |
| SEC-004 | No fail-open security gate; uncertainty produces deny, contain, or ask. |
| SEC-005 | No production mutation using local test credentials or generic administrator identities. |
| SEC-006 | No destructive smoke tests against real project IDs or customer data. |
| SEC-007 | Secret scan before memory write, file change, commit, outbound call, and diagnostics export. |
| SEC-008 | Signed tags and published checksums for releases. |

## Out of scope

Godmode does not defend against a compromised operating system, a hostile local
user with filesystem access to the archive, or a coding agent host that ignores
exit codes. Those boundaries are stated, not silently assumed: `godmode
capabilities` reports what the current host can and cannot enforce.
