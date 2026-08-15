Cross-project precedent exchange, file-carried and opt-in (U-E2): `godmode
precedent export --domain <d> --out <file>` writes one project's
`reg:<domain>:*` register entries (key, state, evidence collapsed to bounded
statements) plus an origin fingerprint (`sha256(project-root basename +
archive genesis hash)[:16]`) as one self-verifying JSON file, whole-file
`content_hash` computed over canonical JSON. The operator carries the file -
that IS the transport; no network, no daemon.

`godmode precedent import <file>` verifies the content hash before writing
anything, then appends the entries into a SEPARATE namespace
(`reg-foreign:<origin-fp>:<key>`), never `reg:<domain>:<key>` itself. A hash
mismatch or malformed file is refused with nothing partially imported, and
`binding` is force-set to `False` on every imported record regardless of
what the file claims - a foreign precedent can never arrive binding, even
from a hand-crafted file whose own hash is genuinely valid.

Foreign precedents are advisory everywhere: `register(archive, domain,
foreign=True)` reads them separately from the local, binding
`register_view()`; `conflict_findings()` never scans the foreign namespace;
and `precheck()` surfaces a matching foreign entry in its own
`foreign_precedents` section, labeled `foreign precedent (from <fp8>)`,
which never joins `already_rejected`/`rejected_precedents` and never flips
`verdict` to blocking. `godmode precedent adopt --domain <d> --key <k>` is
the one explicit, human-triggered promotion to a local, binding record,
citing the foreign entry as evidence.
