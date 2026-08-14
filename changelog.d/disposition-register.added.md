Disposition register with superseded states and rejection precedent (U-V2):
a closed-enumeration register (`established`, `superseded`, `refuted`,
`worse-than-baseline`, `matched-baseline`, `rejected-precedent`, `open`) over
`decision` records whose subject is `reg:<domain>:<key>`. The register is a
derived view, never a stored second copy - `register_view()` folds every
record for a domain into latest-state-per-key with full lineage, and an
unlisted key reads as the explicit named default `open`, not an error and
not `None`.

Every non-open entry needs at least one `witness:`/`verdict:`/`file:`
evidence citation, refused at `set_state()` and again at the archive seam
itself (`godmode_invariants._register_invariants`, seeded eagerly into
`Chronicle.append()`'s `KIND_INVARIANTS`) so a raw append that bypasses this
module cannot slip an unevidenced or unlisted-state entry past either.
Transitions are legal-only: `open` reaches anything; every closed
disposition's only way back to `established` is a record naming
`supersedes:<seq>` that cites the exact record it replaces -
`established -> superseded` and `rejected-precedent -> established` both
need it. `set_state()` refuses an illegal or wrongly-cited transition at
write time; `conflict_findings()` detects the same violations at read time
for a hand-appended record that skipped `set_state()` - a HARD halt finding,
never a silent latest-wins.

`precheck` now consults `rejected_precedents()`: a task whose normalized
terms name a `rejected-precedent` key across any domain is told the
precedent's sequence and the way through - cite it and supersede it, or drop
the work. `godmode register set|supersede|show`.
