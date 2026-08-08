Quick start described a CLI; the product is three hooks and five skills.

A reader's first experience is a continuity brief loaded at session start, a
refusal at the pre-tool boundary, and skills routing by the shape of the work.
The section that introduces the product opened with three interpreter
invocations and a command count, which reads as a large manual CLI and is the
opposite of what installing it feels like. It now leads with what happens
without being asked, and names the three ways to answer a refusal — including
staging a capability, which is the one that had gone unmentioned everywhere.

Two stale figures went with it, and both were inside fenced code blocks:
`80 commands` when there are 82, and a CI snippet pinning
`AIimagined/Godmode@v0.2.0` through seven releases.

The count is now gone rather than corrected. Only 82 of 120 `add_parser` calls
are top-level commands, so there is no exact local answer, and the linter's own
guidance is to stop stating a number that changes rather than to police it —
the same reason `hosts` has never been checked.

The pin is checkable, because the running version is an exact answer, so
`stale-self-pin` now reports any snippet pinning a version of this project that
is no longer current. It reads inside fenced blocks deliberately: the figure
check skips them, since a number in a code sample is usually an argument, which
left every install snippet — the one thing a reader copies verbatim — in the
only place no check looked. Release notes are exempt, because a document about
v0.2.4 should say v0.2.4.
