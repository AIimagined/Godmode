# Purpose

This skill exists so a release's notes are drafted from what the changelog
fragments and commits actually earned, and checked before the release ships
- instead of being written from memory at cut time and never checked at all.

## Gap evidence

- A changelog-fragment gate is exercised release after release, yet nothing
  names when to run it, in what order, or what to do with a
  missing-fragment result.
- The same three-step sequence — check the fragments, merge them, then
  build and check the notes — is repeated by hand for every release
  instead of being named once.
- Release notes have been cut from memory, with the same fragment-then-merge
  sequence redone each time rather than run from one named flow.

## Promise

Cutting a release's notes means running the fragment gate, merging what it
found into the changelog, and building and checking the resulting notes
against the required shape - in that order, every time, with the exact
verb that already does each step.

Future edits to this skill append their own plain-language evidence above.
