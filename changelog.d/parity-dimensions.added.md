The parity matrix now compares eleven capability-level dimensions instead of
file-surface counts: `capability` (public symbols via the atlas, both trees),
`architecture`, `runtime-wiring` (orphan ratios: presence vs wiring), the six
surface dimensions, `identity-freshness`, and `project-invariants`. Each
dimension carries one of five verdicts (ADOPT, EXTEND, DIVERGE-DELIBERATELY,
REJECT, ALIGNED) with a one-line reason; reference-ahead gaps name their adopt
candidates and project-ahead gaps list local extensions, never "ignore".
`adoption_floor` enforces E-14: an ADOPT whose paths overlap a recorded
invariant's `file:` evidence flips to REJECT ("protected local fix; parity is
a floor, not a ceiling"), wired into `parity_matrix` via a new optional
`archive` parameter. `waive` records written acceptance of a gap, and the
matrix's new `accepted` flag stays False while any open recommendation lacks
one.
