# Purpose

This skill exists so a release's notes are drafted from what the changelog
fragments and commits actually earned, and checked before the release ships
- instead of being written from memory at cut time and never checked at all.

## Gap evidence

- seq:11363 — an attestation on `guard:changelog-fragment-category` recorded
  the fragment gate itself proven: "observed failing: green(0) -> red(1) ->
  green(0)" against `tests.test_changelog_gate`, over the file that
  implements the check (`scripts/godmode_runtime/godmode_changelog.py`). The
  same attestation recurs dozens of times across the archive (seq:11378,
  seq:11405, seq:11512, seq:11609, seq:11625, seq:11712, seq:11767 and more)
  - a gate this well-exercised has no corresponding workflow naming when to
    run it, in what order, or what to do with a `missing-fragment` result.
- seq:6992 — a checklist record, `release-0.3.9 changelog satisfied`,
  evidenced by `cmd:godmode changelog check`, closing out that release's
  changelog step. The same checklist item recurs release after release
  (seq:7355 for 0.3.10, seq:7458 for 0.3.11) - each one a separate,
  hand-run instance of the same three-step sequence (check, merge, build
  and check the notes) this skill now names once.
- seq:7929 — a checkpoint recording "v0.3.12 cut: fragments merged,
  surfaces bumped, gates green pre-tag", the same fragment-then-merge
  sequence carried out again by memory rather than by a named flow.

## Promise

Cutting a release's notes means running the fragment gate, merging what it
found into the changelog, and building and checking the resulting notes
against the required shape - in that order, every time, with the exact
verb that already does each step.

Future edits to this skill append their own seq: citation above.
