# Godmode v0.3.2

The first telling is enough.

v0.3.1 shipped the hooks that run where they are loaded; the day after,
three hosts ran them live and wrote back what they found. This release is
that feedback landed: thirteen fragments, every one traceable to a field
report from a real session on Claude Code, Codex, Grok, or OpenCode.

## The counter that gates, the install that seeds, the claim that meets its pin

The required-sources counter stopped being decoration in 0.3.1; now it
gates. Once per session, the first pre-tool call that would otherwise be
allowed while a bound authority document is uncited becomes an ask naming
the unread files - with two escapes, both on the record: cite the document
as you read it, or exempt it with a `sources-exemption:<path>` decision.
`adopt --from-docs` answers the late install: one counts-only adoption
record per bound document - headings, bullets, lines, a digest, `file:`
evidence - so a mature repo starts with a populated brief instead of a
blank one. And a state-is-a-gap claim is now checked against the tests
that name its surface and the lessons ledger: an uncited pin downgrades
the claim to hypothesis, naming the pin whose provenance answers it.

## A standing instruction lands on first telling

An operator stated a rule once; the agent stored it where this runtime
cannot read, and dropped it three reports later. The correction detector
only ever caught the second telling - the operator having to say it again.
An instruction-shaped prompt (always, never, from now on, every time) now
writes a law candidate on the FIRST telling, keywords and digest only,
and its cluster promotes after one session where an inferred correction
still climbs the three-session ladder: an explicit directive is stronger
evidence than an inferred one, and the guard is still reviewed prose at
promotion time.

## The tamper alarm looks twice

Twice in one day, in two different projects, a reader holding a pre-append
listing saw the chain anchor count one record more than its stale view and
called it truncation - a false alarm whose printed remedy (`db
--reanchor`) would be destructive to run on a phantom. The check now
re-reads fresh disk state once, after a short beat, before it fires; a
real truncation still raises. Beside it, `doctor --deep` names every
cached godmode install whose version differs from the running one, because
stale caches share the archive and race its chain.

## Each host, by its own contract

- **Grok** honored a live deny in a real session and re-probed to HARD -
  and its own read-only builtins (`get_command_or_subagent_output`,
  `read_file`, `grep`, `spawn_subagent`) now classify read-kind and pass
  by construction, where before the gate fail-closed on them and blocked
  ordinary work. Unknown tool names still fail closed.
- **Codex** (CLI 0.150.1) ignores plugin-bundled hook manifests entirely -
  its own bundled plugins' hooks show `Installed: 0` - so `godmode hooks
  wire` writes the project-level `.codex/hooks.json` it does load,
  projecting the shared hooks into absolute commands (`py -3` on Windows).
  The operator reviews and trusts each command inside `codex`; verified
  live: PreToolUse and SessionStart, Installed and Active.
- **OpenCode**: `hooks wire --host opencode` installs the Bun shim into
  the project's `.opencode/plugins/` and names the exact
  `GODMODE_PLUGIN_ROOT` to export - the manual copy step a live OpenCode
  review called out is gone. Interception stays SOFT until a live block is
  chronicled.
- The shared PreToolUse matcher ships its dotted tool name regex-escaped
  (`functions\.exec`), and PostToolUse also hears the lowercase `write`
  and `search_replace`.
- A positively identified read-kind tool is allowed by construction at the
  pre-tool boundary, on every host adapter.

## Also

`context why --about <symbol>` carries a guards section naming the tests
that mention the symbol, so a gap claim meets its pin at design time -
the same session that asked for it had reversed a finding only by
hand-reading the test file this now surfaces.

## Verifying

- `python -m unittest discover -s tests` - run in four shards
  (`scripts/dev/run-suite.ps1`); every suite touched by this release ran
  green at the release commit.
- `godmode bindings` - every generated manifest current, 0 drifted.
- `godmode version --reconcile` - every surface agrees.
- `godmode changelog check` - satisfied; thirteen fragments folded.
- `python -m unittest tests.test_s6_field_gaps tests.test_sources_gate` -
  the field-gap closures, pinned.
