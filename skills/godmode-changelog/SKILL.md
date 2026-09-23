---
name: godmode-changelog
description: Draft and verify release-notes from local commits and changelog fragments. Use when checking that every user-visible update carries a fragment, merging fragments for a version, or building and checking the release-notes for that version. Not for a one-line note authored by hand and not for a code-review summary of a single file.
---

# Godmode Changelog

## Outcome

A release note written by hand at cut time is written from memory, and a commit
that ships user-visible behavior with no fragment is a note nobody will ever
write. This skill runs the fragment check, spends the fragments into the
changelog for the version being cut, then builds and checks the notes so the
release carries the note that behavior actually earned - never a narration of
the work that produced it.

## Use

- Confirm every user-visible commit since the base ref carries a `changelog.d/*.md` fragment before a release is cut.
- Merge the accumulated fragments into `CHANGELOG.md` under the version being released.
- Build that version's release notes from the merged changelog section, and check the built notes hold the required shape.
- A release is being prepared and the changelog gate, the merge, or the notes have not been run yet.

## Do not use

- For a one-off commit message on a single change - that is normal commit authoring, not a release note.
- To summarize what one file does for a code-review comment.
- To invent release-note prose that no changelog fragment or commit backs; the notes are built from what was merged, not composed from scratch.

## Deterministic Execution Flow

1. **Check the fragment gate before anything else.**
   ```
   godmode changelog check --base <last-release-ref>
   ```
   Read the result's `verdict`. `satisfied` means every user-visible change already carries a fragment, or the changelog gained an entry directly; `missing-fragment` names the exact paths under `changes_needing_note` still uncovered.

2. **Fallback for a `missing-fragment` verdict:** add one fragment per uncovered user-visible change:
   ```
   changelog.d/<slug>.<added|changed|fixed|removed|deprecated|security>.md
   ```
   containing one sentence describing the user-visible effect (not the implementation). Re-run step 1 until `satisfied` is true. Never merge or build notes over an unsatisfied gate.

3. **Confirm the release has no other missing paired artifact** before cutting:
   ```
   godmode precheck --about "cut release <version>"
   ```

4. **Spend the fragments into the changelog** for the version being released:
   ```
   godmode changelog merge --set-version <version> [--date <YYYY-MM-DD>]
   ```
   This folds every fragment under `changelog.d/` into a `## [<version>]` section in `CHANGELOG.md` and removes the spent fragments. A fragment that arrives after a first merge folds into that same section on the next run rather than opening a second heading for the version; running it again with nothing left under `changelog.d/` has nothing to spend and refuses.

5. **Build the release notes** from that merged section:
   ```
   godmode release-notes build <version>
   ```
   Fallback: if a note for `<version>` already exists and needs regenerating, pass `--force`.

6. **Check the built notes hold the required shape:**
   ```
   godmode release-notes check <version>
   ```
   The shape is: present, every changelog entry for the version covered, no empty section, no process narration, and a `Verifying` section a reader can actually run.

7. **Fallback for a failed shape check:** fix the source, not the built file - add the missing piece to the relevant `changelog.d/*.md` fragment or the merged `CHANGELOG.md` section the check named, then rebuild with `--force`:
   ```
   godmode release-notes build <version> --force
   ```
   and re-run step 6. A direct hand edit of the generated release-notes file is a last resort only, and only when it is recorded as one - the deterministic path is fix the source, rebuild, re-check.

## Must not

- Must not run `changelog merge` or `release-notes build` while `changelog check` still reports `missing-fragment`; the notes would omit exactly the change that triggered the check.
- Must not write release-note prose that names no changelog entry or commit behind it.
- Must not edit `release-notes check`'s required-shape rule to accommodate a specific note instead of fixing the note.
- Must not treat `merge` as safe to re-run out of caution; with nothing left under `changelog.d/` it has nothing to spend and refuses. Only run it again when a genuinely new fragment has arrived for the same still-open version.
- Must not bypass a failing changelog or notes check with `--no-verify` on the commit that cuts the release; a blocked gate is fixed at its source, not skipped past.
- Must not hand-edit a generated release-notes file as the default fix for a failed shape check; fix the fragment or changelog section and rebuild with `--force` instead, and treat a hand edit as an explicitly-recorded exception, never the routine path.

## Completion

Report the fragment-check verdict, the version merged, and the release-notes check's final verdict. A release cut without all three run in order is not proof the changelog is honest - it is a note that was never checked.
