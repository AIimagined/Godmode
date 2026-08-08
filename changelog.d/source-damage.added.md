`integrity` now checks that a change arrived intact before asking what it means.

The nine existing monitors watch what a diff does to the meaning of the tests.
These watch something earlier and dumber: whether the write landed as written. A
file this change touched must still parse, and must not carry control bytes no
editor produces.

Both come from real damage. A scripted edit reported success while the shell
halved its backslashes, turning a word boundary into a literal backspace byte —
so every pattern in that file silently matched nothing, and the fault was found
by a test failing later rather than by the write. The same shell mangled two
more edits in the same session, the same way, each time reporting success.

Only files the diff touched are examined, because a pre-existing oddity
elsewhere is not this pass's finding and reporting it trains the reader to skip
the whole report. Both findings block: a file that no longer parses cannot be
reasoned about by any monitor above it, and a corrupted write has already failed
whether or not anyone has noticed yet.
