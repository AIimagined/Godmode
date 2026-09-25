# Purpose

This skill exists so a staged edit's reach is scored before `git commit`,
from the project's own graph and boundaries, instead of being discovered by
the refusal - or not discovered at all when the crossing is one no refusal
checks.

## Gap evidence

- A commit-time refusal blocks a staged code path with no fresh retest, but
  nothing ran that check together with the graph-derived fan-out and
  closure scoring as one pre-commit pass.
- The fan-out and boundary-crossing checks existed separately from the
  fence and paired-artifact checks, with no named way to accept an intended
  crossing on the record.
- A dependency-direction check exists with no documented workflow tying it
  to the other pre-commit checks around it.

## Promise

Before a multi-module commit, its fan-out, boundary crossings, fence
escapes and paired artifacts are scored, its retests are attested, and any
intended crossing is accepted on the record by name.

Future edits to this skill append their own plain-language evidence above.
