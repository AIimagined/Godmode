Non-git context ranking no longer depends on copy/checkout timing.
`godmode_corpus.rank`'s freshness ordering fell back to raw filesystem mtime
for a project with no `.git` directory - mtime there is assigned by
whatever copied or checked the files out, not by their content, so two
copies of an identical non-git project could disagree on file order purely
from copy timing (`tests/test_gate_falsifiability`'s own git-stripped
project copy reproduced it as a real `ranking-changed` verdict against the
pinned `evals/fixtures/ranking.json` snapshot). Non-git freshness ordering
now degrades to a deterministic path sort - the same secondary key the
git-log fix already uses for ties - instead of comparing mtime magnitudes
across files; mtime itself remains the freshness value `_freshness_stamp`
returns for a non-git/untracked path (unchanged). A new test constructs two
non-git copies with deliberately shuffled mtimes and asserts identical
ranking.
