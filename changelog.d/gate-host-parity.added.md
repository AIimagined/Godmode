`hooks/gate_table.json` is now generated, not hand-built: a new
`scripts/dev/build_decision_table.py` reads `godmode_sentinel.py`'s own vocab
tables - `DB_CLIENTS`, `_FIND_MUTATION`'s compiled flag alternation,
`_OUTPUT_FLAGS_BY_HEAD`'s git write-flag entry - and re-verifies every floor
phrase, read head, git-ask/git-refuse candidate, and mutation head against
`classify_action` at generation time, so a sentinel change that moves one of
them to a different tier breaks the build instead of shipping a table that
silently disagrees with the classifier it was built from. `generated_from`
is a 12-hex sha256 prefix of `godmode_sentinel.py`'s own bytes;
`tests/test_gate_parity.py` asserts regenerating the table (`--stdout`)
reproduces the checked-in file exactly, plus a plant test proving that
check would actually fail on a dropped floor entry.

The provisional table's one deliberate omission is reversed: `tr` was left
off the floor because the sentinel did not yet classify a bare `tr` as
read-only when that fixture was hand-built. Re-verified live against
today's sentinel (`classify_action("tr a b")` is R0), `tr` now belongs on
the floor and the fast gate fast-allows it like every other read head
(`tests/test_gate_fast.py::KnownShapes::test_bare_tr_is_on_the_floor`).

`git_ask`/`git_refuse` and `mutation_heads` are populated for the first
time - curated candidate lists, each classified through `classify_action` at
build time and asserted into the bucket its own verdict names, rather than
retyped by hand disconnected from the classifier.

Deferred-minor fix, red-first: `hooks/godmode_gate_fast.py`'s `flag_denylist`
matching compared each trailing token to a denylisted flag by exact string
(after stripping any `=value`), which caught `-o /tmp/x` and `-o=x` but not
git's own glued short-flag spelling - `git log -o/tmp/x`, one token, no
separator at all - fast-allowing a real, unrecorded write. A short
(single-dash, single-character) denylisted flag is now prefix-matched
against each trailing token as well as compared for equality; a long flag
(`--output`) is never prefix-matched, since gluing a value onto it with no
`=` is not a form git itself accepts.
