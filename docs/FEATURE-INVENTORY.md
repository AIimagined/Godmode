# Inventory

What exists and where, so nothing is rebuilt blind.

`capabilities.json` (repo root) is now the machine-checkable inventory of
81 numbered capability statements (`C-01`…`C-81`; C-73 turned out to have
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
