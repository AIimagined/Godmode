# Purpose

This skill exists so the checks CI will run have already run locally, in
CI's order and on the tree that will be pushed, instead of a half-hour suite
running five times before a seconds-long gate refuses the push.

## Gap evidence

- Five push attempts each ran the full pre-push suite before a fast gate
  refused them on a stale table, a swallow ceiling and a fragment check.
- A red CI job could not be reproduced locally because nothing named the
  shard, the command or the tree the job had validated.
- The version stated by the plugin manifests, the runtime and the notes
  drifted apart between a tag and its release.

## Promise

Cheap gates first, the suite after, on HEAD or a named snapshot, with the
install self-test, the control grid, the version and the hook proof
refreshed before a push, and a red leg reproducible by its shard.

Future edits to this skill append their own plain-language evidence above.
