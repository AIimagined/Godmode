Capability register reconciled to code (U-S2): `capabilities.json` at the
repository root enumerates every capability id from the private sprint
ledger (`C-01`…`C-81`, ids and neutral one-line statements only, honest
gaps recorded where a numbered id has no retrievable statement) with a
status (`built`/`partial`/`unbuilt`/`rejected`) and, for `built`/`partial`
entries, the `file:`/`test:` pointers that back the claim.

`godmode_reconcile.reconcile_capabilities` holds the register to the same
both-directions discipline as the existing guard-citation reconciler: a
`built` entry whose pointer no longer resolves is dead, and an
`unbuilt`/`rejected` entry whose pointer DOES resolve is a status that went
stale the moment the code landed. `godmode assess` now surfaces the
`unbuilt` ids as `capability_debt`, and `godmode capabilities --reconcile`
runs the check directly, exiting non-zero on drift.
