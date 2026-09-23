# Purpose

This skill exists so an outside source is judged on the files that were
actually opened, with receipts, and never given an adopt or extend verdict
from its landing page.

## Gap evidence

- seq:7999 - a lesson recorded 2026-09-02: an operator challenge exposed
  that recent surveys were README-level without saying so, and a code-level
  read of one source found an idea the README pass had missed. It carried no
  guard.
- seq:14408 - the same README-level miss recurred on 2026-09-16: seven
  sources were given extend verdicts before any source file was opened,
  because lesson seq:7999 carried no guard and nothing failed when it
  happened again. Its guard: an absorb decision whose import verdict is
  adopt or extend must cite a source-code path.
- seq:16489 - "Plan 3 Task 4: read receipts recorded by godmode read, absorb
  verdicts refuse README-only readings, parity --sources reports files
  opened (7fa218a)": the record that introduced `godmode read` and `parity
  --sources`, which this skill's steps 1, 3 and 4 front. The verbs existed;
  the read order they enforce was still prose.

## Promise

Every survey classifies the licence first, receipts each implementing file
it opens, measures its depth with `parity --sources`, and records both
verdicts - never adopt or extend from a surface read.

Future edits to this skill append their own seq: citation above.
