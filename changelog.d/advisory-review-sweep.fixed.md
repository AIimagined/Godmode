This repo's own charter advisory rules are fully reviewed, and the review
test is portable. 16 of 19 committed ADVISORY charter rules (added by the
capability-register/coverage/minimality/checklist docs) had never been run
through `charter --review-advisory`; each now carries a real, rule-specific
decision record (`charter-advisory-reviewed:<id>`) - most are documentary
sentence fragments or topic sentences the charter compiler's per-line
chunking produced (not imperative directives), a few describe behaviour
that is genuinely already mechanically enforced elsewhere
(`capabilities --reconcile`, `changelog check`) but not in a shape the
charter compiler's checkable-shape table recognises. One rule was
genuinely wrong rather than merely unreviewed:
`docs/RELEASE-CHECKLIST.md` read "Before this sprint's commits land",
contradicting the doc's own "Standing verification rows" framing by naming
one already-landed sprint - reworded to "this repository's commits" so the
checklist reads as reusable.

Separately, `tests/test_charter_checkability.py`'s
`AdvisoryReviewRepoTests` read this machine's live, gitignored archive
unconditionally and could never pass on a fresh clone or CI, where no
`charter-advisory-reviewed` decision exists yet. Restructured to the same
degrade pattern the role-doc and private-ledger tests already use: it
skips with an explicit message when the local archive holds no review
records, and asserts `advisory_unexplained == []` fully once real ones
exist.
