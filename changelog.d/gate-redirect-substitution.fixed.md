Four more refusals of ordinary shell work, all found by using the released
build rather than by testing it.

An input redirect was classified as a write. `wc -l < README.md` reads a file
and writes nothing; the two characters were grouped only because they look
symmetrical. Reading from a file is a read.

`2>&1` was split at the ampersand. Making a bare `&` a separator so that
`ls & rm` could not launder was correct, but in `2>&1` the ampersand
duplicates a file descriptor and is part of one token — the split left a bare
`1` behind, which classified as an unknown mutation and refused the whole
command. The separator now ignores an ampersand that follows a redirect.

Every command substitution was refused on sight. That held the line against
`ls $(curl …)`, and denied `echo $(ls)` along with it, which runs nothing the
classifier could not already see. What a substitution runs is now extracted and
classified alongside the line containing it, so the laundering is stopped just
as firmly and nothing legitimate is lost. `${VAR}` is expansion rather than
execution and was never this.

An output redirect inside the working tree was refused while the declared
`Edit` of the same path was permitted. That gated the honest form and not the
other, which is all cost and no cover. A redirect is now judged by where it
lands, exactly as an edit is: inside the tree it is ordinary work, and outside
it, or into `.git/`, `.env` or a key, it is protected.
