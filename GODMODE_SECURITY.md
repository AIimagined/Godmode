# Godmode Security Model

Godmode assumes repository content, filenames, branch names, command text, and imported
local references may be hostile. It treats them as data, never evaluates them, never
uses a shell to process them, does not follow directory symlinks during inspection, and
caps file hashing by size.

Protected-action controls are advisory unless a compatible host invokes the bundled
gate adapter before tool execution. The CLI itself never performs Git, database,
release, deployment, external-write, or destructive operations. A preview describes
the category and impact; authorization yields a password-backed, scoped, expiring,
one-use capability. Unknown mutations fail closed.

The capability store relies on operating-system account and file permissions. Its local
signing material is not a defense against an attacker who can rewrite the private state
directory or control the invoking process; such an attacker can also bypass the host
adapter. The authorization password gates issuance through the supported broker but is
not archive encryption. Use the host's sandbox, account isolation, and native approval
controls as the outer security boundary.

The archive uses exclusive lock files, atomic temporary-file replacement, restrictive
file modes where supported, canonical-path checks, monotonically increasing sequence
numbers, and a SHA-256 record chain. `doctor` detects corruption, identity drift, stale
inventory, contradictory invariants, unproven completion, and repeated failed attempts.

Report security issues without including secrets or private repository contents.
