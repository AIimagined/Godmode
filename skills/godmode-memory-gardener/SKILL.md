---
name: godmode-memory-gardener
description: "Garden the continuity archive at session close or idle time: tell the session as dated prose, list near-duplicate or contradicting lessons and decisions, preview which old episodes expire into the cold tier, supersede a duplicate, and cluster correction candidates for a promotion that cites its rationale. Use when lessons pile up duplicated, stale records crowd the brief, or a candidate cluster is ripe to promote. Not for resuming work at session start, and not for scrubbing a secret."
---

# Godmode Memory Gardener

## Outcome

The archive a later session inherits is pruned by rule, not by feel: the
session is told as dated prose, duplicates and contradictions are named and
superseded on the record, expiry is previewed before it runs, and a lesson
graduates only through a promotion that cites its evidence and an approval
from a second actor.

## Use

- A session is closing (or idle) and its episodes should be summarised before the next one starts.
- Lessons or decisions have piled up near-duplicated or contradicting one another.
- Old episodes crowd the brief and the forgetting pass has not run in a while.
- A cluster of correction candidates has recurred enough to promote, and the promotion needs a cited rationale.

## Do Not Use

- Resuming work at the start of a session, or rebuilding a lost context brief - that is `godmode-continuity`.
- Erasing a leaked credential from an archived record - that is `expunge`, previewed through `godmode-governance`.
- Following the compiled code of law before a new task - that is `godmode-code-of-law`.

## Deterministic Execution Flow

1. **Tell the session first.** `godmode digest --since <first seq of this session>` - the archive told as dated prose, assembled verbatim from record fields; it writes nothing. Everything after this step is judged against what actually happened, not against memory of it.
2. **List what duplicates or contradicts.** `godmode hygiene --cap 80` - near-duplicate and contradicting lessons and decisions as a review list; it proposes, never retires.
3. **Name carried obligations a later handoff made moot.** `godmode checkpoint --review` - reports; it closes nothing.
4. **Preview expiry before it runs.** `godmode forget --dry-run` - performs every read a real pass would and records nothing: which episodes would move to the cold tier, which supersession chains exist, which same-subject values contradict. A record cited by a live claim, a checkpoint, a law guard or a pin never expires.
   - Only after reading the preview, run the real pass: `godmode forget`. A preview that names a record you still need means fix the citation first, never skip the preview.
5. **Supersede a duplicate on the record.** `godmode remember --kind <same kind> --subject "<subject>" --value "<the merged value>" --supersedes <older seq>` - same kind only, and never for an incident or pattern (they carry their own evolution). The older record stays in the chain; readers stop treating it as current.
6. **Cluster promotion candidates.** `godmode law candidates` - correction candidates clustered by keyword, with recurrence counts across sessions.
7. **Promote with a cited rationale.** `godmode lessons promote <lesson seq> --cite seq:<evidence> --rerun-hash <sha256 of a held-out re-run>` - refused naming any missing structured field.
   - The approval is a different actor's pass: `godmode lessons approve <promotion seq> --rerun-hash <sha256 of that checker's own re-run>`, refused when the approver is the promoter or the re-run hash repeats the promotion's own.
8. **Close the loop.** `godmode checkpoint --summary "<what was gardened>" --status "<state left>" --next "<next action>" --evidence seq:<digest start>` - the next session reads this instead of re-deriving the pass.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never run `godmode forget` before `godmode forget --dry-run` in the same pass; an expiry you did not preview is an expiry you cannot explain.
- Never delete, move or hand-edit a file under the archive's state directory; supersede on the record instead, so the chain stays verifiable.
- Never approve your own promotion; the approval must come from a second actor with its own re-run.
- Never use `expunge` to tidy a duplicate; it exists for leaked secrets and leaves a tombstone.
- Never supersede across kinds, or supersede an incident or pattern; instead retire the stale record within its own kind, and leave incidents and patterns as history.

## Acceptance

- `godmode forget --dry-run` names what a real pass would expire, and the archive's record count is unchanged by it.
- A duplicate is superseded with `--supersedes`, and a promotion carries a cite and a second actor's approval.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
