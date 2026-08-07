The gate is tested the way the host drives it, and three defects it had been
hiding are fixed.

Every file edit was refused. The allowance for ordinary working files tested
whether a path looked absolute, which read as a reasonable proxy for "outside
the tree" and is not one: the host sends an absolute `file_path` for every
`Write` and `Edit`, so the allowance could never fire and no edit was ever
permitted in a session. Containment is now measured against the project root,
which also subsumes traversal — a path normalising outside the tree fails
containment rather than needing its own rule — while `.git/`, `.env`, keys and
certificates stay protected wherever they sit.

Shell control flow was refused. `for`, `do` and `done` are not commands, so
they matched nothing and failed closed, and an ordinary loop over a few files
was denied. Control flow is now recognised as structure: a keyword is stripped
and the remainder judged, exactly as an assignment prefix is, so `do rm -rf x`
stays protected and a loop body is still classified on its own.

The refusal message named a remedy that did not exist. It asked for a one-use
capability, but no host tool call carries a field a capability could travel in,
so the broker was unreachable from the hook and the operator was sent looking
for a token they had no way to supply. It now names what actually unblocks the
call, and says plainly that there is no in-session approval — which is also the
reason this gate must be conservative about what it stops, since every refusal
is total.

All three were invisible to the suite for one reason: the tests fed the
classifier operation strings written by hand, one layer below the boundary
where the host's payload arrives. A real `PreToolUse` payload now goes into the
hook process and the decision comes back out, so a case can only pass by
working the way it will work in a session.
