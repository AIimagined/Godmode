Merging a version twice no longer produces that version twice. A release is
rarely cut in one pass — a fragment arrives after the first merge, usually
because a gate caught something, which is the system working — and the second
merge inserted a second heading for the same version above the first rather
than folding into it. Entries already recorded are kept verbatim, so a re-merge
never reformats prose that has already been published.

One such duplicate shipped in a tagged release while 464 tests, thirteen gates,
the changelog check and the document linter all reported green, because nothing
had ever asked whether a version appears once. The repository's own changelog
is now asserted to carry each version exactly once.
