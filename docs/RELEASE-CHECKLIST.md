# Checklist

Standing verification rows this project re-runs before it ships.

Before this repository's commits land: the affected suites
(`tests.test_capability_register`, `tests.test_minimality`, plus every
existing suite touched by the reconcile/assess/console edits) pass serially;
`godmode assess` on this repo reports `capability_debt` as a stated list
rather than an error; `godmode selftest`, `godmode scenarios`, and `godmode
capabilities --reconcile` all exit clean; `godmode docs --lint` is clean
against the four new/edited docs (`docs/CAPABILITY-COVERAGE.md` plus the
eight role stubs this session filled); and every commit carries its
`changelog.d/` fragment before it is made, per the changelog gate this same
repository enforces on every other contributor.
