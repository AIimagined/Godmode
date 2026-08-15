Capability coverage matrix (13c) and this repository's own dogfooding
(U-S3). `docs/CAPABILITY-COVERAGE.md` ships one table naming eight
capability classes in godmode's own vocabulary - session continuity, claim
admissibility, process discipline, minimality pressure, approval gating,
content trust, session burn measurement, and prose-restyling/token-burn
reduction as an explicit non-claim - with honest statuses: `covered` only
where surface pointers resolve to shipped code and tests, `partial` where
part of the class is mechanized and the rest is a stated boundary,
`not-claimed` where it is a scope boundary rather than a gap.
`godmode_reconcile.reconcile_capability_coverage` holds every row to the
same both-directions discipline as the capability register.

Dogfooding: all five of this repository's live HARD charter rules are now
provably planted (`godmode capability register` archive state,
`assess.hard_unplanted == []`), each against the specific test that already
exercised the guarded line rather than an inferred break. `init --roles`
scaffolded the eight missing authority-document roles; every stub now
carries a real paragraph about this repository's own state, decisions,
invariants, inventory, lessons, operator profile, sprint truth, and release
checklist (`assess.missing_roles == []`). Four of the eight role documents
(state, decisions, lessons, sprint-truth) are gitignored by this
repository's existing proprietary-content convention, so `missing_roles`
and the eval charter/ranking snapshots are, honestly, machine-local facts
here - the charter/ranking snapshots in `evals/fixtures/` are re-baselined
against the committed-only role documents so a fresh clone still reads
`routing-sound`.
