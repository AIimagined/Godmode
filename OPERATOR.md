# Operator Profile

Who operates this project and what they authorize.

This repository is developed under a small set of standing directives that
apply regardless of which session or agent is doing the work.

- Godmode owns its capabilities natively: stdlib only, and never a
  third-party tool depended on at runtime.
- Execution is sequential: no parallel agents, one task worked at a time.
- Commits favor conventional-commit messages grouped by deliverable family,
  with a changelog fragment per change.
- Internal planning artifacts — checkpoints, the research ledger, sprint
  specs — are proprietary and must never reach the shippable surface.
  `capabilities.json` in particular is scoped to ids and neutral one-line
  statements only, with the private ledger's own prose left out.
- Release and push decisions remain the operator's explicit call, and are
  never inferred from a green suite alone.
