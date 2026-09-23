---
name: godmode-second-look
description: Independently recheck a change, session, PR, or diff that already carries an accepted claim or verdict. Use before trusting an earlier pass as settled, sorting any new finding into a gap, bug, verification-miss, or scope-drift. Not for a first-time look at work nobody has checked yet, and not for re-running the same suite the first pass already ran.
---

# Godmode Second Look

## Outcome

A prior pass being accepted is not proof it survives a second, independent look. This skill runs that second look against fresh evidence and either leaves the original verdict standing, on the record, or reopens it with a cited reason - never a silent redo of the same work.

## Use

- Another session, PR, or diff already carries an accepted claim or verdict and the cost of being wrong about it is high enough to check again.
- A change is about to be relied on (merged, released, cited by a later claim) and no one but its own author has looked at it.
- A recheck needs to say precisely what kind of thing it found: a gap the first pass never covered, a bug it missed, a verification miss (it claimed a check ran that didn't prove what it says), or scope drift (it now covers ground the approval never considered).

## Do not use

- For a first-time investigation of a fresh, never-reviewed report - that is `godmode-investigation`.
- To re-run the exact same suite the first pass already ran and call agreement a second look; this skill needs an independent angle (fresh evidence, a different checker, a wider blast radius), not a repeat.
- As a way to stall a decision indefinitely; a second look ends in a recorded disposition, held or reopened.

## Deterministic Execution Flow

1. **Locate the pass under review.** Read the original record in full rather than trusting its subject line:
   ```
   godmode history --kind claim --subject "<exact subject text>"
   godmode history --kind verdict --subject "<exact subject text>"
   ```
   When the exact sequence number is already known instead:
   ```
   godmode verdict show --seq <n>
   ```
   (verdict records only - a claim record has no `show` counterpart; use `history --kind claim --subject` for those.)
   Fallback: if neither resolves, there is no accepted pass to recheck - route to `godmode-investigation` for a first look instead.

2. **Check whether the evidence the original pass relied on is still there.**
   ```
   godmode claim --stale
   ```
   Any of the original pass's own file citations appearing here (changed or vanished since it was recorded) is itself a finding - the approval rested on evidence that no longer exists as read.

3. **Compare the state at approval against the state now**, when there are two comparable states (a base commit vs HEAD, a pre-fix run vs post-fix run, a claimed file vs its current content):
   ```
   godmode differential record --subject "<what changed since the accepted pass>" --a <seq:N|file:path|cmd:...> --b <seq:N|file:path|cmd:...> --method "cmd:<comparison command>" --delta "<one observed difference>"
   ```
   Fallback: when there is only one state to look at (no prior snapshot to diff against), skip straight to step 4 and rely on retest and closure instead.

4. **Run the tests that pin the changed files, independently of whatever the first pass ran:**
   ```
   godmode retest --base <the pass's own base ref> --run
   ```
   A test the first pass never ran, or one that now fails, is a verification-miss finding, not a gap - the first pass claimed coverage it did not have.

5. **Map how far the change actually reaches**, to catch scope drift the approval never considered:
   ```
   godmode atlas closure --changed <path> [<path> ...] --depth 2
   ```
   Fallback: a fresh checkout or one with no saved graph refuses with "no graph snapshot found" - run `godmode atlas graph rebuild` once, then repeat the closure call.
   A caller or dependent outside what the original pass described is a scope-drift finding.

6. **Record an independent disposition**, distinct from the original claim, with its own checker:
   ```
   godmode verdict record --claim "<the original claim, restated>" --value <observed value> --witness file:<path>|seq:<n> --checker "<independent check command>" --acquitted-by independent
   ```
   The checker here must not be the same command the original pass cited; an independent second look needs a second instrument.

7. **Close the loop on the original record**, whichever way it goes:
   - Nothing new, evidence still holds:
     ```
     godmode claim --resolve <original-seq> --outcome held --cite verdict:<new-verdict-seq>
     ```
   - A gap, bug, verification-miss, or scope-drift finding stands up under evidence:
     ```
     godmode claim --resolve <original-seq> --outcome superseded --cite file:<path> --cite cmd:<the independent checker's command>
     ```
     `verdict:<seq>` only resolves a claim when that verdict is CONFIRMED; a
     second look that finds something records a refuted (or malformed)
     verdict in step 6 - exactly the case this citation cannot cover. Cite
     the fresh `file:`/`cmd:` evidence the independent checker actually read
     instead.
   A claim resolves at most once; do not call `--resolve` twice on the same sequence.

8. **When a durable regression check is worth keeping** (the finding is the kind that could silently recur):
   ```
   godmode verify "<name>" --rule <rule-id> --command "<the check that would have caught this>"
   ```

## Must not

- Must not resolve any sequence other than the exact one identified in step 1; a second look that reopens the wrong record is worse than one that reopens nothing.
- Must not record `--outcome superseded` without at least one fresh `--cite` the original pass did not already have; disagreement without new evidence is not a reversal.
- Must not close a claim with `--outcome held` citing only the original pass's own evidence; cite the step 6 independent verdict (`--cite verdict:<seq>`) so "held" means a fresh check agreed, not that no fresh check ran.
- Must not silently redo the underlying work and stay quiet when it agrees - agreement is recorded with `--outcome held`, not left unrecorded.
- Must not treat this skill's own recheck as exempt from the evidence bar it is enforcing on the first pass.

## Taxonomy

- **Gap** - something the original pass never looked at, but should have.
- **Bug** - something the original pass looked at and got wrong.
- **Verification-miss** - the original pass claimed a check that does not actually prove what it says (a stale citation, a checker that doesn't discriminate, a green run that never reproduced the failure).
- **Scope-drift** - the change now reaches further than what was approved.

## Completion

Report which of the four taxonomy classes applied (or none), the fresh evidence behind that call, and the exact record (`held` or `superseded`) written to close the loop. A second look that produces no new record proved nothing happened - it just used the verbs and stopped.
