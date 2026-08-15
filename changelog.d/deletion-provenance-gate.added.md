Added a provenance-before-deletion gate (B3-6, PARTIAL-P1).

`godmode_removal.py` already records *why* something was deleted, after the
fact. `godmode_fence.deletion_verdict` is the mirror: *before* a deletion the
fence would otherwise allow - an `rm` or archive-move of a tracked file -
it asks whether a pre-check is on record.

Requirement-driven like B3-5: with no policy declaration it stays advisory,
recording what a pre-check would have covered and never blocking. Once
`.godmode-authorization-policy.json` declares `deletion_provenance_gate`,
the file's deletion is refused until `godmode fence delete-precheck --path
<p> --history-read "..." --sole-carrier "..."` is on record - reusing C-16's
reverse-impact traversal (`atlas.build(project).affected(path)`) rather than
rebuilding it, so the record carries what traversal actually found.

A new `.godmode-pins.json` names files that stay denied for deletion
regardless of policy or attestation - the pin store outranks everything
else this gate checks. Deleting an untracked scratch file is unaffected
either way: nothing about it carries a provenance obligation to check.
