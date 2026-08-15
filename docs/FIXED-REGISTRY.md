# Invariants

Behaviours that must stay true, each owning a guard.

Every `built` entry in `capabilities.json` must keep its `impl` and `guard`
file pointers resolving on disk, and every `unbuilt`/`rejected` entry must
keep NEITHER pointer resolving — guarded by
`godmode_reconcile.reconcile_capabilities`, exercised in
`tests/test_capability_register.py`; a renamed or deleted implementation
file, or a status label left stale after the code landed, fails this check
before it fails anything else. That drift-in-either-direction rule also
covers the `detectors` section (each id must resolve to a real function in
`godmode_mistakes.py` and a real guard test — `reconcile_detectors`) and
for `docs/CAPABILITY-COVERAGE.md` (`reconcile_capability_coverage`): a
`covered` row's pointer must resolve, and a `partial`/`not-claimed` row's
pointer must not. All three checks are population-pinned grows-only, so a
newly added capability, detector, or coverage row can raise the count but
never silently lower it.
