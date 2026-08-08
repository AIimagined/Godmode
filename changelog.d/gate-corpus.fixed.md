The action gate, corrected against the commands this project actually ran.

Its allowances were written from memory, and classifying 1,419 real commands
recovered from the project's own transcripts showed 506 refused - 74 of them
naming no mutation at all. Twelve defects were behind that, and one ran the
other way: `echo pwned > ~/.bashrc` was **permitted**, because `~` is not
expanded here, so the target was joined to the project root and passed
containment. An unexpanded path is no longer treated as a path.

Also corrected: `git -C path <read>` and the other global options; the git read
subcommands (`rev-list`, `ls-files`, `describe`, `blame`, `cat-file` and nine
more); `merge-base` read as `merge` and `commit-tree` read as `commit`, the
second of which admitted plumbing that writes; `> /dev/null` treated as a file
write; `--help` and `--version` classified by the operation they describe;
`gh` read subcommands, with `gh api` judged on its flags rather than its noun;
PowerShell literal assignments; `export`/`unset` of names that do not decide
what runs; and a segmenter that split inside an escaped quote, reporting a
`grep` as a mutation because its pattern contained one.

Each widened allowance ships with the mutation it must still refuse.
