# Godmode v0.3.5 (draft)

The night the field reports came from five hosts.

v0.3.4 closed the first day's feedback; hours later Grok, Codex, and a
new arrival - Antigravity - each filed a full report against it. This
release is those reports closed, plus the fifth host wired.

## Antigravity becomes the fifth wired host

An Antigravity agent cloned the repo, ran `godmode init`, the full unit
suite, the 23-scenario battery, and observe mode entirely through its own
tools - skills discovered natively from `.agents/skills/`, no installer.
This release meets it halfway on the gate: the host adapter reads BOTH
dialects - the nested `toolCall` shape the official docs describe and the
flat BeforeTool envelope the live host actually speaks, with its own
vocabulary the same day's report captured (`run_command` gates as shell on
`CommandLine`, `view_file` reads, `write_to_file`/`replace_file_content`
are fenced mutations on `TargetFile`, unknown names fail closed).
Detection keys on the unique tool names, the `toolCall` nesting, and the
live-captured `ANTIGRAVITY_*` env markers. `render_decision` speaks the
documented `{decision, reason}` stdout contract - with a real `ask`, the
third host to have one - and `godmode hooks wire --host antigravity`
merges the godmode entry into the project's `.agents/hooks.json` without
clobbering foreign hooks. The artifact registry stays honest: interception
is SOFT until a live deny is chronicled, and Stop not firing on Windows is
field-confirmed.

## The digest reads a no-ask host's real evidence

`roi --digest`'s enforce section now renders from denial records alone.
Grok's first live project had sixteen real denials and a digest that
reported observe-only zeros - because a no-ask host folds every would-ask
into a deny, so its enforce-era evidence lives in refusal records, not
gate-ask records. R2/R3 denials feed the `ask_only` tune; R4/R5 are
counted but never proposed for silencing.

## Fixes the second night's reports demanded

- The day-one `guide` speaks the host's own dialect: a no-ask host sees
  deny-not-ask on the first screen instead of Claude's ask language.
- Bare `godmode version` prints the package version and writes nothing;
  recording a version fact still takes `--name` and `--value`.
- `GODMODE.md` opens with the four - now five - hosts, not one; the
  identity line is itself a compiled advisory charter rule, so the change
  carries its review on the record and regenerated eval snapshots.
- The pre-push hook test resolves `sh`/`bash` from PATH and skips with a
  stated reason on a pure-Windows host without Git Bash (Antigravity and
  Codex both hit WinError 2); the real-push half of the contract still
  runs everywhere, inside git's own bundled shell.

## Verifying

- `python -m unittest discover -s tests` - run in shards
  (`scripts/dev/run_with_flaky_retry.py` retries only registered flakes).
- `godmode bindings --check` - every generated manifest current,
  including the new `.antigravity-plugin/hooks-fragment.json`.
- `godmode evals --brief` - exit 0.
- `godmode changelog check` - fragments folded at release time.
