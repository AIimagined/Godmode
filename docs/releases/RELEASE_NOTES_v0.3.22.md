# Godmode v0.3.22

The data release. Three field reports arrived on 2026-09-09 from one
project after three weeks of daily use, and their verdict was the same
sentence three times: the plugin names verbs to run and points at nothing.
Before changing a line, every complaint was replayed against that
project's own archive and transcript, an independent reviewer read the
code blind, and the mechanisms were traced in-process. The findings and
the numbers are in the changelog; this release acts on them.

## What changed

- **Turn-boundary nags name this session's asks only.** The ask pool had
  grown to 86 open asks up to 30 days old, and a three-shared-word match
  against a 90-word reply nagged on 34 of 42 real replies; with the
  session filter, 0 of 42. Older asks stay reviewable at handover
  (`checkpoint --review`, session close).
- **No ask is closed by keyword overlap.** The runtime closure added in
  0.3.21 would have "served" an ask on 41 of 42 replies. Asks close by hand
  or age out of the turn boundary with their session.
- **The failure line carries the record, not a verb list.** When a tool
  run fails, Stop names the last attested check, its age and head, every
  file changed since, and the incident count. Nothing else.
- **`checkpoint` names what nothing has checked.** Files changed since the
  last attested check that no attestation or claim cites are listed; a
  green-worded `--status` with no `--evidence` is flagged.
- **The resume nudge defers to the project's own state document.**
- **One observe-mode advisory per category per session.** Fifteen
  identical opaque-payload warnings become one; every refusal is still
  recorded for `observe --report`.
- **The done-bar reads fewer things as claims.** A short colon-terminated
  line is a label; a quoted span is a mention.
- **`atlas closure` takes the documented positional file list**, and a
  relative import on a TypeScript or JavaScript tree resolves to its file,
  so the dependents it lists are real on those trees (they were empty).
- **`precheck` bounds its atlas walk to 20 seconds** and says so when the
  bound was hit; on one field tree the unbounded walk outlasted the suite.
- **A `Write` over a tracked file the session never read is named at the
  call**, with the number of lines being replaced.
- **Record verbs take one shape.** `remember`, `checkpoint`, `attest`,
  `claim`, `build`, `plan`, `criterion` each accept their text positionally
  or by flag; both with different text is refused (obligation 10372).

## Known limits

- A `node -e` payload is still opaque and asked about at R2. A JavaScript
  read-only scan without a parser would be unsound; the advisory is bounded
  instead.
- Every CLI call reads and re-hashes the whole archive once (about 2.4 s at
  2,400 records, 4 s at 10,000). An on-disk cache would weaken the
  tamper-evidence contract and is not built.
- The atlas resolves relative import specifiers only; a bare package
  import or a path alias (`@/lib/x`) stays an inferred edge and does not
  count as a dependent.

## Verifying

- `python -m unittest` across eight shards on Windows, Python 3.14: all
  green after the two contract updates this release makes deliberate.
- `tests/test_field_reports_23_25.py` (11 tests) and
  `tests/test_record_verb_shape.py` (5 tests) each failed against 0.3.21
  before the change.
- `tests/test_repo_privacy.py`, `tests/test_docs_lint.py`,
  `tests/test_changelog_gate.py` green.
