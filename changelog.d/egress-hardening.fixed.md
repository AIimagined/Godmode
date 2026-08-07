Egress hardening closed four gaps at the disclosure boundary. Path containment:
every path a manifest or scan touches is resolved and verified inside the
project root first; `../`, absolute, and symlink escapes are refused unread
with a `path-escape` finding. Disclosures now carry `destination` and
`destination_known`, stating "unknown" explicitly instead of omitting the
receiving party. An optional `.godmode-privacy.json` lets a user declare
`sensitive_paths` and `never_leave` globs that extend (never shrink) the
built-in denials; a never-leave match blocks a notice exactly like a secret.
And `redact=True` makes the "redact further and send less" choice real:
blocking items are replaced by bare `redacted` entries - no counts, no
excerpts - and the remaining scope is no longer blocked.
