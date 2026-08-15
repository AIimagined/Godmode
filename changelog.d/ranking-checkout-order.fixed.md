Context ranking no longer depends on checkout order. `godmode_corpus.rank`'s
freshness tie-break read filesystem mtime, which `git clone`/`git checkout`
do not preserve from commit time - two clones of the identical commit could
disagree on file order, and this task's own `evals/fixtures/ranking.json`
update exposed the fragility (a live fresh-clone reproduction found
`ranking-changed` even with a charter-stable snapshot). Freshness for a
git-tracked project now reads the file's last commit timestamp via `git
log`, which is part of the commit object every clone already has and so
agrees regardless of checkout order; non-git projects are unaffected
(mtime remains correct there, since there is no separate checkout step to
reorder against). A new test constructs a git fixture where on-disk mtime
order is the exact opposite of commit order and asserts ranking is
unaffected.
