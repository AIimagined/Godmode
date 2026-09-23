# Purpose

This skill exists so a spec, its plan, its approval, its bound
implementation, and its status stay one linked record a later session can
resume - instead of divergent drafts of the same document that only get
reconciled by hand, after the fact, once someone notices they disagree.

## Gap evidence

- seq:12495 / seq:12496 - the same spec was measured at 419 lines in one
  claim, then 432 lines a moment later in the same session, with the second
  record needing to say in prose that it "supersedes" the first because an
  acceptance-clause edit had already landed between the two measurements.
  Two drafts of the same document, reconciled only because someone happened
  to notice the number had moved and wrote a correction claim by hand.
- seq:12186 - four defects a review had already found in the v0.3.26 plan
  still had to be independently reconfirmed in this checkout before they
  counted (`classify_action` takes `operation` not `command`; a test
  pattern reporting no tests ran; a hook wired through the wrong manifest
  entry; an event choice missing from the session hook). The review's
  findings were not carried forward as part of the plan's own linked
  record, so the same ground was walked twice.

## Promise

A task's spec and plan move through `specify`, `start`, `check`, `approve`,
`bind`, and `status` as one linked chain: a divergent draft is superseded
with a cited reason instead of a hand-written correction, and a review's
findings are read back from the plan's own record instead of being
reconfirmed from scratch.

Future edits to this skill append their own seq: citation above.
