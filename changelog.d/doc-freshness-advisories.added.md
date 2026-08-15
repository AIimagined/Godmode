Two docs-lint advisories, absorbed from two lessons (U-E11): `stale-open-marker`
flags a scanned doc line carrying an open-status marker (`pending`, a bare
to-do marker, `open item`, `not started`, `in progress` - a small closed
tuple, word-bounded) with no `YYYY-MM-DD` verification date on the same or an
adjacent line, exempt inside fenced code blocks. `title-collision` flags two or more LIVING docs
whose first heading normalizes to the same term set (via
`godmode_precheck._terms`, reused rather than duplicated) with neither
carrying a `supersedes`/`superseded by` pointer, naming every colliding path;
archive/changelog docs are exempt through the same `_HISTORICAL` pattern the
figure and self-pin checks already use.

Both ride `lint_docs`'s `prose_advisories` seam alongside the charter-prose
checks: `severity: "advisory"`, never joining `findings`/`high_severity`/
`verdict`, so neither can fail `docs --lint`.

Population sweep on this repository surfaced real, honest advisories rather
than a clean scan, all accepted rather than fixed (out of this unit's file
scope): twelve `stale-open-marker` hits - ten in historical prose
(`CHANGELOG.md`, `docs/releases/RELEASE_NOTES_v0.2.10.md` and `.../v0.2.11.md`)
or SKILL.md example/behavior text (`skills/godmode-repair/SKILL.md`,
`skills/godmode-continuity/SKILL.md`) using the marker words as vocabulary,
not as literal open items, and two self-referential ones right here in this
fragment's own description of the marker tuple; and one `title-collision`
group - `GODMODE.md`, `llms.txt`, `locales/hi/GODMODE.md`, and
`skills/godmode/SKILL.md` all title themselves plainly "Godmode" - a
translation, an SEO summary, and a skill entry point sharing one common
word, not a stale duplicate needing a supersedes pointer. `docs --lint`'s
blocking verdict on this repository remains `clean` (exit 0) either way,
since both checks are advisory only.
