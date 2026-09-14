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
| Ledger record tampering | Records are hash-chained (SHA-256, unkeyed - a content-integrity check, not a signature); an in-place edit to any record breaks every hash computed after it. A `godmode-chain-anchor.json` sidecar records the chain's length and head hash on every append, and a later read must still pass through that anchored point, which catches a deleted tail up to the last anchor. A read trusts a record file's on-disk size and modification time as unchanged since its last verified read; set `GODMODE_VERIFY_READS=1` to force full re-verification on every read instead. This detects tampering; it does not authenticate the archive against an operator who also has filesystem write access to it (see Out of scope). |
| Unaudited network egress | `godmode netgate` differentially audits five CLI surfaces (`init`, `inspect`, `resume`, `doctor`, `report`) and proves each makes zero outbound connections. It does not instrument hook subprocesses, and an operator-supplied check command (for example the command given to `claim --verify`, `ratchet run`, `oracle run`, `retest --run`, or `perimeter run`) runs verbatim and can reach the network - the audited "zero network" finding covers those five surfaces, not every command Godmode can be configured to run. |

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
| SEC-008 | Annotated (unsigned) git tags and published checksums for releases. |

## Out of scope

Godmode does not defend against a compromised operating system, a hostile local
user with filesystem access to the archive, or a coding agent host that ignores
exit codes. Those boundaries are stated, not silently assumed: `godmode
capabilities` reports what the current host can and cannot enforce.
