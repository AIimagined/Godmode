A claim about the outside world is now recognised without being declared. The
runtime already refused to record a verified claim about an external system
unless a primary source had been read, but that check only ran when the caller
passed the flag — so it protected whoever remembered they were talking about a
remote system, which is not the person who needs it. The seed case was an
assertion that a pinned action version did not exist: stated from recall,
wrong, and caught only because a human checked. No flag was passed, because it
did not feel like a claim about anything remote.

Detection is narrow on purpose, firing on third-party artefacts pinned at a
version and on assertions about what a released version does. A detector that
fired on ordinary local statements would teach the operator to route around it.

Fixing the detection exposed the gate behind it as unsatisfiable. It demanded a
`doc:` or `url:` citation and then rejected every one of them as unresolvable,
so a claim about the outside world could never be recorded as verified whatever
the author had actually read. A source outside the worktree now resolves as the
operator's declaration that they read it — nothing local can confirm that, and
confirming it over the network is not something this runtime does — and the
record names which citations were asserted rather than checked, so a later
reader sees the difference instead of one uniform "verified".

The seeded fuzz harness caught the first version of that change accepting a
citation of control characters and encoded traversal, which a declared source
reference must now not look like.
