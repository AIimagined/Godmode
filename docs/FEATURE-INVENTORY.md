# Inventory

What exists and where, so nothing is rebuilt blind.

`capabilities.json` (repo root) is the machine-checkable inventory of 105
numbered capability statements (`C-01`…`C-105`) and 14 live mistake-class
detectors (`M1`, `M2`, `M6`, `M8`, `M13`–`M22` — the numbering stays sparse
because `godmode_mistakes.py` implements only those ids, and
`capabilities.json` records that gap rather than papering over it).
`scripts/godmode_runtime/godmode_minimality.py` is a small aggregator with
no analysis of its own, folding `godmode_atlas`'s duplicate/orphan/
speculative-seam findings and `godmode_census`/`godmode_attest.advisory_decay`'s
unexercised-surface and charter-decay findings into one ranked report, wired
to `godmode minimality`. `docs/CAPABILITY-COVERAGE.md` is the eighth
artifact: one table, eight capability classes, each row's status
reconciled against shipped code and tests by `godmode capabilities
--reconcile`.

`scripts/godmode_runtime/godmode_donebar.py` (C-9) gives the Stop hook's
own completion checks a role: `godmode governance --checks` prints the
fixed check -> reviewer/builder table, and `godmode governance escalate
<check> --reason "<why>"` records a builder's reason for skipping one
check (`scope-still-open`, `open-operator-asks`, `style`) for a few real
Stop turns, bound to the current session anchor; a reviewer check
(`uncited-claim`, `unattested-hard-rule`, `reworded-done`) refuses with
exit 2. `docs/COMMAND-REFERENCE.md`'s generated table stays verb-level
(`governance`, unchanged) - this subcommand surface is documented here
instead of by hand-editing a generated file.
