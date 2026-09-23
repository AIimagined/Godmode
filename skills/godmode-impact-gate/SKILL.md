---
name: godmode-impact-gate
description: "Score a staged commit's fan-out and architectural-boundary crossings just before committing: dependents left unfollowed, hook-to-runtime import direction, paths outside the plan's editable fence, paired artifacts left behind, and the green retests the commit-time closure refusal will demand, with a recorded decision as the named escape hatch. Use before committing a multi-module edit. Not for answering who-calls questions ahead of an edit, and not for authorizing a push or release."
---

# Godmode Impact Gate

## Outcome

Before `git commit`, the staged edit's reach is scored against the
project's own graph and boundaries - how many dependents it leaves
unfollowed, whether it crosses the hooks/runtime import boundary, whether it
steps outside the declared fence or leaves a paired artifact behind - and
every finding is either fixed or accepted on the record through one named
escape hatch. The gate is advisory; the one refusal that is not (the
commit-time closure check) is satisfied by running the retests, never
waived.

## Use

- A multi-module edit is staged and about to be committed.
- A commit touches `hooks/` or `scripts/godmode_runtime/` and the import direction between them must hold.
- A plan declared an editable fence and the staged set may have stepped outside it.
- A crossing is intentional and should be accepted on the record rather than silently.

## Do Not Use

- Finding who calls or imports a module before planning an edit to it - that is `godmode-codegraph`.
- Previewing or authorizing a force push, tag, or release - that is `godmode-governance`.
- Diagnosing why a retest went red after an edit - that is `godmode-investigation`.

## Deterministic Execution Flow

1. **Open a session, then enumerate the staged work and its size pressure.** `godmode session open` (if none is open; steps 6 and 7 refuse without one), then `godmode scope --minimality` - lists what changed against the working tree and reports size pressure; it never blocks.
   - Fallback: outside a git repository it reports `verdict: unavailable`; name the paths explicitly in every later `--changed` instead.
2. **Prove the saved graph before trusting its fan-out.** `godmode atlas graph verify` - reports `verified: false` with a reason when no snapshot exists or it is stale.
   - Fallback: only then run `godmode atlas graph rebuild`, and repeat step 2.
3. **Score the fan-out.** `godmode atlas closure --changed <path> [<path> ...] --depth 2` - every dependent of a changed path that was not itself changed. `verdict: unfollowed-dependents` (exit 1) is the finding, not an error; the count of dependents is the fan-out score.
4. **Check the architectural boundary.** `godmode atlas --direction` - hooks import the runtime only through the declared surface, and the runtime never imports hooks; exit 1 names each crossing.
5. **Check the declared fence.** `godmode fence audit --changed <path> [<path> ...]` - changed paths outside the plan's editable set.
6. **Check paired artifacts.** `godmode precheck --about "commit <one-line summary>" --changed <path> [<path> ...]` - read `paired_artifacts.verdict`: an artifact declared to change together with a staged path that did not.
7. **Satisfy the commit-time closure refusal.** `godmode retest --run` - runs the tests that pin the changed paths and attests their exit code. The pre-commit closure check refuses a staged code path with no green retest newer than its last edit; it has no escape and none is sought here.
8. **Accept an intended crossing through the named escape hatch.** A fan-out, fence or boundary finding that is deliberate is recorded before the commit: `godmode remember --kind decision --subject "impact-accepted:<path>" --value "<why the crossing is intended and what bounds it>" --evidence seq:<the closure or audit record>`. Size growth past a recorded ceiling is accepted with `godmode minimality --accept-growth <section> --reason "<what the added surface bought>"`.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never trust a fan-out from an unverified graph; step 2 comes before step 3, and `rebuild` runs only after `verify` says so.
- Never commit with `--no-verify` to get past the closure refusal; run `godmode retest --run` instead.
- Never accept a crossing silently; the escape hatch is a recorded decision that names the path and the reason, or it is not accepted.
- Never edit the fence or the paired-artifact declarations to make a finding disappear; accept it through the escape hatch or fix the edit.
- Never turn this advisory gate into a blocker for a docs-only or fixture-only commit; the closure check exempts those, and so does this skill.

## Acceptance

- `godmode atlas closure` names every unfollowed dependent of the staged paths from a verified graph.
- Every boundary, fence or fan-out finding is either fixed or carries an `impact-accepted:` decision before the commit.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
