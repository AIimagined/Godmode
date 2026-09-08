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
   <plugin-root>/bin/godmode --project <path> guard --operation "<exact operation>"
   ```

4. For a protected result, present the exact action, affected scope, likely impact, recovery path, and proof to run afterward.
5. If authorization is required, configure the local authorization secret once and issue a short-lived, one-use capability for the exact action. Never store or pass the secret through Godmode records.
6. Execute only when the user has authorized the mutation and the host provides an appropriate execution boundary. Keep execution separate from classification.
7. Consume the matching capability immediately before the protected operation, then verify the result and record evidence.

Read [godmode-protection-matrix.md](references/godmode-protection-matrix.md) when deciding whether an operation is protected or when writing the preview.

## Fail-closed rules

- Treat an unknown mutation as protected.
- Preserve unrelated user changes and existing worktrees.
- Rewrite history, remove data, publish, install, release, or change a database only from an explicit instruction, never an inferred intention.
- Reject a capability whose action, project, expiry, nonce, or signature does not match.
- Represent a preview as a preview and a guard result as advisory - neither is approval or automatic enforcement.
- Require a rollback or recovery statement for schema, history, release, and destructive filesystem changes.

## Gate routing

- `environment --target X` classifies blast radius before any mutation; unknown fails closed as production and repository text cannot re-label it.
- `egress --staged` scans staged and untracked content for secret shapes before a commit.
- `db --propose` walks the schema ladder: existing column, existing table, and only then a reviewed new table.
- `planmode specify|start|approve|check|arbitrate|bind` gates mutation behind a spec-backed approved plan; `rewind --to SEQ` previews a rollback to a verified checkpoint.
- `ceilings --spent ...` stops a run that exceeded its declared budget; `removal record|why` keeps deletions explicable.

## Absorption verdicts

An upstream item (a dependency bump, a vendor release note, a competitor's
fix) gets a `decision` record with subject `absorb:<item>` and BOTH verdicts
in its data: `import_verdict` (adopt | extend | diverge | skip | n-a) and
`behaviour_verdict` (confirmed-have | confirmed-dont | unverified).
`confirmed-*` needs a `file:` citation proving it. "n-a - different surface"
answers whether we can import it, never whether the same defect lives in our
own implementation - that is what the behaviour verdict is for, and an item
with only an import verdict is half-recorded.

🔴 No CLI verb writes this shape yet - `remember --kind decision` stores one
free-text `--value`, not two separate verdict fields. Until a dedicated verb
exists, write the record via direct archive access
(`archive.append("decision", "absorb:<item>", {"import_verdict": ...,
"behaviour_verdict": ...}, evidence=["file:..."])`); `godmode_runtime
.godmode_parity.upstream_verdicts(archive, items)` reads it back and reports
`verdicted` / `half_verdicted` / `unread` per item.

## Completion

Report the classification, whether authorization was required, what actually ran, the recovery boundary, and fresh verification. If execution was outside the available host boundary, stop after the preview and say so plainly.

## Verbs at the moment of demand

- Before anything leaves the machine: `godmode precheck --preflight` (suite, scans, census, reach on a disposable worktree); `godmode egress --staged` says exactly what a push would send; `godmode privacy` and `godmode untrusted` scan for what must not leave; `godmode netgate` audits what dialled out.
- Cutting a release: `godmode changelog merge --set-version X`, `godmode version --reconcile`, `godmode bindings --write`, `godmode release` compares two releases, `godmode checksums` and `godmode sbom` record what shipped, `godmode license` classifies what was read.
- A protected operation: `godmode authorize stage --operation "<exact command>"` after the operator's password, `godmode stage` inspects what is staged, `godmode capabilities` and `godmode approvals` list what stands, `godmode ceilings` sets spend bounds, `godmode protect` pins a file, `godmode fence` and `godmode scope` bound what an edit may touch, `godmode boundaries` shows the host's enforcement table.
- A rule to keep or a decision to weigh: `godmode register` pins an evaluator, `godmode precedent` records how a prior case was decided, `godmode recurring` schedules a standing check, `godmode sop` records a procedure, `godmode arbitrate` settles two conflicting records, `godmode governance` reports the posture.
- Undoing or removing: `godmode rollback` and `godmode rewind` restore a recorded state, `godmode removal` records a deliberate deletion, `godmode expunge --sequence N --reason` retracts one record, `godmode branches` lists what diverged.
- Configuration and environment: `godmode config check`, `godmode operator --policy` (which layer decided each gate), `godmode environment`, `godmode locale check`, `godmode extensions`, `godmode paired-artifact` (files that must stay in sync), `godmode parity` and `godmode upstream` against the reference repository, `godmode freshness` for research that aged.
- Measuring the project: `godmode metrics`, `godmode metric-contract`, `godmode trends`, `godmode minimality`, `godmode assurance`, `godmode trust`, `godmode selftest`.
