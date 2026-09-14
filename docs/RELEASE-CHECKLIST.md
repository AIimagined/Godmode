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

Before any public surface ships: `godmode claim --scan` reports `covered`.
A sentence on README, the listing kit, the coverage map, `llms.txt` or
`GODMODE.md` that carries a measured number or a promised outcome must name
its own reproduction on the same line, or a claim record must carry its
text; `tests/test_claim_scan.py` runs the same scan with an empty archive,
so the prose has to cover itself. `godmode examples --check` reports
`reproduced`, so every worked example still returns what it says it does.

Immediately before cutting a tag: `python quality/checks/version_payload_identity.py`
must print `verdict=ok`. It fails when `plugin.json` still declares the
version the latest reachable `v*` tag names while a commit after that tag
touched shipped payload (`skills/`, `hooks/`, `scripts/`, `bin/`,
`adapters/`, or a manifest) - the case where the tag and the manifest agree
with each other while neither agrees with what actually shipped afterward.
This is deliberately not run by `python -m unittest discover` or by CI: a
sprint branch commits payload continuously while carrying the last released
version number until the release-prep bump lands (see the version-bump step
above), so it reads `identity-drift` for most of a sprint by design and
would fail every ordinary commit if wired into the suite. Run it by hand,
here, once the version bump for this release is committed and before the
tag is created; `verdict=ok` (or `no-tags` on a project with none yet) is
the only passing state at that point.
