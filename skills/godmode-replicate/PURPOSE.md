# Purpose

This skill exists so a host or platform row is earned by a replication
pinned with a test that can fail - never declared `unverifiable` while the
reference that would settle it sits unread.

## Gap evidence

- Compatibility with several hosts was declared unverifiable while
  reference implementations for each of those hosts already existed and
  sat unopened.
- A way to prove a reference had actually been read, rather than skimmed
  from its landing page, existed separately from the workflow that would
  use it before replicating anything.
- A privacy scan of the tracked tree existed as a standalone check,
  disconnected from the point in a replication where it actually needs to
  run — right before the change is committed.

## Promise

A replication starts from receipted source reads, is pinned by a test
proven able to fail, is cited on its row with both the receipt and the
test, and is scrubbed before it is committed.

Future edits to this skill append their own plain-language evidence above.
