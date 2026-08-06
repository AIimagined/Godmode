---
name: godmode-governance
description: Preview and govern protected engineering actions without executing them implicitly. Use before destructive, externally visible, history-changing, database-changing, release, credential, branch, or worktree operations.
---

# Godmode Governance

## Outcome

Turn a risky requested operation into an explicit, reviewable contract. This skill classifies and previews the operation; it does not grant the host permission or claim to intercept every tool.

## Workflow

1. Inspect the current project identity, branch or worktree, dirty state, and the exact target.
2. Separate observation from mutation. Read-only inspection needs no capability.
3. Classify the proposed action with:

   ```powershell
   python <plugin-root>/scripts/godmode.py --project <path> guard --operation "<exact operation>"
   ```

4. For a protected result, present the exact action, affected scope, likely impact, recovery path, and proof to run afterward.
5. If authorization is required, configure the local authorization secret once and issue a short-lived, one-use capability for the exact action. Never store or pass the secret through Godmode records.
6. Execute only when the user has authorized the mutation and the host provides an appropriate execution boundary. Keep execution separate from classification.
7. Consume the matching capability immediately before the protected operation, then verify the result and record evidence.

Read [godmode-protection-matrix.md](references/godmode-protection-matrix.md) when deciding whether an operation is protected or when writing the preview.

## Fail-closed rules

- Treat an unknown mutation as protected.
- Preserve unrelated user changes and existing worktrees.
- Never rewrite history, remove data, publish, install, release, or change a database from an inferred intention.
- Reject a capability whose action, project, expiry, nonce, or signature does not match.
- Do not represent a preview as approval or a guard result as automatic enforcement.
- Require a rollback or recovery statement for schema, history, release, and destructive filesystem changes.

## Gate routing

- `environment --target X` classifies blast radius before any mutation; unknown fails closed as production and repository text cannot re-label it.
- `egress --staged` scans staged and untracked content for secret shapes before a commit.
- `db --propose` walks the schema ladder: existing column, existing table, and only then a reviewed new table.
- `planmode specify|start|approve|check|arbitrate|bind` gates mutation behind a spec-backed approved plan; `rewind --to SEQ` previews a rollback to a verified checkpoint.
- `ceilings --spent ...` stops a run that exceeded its declared budget; `removal record|why` keeps deletions explicable.

## Completion

Report the classification, whether authorization was required, what actually ran, the recovery boundary, and fresh verification. If execution was outside the available host boundary, stop after the preview and say so plainly.
