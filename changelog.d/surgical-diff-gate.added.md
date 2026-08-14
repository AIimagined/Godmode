Surgical-diff completion gate (U-B1), extending the existing scope fence
rather than adding a second one: `fence audit --complete` parses `git diff
--unified=0 HEAD` into hunks - stdlib text, no dependency on a diff library -
and partitions them by the same `fence_verdict` a plan's editable set already
answers with, so three questions get asked of one parse instead of one.

A hunk that adds or changes lines in a file outside the declared set is an
`out-of-fence-hunk` finding naming the file and how many hunks landed there.
A hunk that only removes lines in such a file is told apart as
`unauthorized-deletion` - pre-existing code outside the plan's own scope is
not the plan's to remove, whatever the reason, and the remedy says so:
mention, don't delete. A deletion inside a file the plan does own passes
either way. And every added line, in any file, is checked against a small
default instrumentation-tag tuple (`[DEBUG-` to start) for an
`instrumentation-residue` finding naming the exact `file:line` - the one
check here that is not fence-scoped at all, because a stray trace print left
in a change claimed complete is not made acceptable by landing somewhere the
plan was allowed to touch.

Undeclared still means unenforced: with no approved plan's editable set to
check a hunk against, the fence-shaped findings stay silent, the same
fail-open contract `fence_verdict` already keeps for every project that
predates this gate. A plan extends the tag tuple through the same editable
field a fence already reads, by writing `tag:<pattern>` alongside its globs -
one declaration, not a second config surface next to it.
