The README and marketplace listing kit now say only what the product does
today, each claim paired with the command that reproduces it.

The prior README asserted "five skills" where six now ship, an "at-risk"
assessment verdict that this checkout currently reports as "workable," and
a "Hosts: 6" badge that flattened three live-tested plugin hosts and three
adapter-only hosts into one undifferentiated number. None of those were
caught by review because nothing re-ran them against the repository they
described.

The rewrite opens with the felt problem instead of a feature list, puts
observe mode ahead of any enforcement claim so a reader can watch what
Godmode would have caught before trusting it to block anything, and groups
the mechanisms (gate, verdicts, register, measurement, trust, run
governance) each behind its own verify-yourself command. Every number in
"The numbers" was run against this repository to write the section, and
the two that weren't (the pre-v0.2.11 gate latency figures) are labeled as
historical measurements with their release-note basis instead of being
re-asserted as current.

Host support is now stated in tiers instead of one combined claim: Claude
Code's gate and session hook run live every session this repository is
worked in; Codex and Grok ship the same plugin package and hooks
convention but are not independently live-probed under those hosts; the
three instruction-file adapters (OpenCode, Cursor, Gemini CLI) declare
`tool_call_interception` as `UNAVAILABLE` because none of them exposes a
pre-tool boundary. The platform note is explicit too: developed and tested
on Windows, where the Windows kill path for an overrun run is exercised
for real and the POSIX kill path (`os.killpg`) is pinned by a mocked unit
test, not live-probed on a POSIX host.

`docs/LISTING.md` is new: short and long descriptions, keywords, category,
and submission steps per marketplace (Claude, Codex, Grok), plus a
manifest audit that finds neither `.claude-plugin/plugin.json` nor
`.grok-plugin/plugin.json` carries any pointer to the shipped logo, and
that Codex has no `marketplace.json` where Claude and Grok both do. The
audit is read-only by design; the manifest edits it surfaces are a
follow-up task.

`tests/test_readme_commands.py` pins every fenced `godmode` invocation in
the README against the real CLI parser (`_build_parser`), the same
mechanism `tests/test_demo_doc.py` already runs against `docs/DEMO.md`. A
doc edit that renames or invents a subcommand fails this test, not a
reader's copy-paste.
