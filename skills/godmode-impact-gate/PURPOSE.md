# Purpose

This skill exists so a staged edit's reach is scored before `git commit`,
from the project's own graph and boundaries, instead of being discovered by
the refusal - or not discovered at all when the crossing is one no refusal
checks.

## Gap evidence

- seq:17508 - "Plan 3 Task 8 landed on sprint as 13b1b68 + b8a89fe;
  closure/githooks/retest/atlas-registry modules green": the record that
  introduced the commit-time closure refusal (a staged code path with no
  green retest newer than its last edit is refused at `git commit`), which
  this skill's step 7 satisfies with `godmode retest --run`.
- seq:17482 - "Plan 4 Task 5 landed on sprint as ee25ef6 + 79c9bab;
  graph/closure/retest/reference-drift/verb-coverage modules green": the
  record that introduced the archive-derived graph behind `godmode atlas
  graph verify` and the `atlas closure` fan-out this skill's steps 2 and 3
  score. Both checks existed; nothing ran them as one pre-commit pass with
  the boundary, fence and paired-artifact checks beside them and a named
  way to accept an intended crossing.

The dependency-direction check (`godmode atlas --direction`, step 4) has no
landing record in the archive; its origin is commit 415f344 only.

## Promise

Before a multi-module commit, its fan-out, boundary crossings, fence
escapes and paired artifacts are scored, its retests are attested, and any
intended crossing is accepted on the record by name.

Future edits to this skill append their own seq: citation above.
