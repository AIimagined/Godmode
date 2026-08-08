The last five tooling failures, each in the form that is actually checkable.

A taxonomy of real coding-agent incidents gives the agent's own tooling its own
section, and five of its entries describe a discipline rather than an artefact.
Each has a narrower form a runtime can see, and the narrow form is worth more
than a rule nothing checks.

An anchored edit that matched nothing reports success and leaves the file as it
was, so a file that appears in a change but differs only in whitespace is
reported. A dependency or lockfile change means any process started before it is
serving the old tree, so a later run is evidence about that tree rather than
this one — reported and not blocked, because editing a lockfile is ordinary and
a gate that stops it is a gate that gets switched off.

A status about a system this runtime cannot see — a build that passed, a release
that is published, a branch that was merged — is now recognised as an external
claim, and needs a source read this session rather than a memory of one. That
came from stating release state here from seventeen-hour-old recall while the
API sat one call away, already used minutes earlier for something else.

`capabilities --usage` reports corrections the runtime made that nobody wrote
down. A downgraded claim is the one correction this runtime can see for itself:
the author asserted something and the record refused it. If that happened and no
lesson exists, the correction survives only in whatever was said at the time,
which is exactly how the same mistake returns.

Three more verifications that pass while proving less than a reader will assume.

A check that changed the working tree while running reports on a tree that no
longer exists — the run is real, the subject moved underneath it. That is
recorded on the attestation rather than refused, because a check that writes is
sometimes legitimate and refusing every one is how a gate gets switched off;
what must not happen is the result being read later as a statement about the
tree that produced it.

A guard whose name promises a universal and whose body asserts one case is
reported. The name is what a later reader trusts and the assertion is what
holds, so either the set gets covered or the name gets narrowed. A body that
compares a whole collection satisfies it without a loop, since demanding an
explicit loop would report the strongest form of an assertion as the weakest.
The quantifier is only recognised at the front of the name, where it binds the
subject: matched anywhere it flagged four of this project's own tests for
ordinary mid-sentence English, which is the rate at which a monitor starts
being skipped.

A test that writes to a path which is not temporary is reported. A mistake
ledger records a write-endpoint smoke test aimed at a live project id, which
returned success and destroyed the draft it was verifying.
