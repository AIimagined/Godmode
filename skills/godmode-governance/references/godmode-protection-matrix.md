# Godmode Protection Matrix

| Operation | Default class | Minimum preview | Completion evidence |
| --- | --- | --- | --- |
| Read files, status, logs, or metadata | Read-only | Scope and purpose | Observation returned |
| Edit ordinary project files | Mutating | Files, intent, verification | Diff plus relevant check |
| Delete or overwrite material data | Protected | Exact targets, recovery, verification | Target audit and post-state |
| Commit, push, merge, rebase, reset, or tag | Protected | Branch, dirty state, refs affected, recovery | Fresh status and ref identity |
| Create, remove, or move a worktree | Protected | Worktree identity, path, branch, recovery | Worktree inventory |
| Apply a schema or data migration | Protected | Environment, backup or rollback, checks | Schema and data verification |
| Publish, release, deploy, or call an external mutation | Protected | Destination, artifact, audience, rollback | External result plus local record |
| Handle credentials or authorization secrets | Protected | Secret boundary and redaction plan | No secret-shaped archive content |
| Unknown operation with side effects | Protected | Resolve exact action before proceeding | Operation-specific proof |

Capabilities are local, short-lived, single-use, project-bound, and action-bound. They are an explicit authorization artifact, not a replacement for the execution host's own permission model.
