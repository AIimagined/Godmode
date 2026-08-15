# Operator Profile

Who operates this project and what they authorize.

This repository is developed under a small set of standing directives that
apply regardless of which session or agent is doing the work: godmode owns
its capabilities natively (stdlib only, never a third-party tool depended
on at runtime — this session's `godmode_minimality.py` and the capability
register both hold to that), execution is sequential (no parallel agents;
one task worked at a time), commits favor conventional-commit messages
grouped by deliverable family with a changelog fragment per change, and
internal planning artifacts (checkpoints, the research ledger, sprint
specs) are proprietary and must never reach the shippable surface —
`capabilities.json` in particular is scoped to ids and neutral one-line
statements only, with the private ledger's own prose deliberately left out.
Release and push decisions remain the operator's explicit call, never
inferred from a green suite alone.
