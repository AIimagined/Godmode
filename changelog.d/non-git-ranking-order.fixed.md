Non-git context ranking no longer depends on copy/checkout timing, within
the non-git mode. `godmode_corpus.rank`'s freshness ordering fell back to
raw filesystem mtime for a project with no `.git` directory - mtime there
is assigned by whatever copied or checked the files out, not by their
content, so two copies of an identical non-git project could disagree on
file order purely from copy timing (`tests/test_gate_falsifiability`'s own
then-git-stripped project copy surfaced a `ranking-changed` verdict against
the pinned `evals/fixtures/ranking.json` snapshot, which was investigated
further and turned out to be a *cross-mode* mismatch - see below - not this
within-mode one). Non-git freshness ordering now degrades to a
deterministic path sort - the same secondary key the git-log fix already
uses for ties - instead of comparing mtime magnitudes across files; mtime
itself remains the freshness value `_freshness_stamp` returns for a
non-git/untracked path (unchanged). A new test constructs two non-git
copies with deliberately shuffled mtimes and asserts identical ranking.

Scope: this closes copy/checkout-timing drift *within* the non-git mode
only. Path sort and the companion git-log commit-time instrument (see
`ranking-checkout-order.fixed.md`) are not promised to agree with each
other on tie order for the same content, so a ranking computed without
`.git` is not guaranteed to match one computed with it. A snapshot must be
generated and compared in the same mode it will be evaluated in - see
`godmode_corpus.rank`'s docstring for the cross-mode boundary. The
falsifiability harness now keeps `.git` in its project copy so it evaluates
in the same mode `evals/fixtures/ranking.json` was generated in.
