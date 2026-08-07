`godmode fuzz` feeds seeded garbage — unicode, nulls, separators, quotes,
comment markers, encodings, lengths — to the command classifier, path
containment, migration review, citation binding, and every config reader, and
asserts the properties that must hold for any input. Findings carry the seed
and case index so a failure replays instead of being hunted. Its first run
found four config readers that crashed with `AttributeError` on a file
containing `null`; they now degrade to defaults, and 2,500 fuzzed cases across
five seeds report fail-closed.
