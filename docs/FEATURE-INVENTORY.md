# Inventory

What exists and where, so nothing is rebuilt blind.

`capabilities.json` (repo root) is now the machine-checkable inventory of
105 numbered capability statements (`C-01`…`C-105`; `C-83`…`C-105` are the
2026-09-11 builds: the held-back oracle, `depends_on`, hygiene, proposed
registry rows, manifest desync, hook timing, the two static checks, the
gate's temp alias, the swallowed-script nudge, the windowed-absence
advisory, the branch-deletion preview, the commit-time private-term guard, the incident prediction, the swallow audience, the prose closure, the docstring-promise check, and the incident fixes; C-73 turned out to have
real content once code comments were searched, not only the sprint-ledger
markdown — it is "rank-fusion context ranking," `rejected` on measurement
per `godmode_corpus.rank`'s own docstring, a fix-round-1 correction; the
remaining honest gaps are C-75–C-78, C-80, C-81, where the reachable
private ledger names an id with no retrievable statement anywhere) and 14
live mistake-class detectors (`M1`, `M2`,
`M6`, `M8`, `M13`–`M22` — the sparse numbering is real: `godmode_mistakes.py`
never implemented M3, M4, M5, M7, M9–M12, and `capabilities.json` records
that gap rather than papering over it). `scripts/godmode_runtime/godmode_minimality.py`
is new this session: a ~70-line aggregator with no analysis of its own,
folding `godmode_atlas`'s duplicate/orphan/speculative-seam findings and
`godmode_census`/`godmode_attest.advisory_decay`'s unexercised-surface and
charter-decay findings into one ranked report, wired to `godmode
minimality`. `docs/CAPABILITY-COVERAGE.md` is the eighth artifact: one
table, eight capability classes, each row's status checked against shipped
code and tests by `godmode capabilities --reconcile`.
