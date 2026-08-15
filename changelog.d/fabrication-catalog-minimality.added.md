Fabrication-pattern detector catalog and a minimality report (13b).
`capabilities.json` gains a `detectors` section: every live mistake-class
detector in `godmode_mistakes.py` (`M1`, `M2`, `M6`, `M8`, `M13`-`M22` -
the sparse numbering is real; M3, M4, M5, M7, M9-M12 were never
implemented, and the catalog records that gap rather than hiding it) with
its function, version, and the fabrication family it targets.
`godmode_reconcile.reconcile_detectors` checks each id resolves to a real
function and a real guard test; a detector added to the source without a
matching catalog entry fails the population check.

`godmode minimality` is new: one command aggregating four existing surfaces
- atlas duplicate/orphan symbols, atlas speculative seams, census
unexercised surfaces, and charter decay - into a single ranked report with
counts and file pointers. Aggregation only; no new analysis.
