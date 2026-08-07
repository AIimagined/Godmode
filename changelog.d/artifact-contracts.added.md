The document linter now checks both directions. Every check it shipped with was
negative — rationale leaks, unverifiable claims, counterfactuals, internal
notes, unfinished markers, local paths — and all six ask whether a document
contains something it should not. None asked whether it contains something it
must, so a document that silently omitted a required section was reported
clean. That is the most flattering possible failure mode: in a one-sided
linter every false negative makes the output look better than it is, which is
the wrong direction for a tool whose purpose is to stop overclaiming.

A project may now declare artifact contracts in `.godmode-docslint.json`,
mapping a path pattern to the sections a document must carry. Both halves are
checked: `missing-section` when a required heading is absent, and
`empty-section` when one is present with nothing under it — a heading with no
content satisfies a word-search and satisfies nobody reading it. A mistyped
contract is reported rather than dropped, since an operator who believes their
documents are under a check that never ran is worse off than one who declared
nothing, and the report states which contracts were applied so it cannot be
read as contract-checked when none was declared.

Applying the first contract to this project's own release notes immediately
found one shipped without any verification instructions.
