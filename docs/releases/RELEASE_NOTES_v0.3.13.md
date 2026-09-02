# Godmode v0.3.13

The delivery release: three fixes that were inside the v0.3.12 tag but never
reached installs (the marketplace snapshots a plugin at the first commit
carrying a new version string, so fix rounds landing after the bump are
invisible to it - the bump is now the final commit before the tag, by recorded
lesson), plus one caught minutes after 0.3.12 installed.

A checkpoint whose summary overflows the 200-char subject slot records anyway:
the subject becomes a label derived from the opening words and the full
summary rides in the record data. `version --reconcile` knows the pre-tag
release window: every source surface unanimous and strictly ahead of the tag
reads `staged`, because CI must pass before the tag moves. The listing
description names the evidence ledger and hook-enforced gates on every host
surface, from its one source. And the package compiles with zero
SyntaxWarnings, pinned by a test that compiles every shipped source with
warnings as errors - 0.3.12 printed one on first import.

## Verifying

- `python -m unittest discover -s tests` — the full suite.
- `godmode checkpoint "<any prose, however long>" --status progress` — records
  with a derived label; the full text is in the record's data.
- `python -W error::SyntaxWarning -c "import godmode_runtime"` from the
  scripts directory — imports silently.
- `godmode version --reconcile` — `agreed` at a tag, `staged` in the lawful
  pre-tag window, drift only when surfaces disagree among themselves.
