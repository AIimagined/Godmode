---
name: godmode-ci
description: "Run CI's checks locally, in CI's order, before opening a pull request: the task precheck, the fragment gate against the base branch, the preflight of HEAD or a working-tree snapshot in a disposable worktree with the designated suite in shards, the install self-test and the control grid, the version reconciled across every surface, and a fresh hook proof on the host. Use when a PR is about to be opened, a CI job went red and the failing leg must be reproduced locally by its shard, or the local gate run is slower than the gate it feeds. Not for merging fragments into release notes, and not for approving a destructive action."
---

# Godmode CI

## Outcome

Every check CI will run has run here first, cheapest first, on the exact
tree that will be pushed, so a push is refused by a seconds-long gate before
it can fail a half-hour suite, and a red CI job reproduces locally with the
shard and the command that failed.

## Use

- A push or a pull request is about to be opened.
- A CI job went red and the failure has to be reproduced on this machine.
- The pre-push run costs more minutes than the gate it feeds, or reruns a suite for a HEAD already validated.
- The version, the bindings or the hook proof may have drifted since the last green run.

## Do Not Use

- Merging fragments or building the release notes for a version - that is `godmode-changelog`.
- Authorizing a history rewrite, a force push or a release - that is `godmode-governance`.
- Reconciling a host's installed manifests - that is `godmode-host-sync`.

## Deterministic Execution Flow

1. **Precheck the task on the tree as it is.** `godmode precheck --about "<the task>"` - paired artifacts, fences and the closure of the changed paths; a finding here costs seconds, so it runs before anything that costs minutes.
2. **Run the fragment gate against the base.** `godmode changelog check --base main` - every user-visible change carries a fragment; a missing one is named with its commit.
3. **Preflight the tree CI will see.** `godmode precheck --preflight` - HEAD validated in a disposable worktree: the gate list first, the designated suite after, stopped at the first red with its reproduce command. With uncommitted tracked changes to validate: `godmode precheck --preflight --dirty` - a snapshot of the working tree instead of a refusal; the report names which tree it validated and every untracked path it did not.
   - Fallback: to reproduce one red CI leg, `godmode precheck --preflight --suite-shards 4 --shard-index 2` runs that shard alone and attests it as one leg, never as the suite.
4. **Prove the install itself.** `godmode selftest` - the shipped install's own checks; `godmode grid` - the control grid, every protected class denied or asked.
5. **Reconcile the version across every surface.** `godmode version --reconcile` - the plugin manifests, the runtime and the notes agree on one version before a tag can name it.
6. **Refresh the hook proof.** `godmode hooks probe` - a fresh live deny on this host, so enforcement reads as proven rather than registered.
7. **Retest what the change reaches.** `godmode retest --run` - the tests the code graph says the change must retest, run and attested.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never run the suite before the cheap gates; instead let the preflight order stop at the first red.
- Never rerun a suite for a HEAD it already validated green; instead cite that run's attestation.
- Never push around a red gate with a hook bypass; instead fix the finding or record the decision that waives it.
- Never report a shard as the suite; instead name the shard index and the leg it attested.
- Never validate a tree other than the one being pushed; instead name HEAD or the snapshot the report validated.

## Acceptance

- The preflight report names the tree it validated and lists no unvalidated path silently.
- Every gate CI runs has a local run on the record for the pushed HEAD.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
