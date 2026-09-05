# Godmode v0.3.19

The field-report release. Five reports arrived in one day - a field walk
of the installed build, then Grok on Windows, Codex, Antigravity, and a
second Claude session - and every finding in them ships here. Nothing
was parked.

## The gate was off in two places nobody could see

**Grok on Windows.** Grok hands a plugin hook's command string to
PowerShell and rewrites known `$VAR` refs to `$env:VAR`. The shipped
quoted-path shape was a ParserError there, so every hook fail-opened and
`git push --force` was not stopped by Godmode on that host. The fix was
pinned live rather than reasoned: a throwaway Grok session on the same
machine tried a dozen command forms through Grok's own runtime path. A
quoted path needs `&` in pwsh; `&` is a syntax error in sh; `$env:`
written by hand is refused by Grok's variable validator; `sh` is not on
a stock Windows PATH; a one-shot git alias runs in both shells but costs
three extra spawns per hook on Windows. `cd "${CLAUDE_PLUGIN_ROOT}/hooks";
./run-hook.cmd <hook>` is a builtin plus a relative command in both
shells, measured equal to the old shape under sh, and a Windows CI job
now feeds every shared entry to pwsh the way Grok does.

**Any session opened below the repository root.** git answers
`--git-common-dir` relative to the directory it was asked from, and the
anchor joined that path onto the toplevel. From a subdirectory the archive
resolved one level too high, the project read as not-initialized, and the
gate was silently off. Found while chasing a test; the anchor cache
carries a format version now so entries written by the old join are
re-resolved instead of served.

## Hooks inside their budget

A SessionStart on this repository's own archive (over nine thousand
records) took five seconds against a ten-second timeout: two dozen reads
each re-stat-ed every record file, and the hook's own appends forced a
full re-parse. A short-lived process now pins the identity it scanned
once, and its appends extend the parsed cache. Under two seconds on the
same archive, with the tamper contract intact - an in-place rewrite still
fails the next read.

The launcher's cmd half and `bin/godmode.cmd` probe interpreters the way
the sh half does and return the hook's own exit code; with only the `py`
launcher on PATH they used to answer 9009. A plain git checkout with no
archive is answered by the fast gate with stats alone instead of loading
the whole runtime to say "not initialized".

## What the other hosts said

- **Codex.** An archive write the OS refuses is a refusal naming the
  remedy, not a traceback (the sandbox could not write outside the
  workspace; on Windows the temporary file name pushed a deep state home
  past MAX_PATH). `doctor --host <name>` checks the hook artifact, the
  interpreter, the archive's writability, the interception grade, and
  every path the project's own hook file names. The live layer finds
  `codex.cmd`. The Cursor and Gemini edit replay failures were fixture
  errors sending Claude's tool name to hosts that never use it.
- **Antigravity.** Handlers sit inside a `hooks` array per matcher group,
  the fast gate reads the nested `toolCall` payload, the done bar answers
  `{"decision": "continue"}` there, and fragment commands carry no single
  quotes for cmd.exe.
- **Grok, again.** Every tool name in a live 1.0.13 init event has a
  declared answer, read-only or fail-closed on purpose.
- **Claude and the field walk.** A claim names the next grade and the
  flag that earns it; `remember --help` explains the `ask:<hex>` closure
  line; a pasted URL reads as its words in the request ledger; a reworded
  obligation value no longer hides a superseded subject; `precheck` with
  no argument is a usage refusal; the R2 reason shows the file, not the
  first eighty characters of its root; an exit-2 refusal says why on
  stderr.

## Hygiene the reports forced

Host tests start from a scrubbed environment (a suite run inside a Grok
or Antigravity session used to detect the ambient host). No skill,
adapter or sample tells a stock macOS to run bare `python`. The root
skill states the enforcement-honesty rule: a PARTIAL hooks status never
becomes "the gate blocked".

## Verifying

- `python -m unittest tests.test_hooks_manifest_polyglot` - on Windows the
  gate command runs through pwsh with a force-push payload and refuses.
- `python -m unittest tests.test_anchor_cache -k subdirectory` - a
  subdirectory resolves the same archive as the root.
- `python -m unittest tests.test_chronicle_cache` - own appends extend
  the cache; pinned reads scan once; an external write is still seen.
- `godmode doctor --host grok` (or codex, antigravity) - the wiring report
  with interpreters, artifact, writability and interception grade.
- `godmode claim "<text>" --cite cmd:...` - the payload carries
  `next_grade` and `next_action`; `--brief` shows the same line.
- CI: dispatch `godmode-verify.yml` on main and on the tag; the macOS
  stock-host leg and the new Windows PowerShell leg must both be green
  before the GitHub release is published.

Full detail per change: `CHANGELOG.md`.
