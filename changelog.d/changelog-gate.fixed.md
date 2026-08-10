The changelog gate refused a release for spending its own fragments.

A fragment is a staging area. The artifact it exists to produce is a CHANGELOG
entry, and `changelog merge` consumes every fragment to write one. So a commit
that merges fragments and ships code in the same breath has changed code, has
recorded the note the gate protects, and carries no fragment — because it spent
them. The gate read that as an unnoted change and failed the release.

It was right about the fragments and wrong about the question. What it exists to
guarantee is that a change is written down, not that a particular staging file
survives to be counted.

Splitting a release into two commits avoids this, and this repository had always
done that by habit. Habit is not a check: a gate that passes only when somebody
remembers the customary commit order refuses a correct release the first time
somebody does it in one, and does so in CI, after the push.

A diff that adds entries to CHANGELOG.md now satisfies the gate. The count is of
*net* bullets and version headings, not added ones — an edited bullet appears in
a diff as one addition and one deletion, so counting additions alone would read a
corrected typo in a released entry as a note for today's code, leaving the gate
on in name and off in effect. A code change with no note anywhere is refused
exactly as before.

The report now names which of the two answers let it through, so a reader seeing
`satisfied` beside an empty fragment list does not have to guess why.
