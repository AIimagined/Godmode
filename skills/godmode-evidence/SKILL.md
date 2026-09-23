---
name: godmode-evidence
description: "Shape a claim so its citations grade the first time: reflect it against the record, cite exit-bearing commands through `--verify`, give a hypothesis its `--refuted-by` falsifier, run falsifiers that aged past due, repair stale or loose citations, and resolve the claim once with fresh evidence. Use when a claim keeps being downgraded, a Stop gate keeps blocking on unsupported sentences, or cited evidence has drifted. Not for a second audit of a pass already accepted, and not for root-causing a failure."
---

# Godmode Evidence

## Outcome

A claim lands at the grade it asks for on the first attempt, because its
citations are shaped to be graded rather than argued: exit-bearing commands
run through `--verify`, a hypothesis names what would kill it, stale and
loose citations are repaired from the record instead of re-asserted, and a
claim is resolved once, with evidence it did not already have.

## Use

- A claim was downgraded (to observed or hypothesis) and the cite needs reshaping rather than a wrapper script.
- The Stop gate keeps blocking on sentences with no claim record behind them.
- A hypothesis-grade claim has no falsifier, or its falsifier has aged past due unrun.
- Evidence a standing claim cited has changed, vanished, or come loose from a rewritten commit.
- A claim has been settled and should be resolved held, failed or superseded.

## Do Not Use

- Independently rechecking a verdict another pass already accepted - that is `godmode-second-look`.
- Root-causing a crash or a red suite - that is `godmode-investigation`.
- Merging changelog fragments or building a version's release notes - that is `godmode-changelog`.

## Deterministic Execution Flow

1. **Reflect before recording.** `godmode reflect "<the claim text>"` - checks the sentence against what the record already says, and names a contradicting or superseding record before a second one is written.
2. **Repair what already came loose.** `godmode claim --stale` - grounded claims whose cited file evidence changed or vanished since they were recorded; `godmode freshness` - standing sources that are no longer what was graded; `godmode reanchor` - citations whose files changed or whose commits are gone.
   - Fallback: before a history rewrite, `godmode reanchor --snapshot` fingerprints every cited commit; after it, `godmode reanchor --remap` finds each one's new sha.
3. **Shape the cite to verify first time.** `godmode claim "<claim>" --grade verified --cite cmd:"<an exit-bearing command>" --verify` - every `cmd:` citation runs through the attested checker first. Exit-bearing forms (`git diff --quiet`, `grep -q`, `cmp -s`, `test`, `git merge-base --is-ancestor`) verify directly; a state-reporting command (`git status`, `ls`) caps at observed no matter what it prints. Name a file line with `file:<path>#L<n>` and a record with `seq:<n>`.
   - Fallback: a claim that still downgrades names why in `next_action`; fix that citation, never wrap the command in a script to change its grade.
4. **Give a hypothesis its falsifier.** `godmode claim "<hypothesis>" --grade hypothesis --refuted-by "<the one command or observation that would refute it>"`.
5. **Run the falsifiers that aged.** `godmode verify --falsifiers --dry-run` lists every hypothesis or incident falsifier aged past two days with no attestation; then `godmode verify --falsifiers` runs each and attests it on its own.
6. **Resolve once, with fresh evidence.** `godmode claim --resolve <seq> --outcome <held|failed|superseded> --cite <evidence the claim did not already cite>` - a claim resolves at most once.
7. **Clear the Stop-gate backlog.** `godmode status remaining --digest` - its `claims.parked` count is the claim-shaped sentences the Stop gate parked unrecorded; each gets a claim from step 3 or is softened. For the public surfaces, `godmode claim --scan` lists claim-shaped sentences whose line names no reproduction and no claim record.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never write a wrapper script to turn a state-reporting command into an exit-bearing one; use an exit-bearing form directly.
- Never record a hypothesis without `--refuted-by`; instead name the observation that would refute it, since a theory nothing could refute is not a finding.
- Never re-assert a stale claim over its drifted evidence; repair it from step 2 or resolve it superseded.
- Never resolve a claim with only the evidence it was recorded with, or resolve one sequence twice; instead cite fresh evidence once, and supersede if the outcome later changes.
- Never run `verify --falsifiers` before its `--dry-run` listing; know what will run before it attests.

## Acceptance

- A claim citing an exit-bearing command through `--verify` records at the grade it asked for.
- `godmode verify --falsifiers --dry-run` lists no falsifier aged past due once step 5 has run.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
