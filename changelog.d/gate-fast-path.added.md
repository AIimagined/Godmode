A stdlib-only fast gate (`hooks/godmode_gate_fast.py`) now sits in front of the
full pre-tool hook. It answers exactly one question - is this command's head
on a vetted, conservative read-only floor (`hooks/gate_table.json`), with no
redirect and no `-exec`/`-delete` - and only ever returns `allow` (skip the
full hook, silently, no archive I/O) or `escalate` (run the full hook,
unchanged, output and exit code mirrored verbatim). Every ambiguous or
malformed input escalates; nothing is ever guessed into an allow. The
equivalence held against the 142-command real-denial corpus is one-directional
by design: every command the fast gate allows, the full sentinel also allows -
never the converse - so the fast path stays correct as the full classifier
continues to change under it.

`hooks/gate_table.json` ships as a PROVISIONAL, hand-built fixture (Task 5's
generated decision table replaces its contents, not its shape): the floor
holds only the host-parity read-only set named for this plan (`git
status/log/diff/show/branch/ls-files/rev-parse/rev-list/remote -v/shortlog/
describe/blame` plus `ls/cat/head/tail/wc/grep/rg/find/pwd/which/echo/sort/
uniq/cut/file/stat/du/df`) - one deliberate omission from that list: `tr` is
excluded because the full sentinel does not yet recognise a bare `tr` as
read-only (a stream-tool gap this same plan charters a later task to close),
so including it here would let the fast gate allow what the full hook still
asks about. `git branch` and `git remote -v` require an exact match with no
trailing token - both are the one shape on this floor where a bare positional
argument, not a flag, performs a real mutation (branch create/delete/rename).

`hooks/hooks.json`'s `PreToolUse` command now points at the fast gate
(`godmode_gate_fast.py`, no arguments) with its timeout dropped from 10s to 3s;
`SessionStart`/`UserPromptSubmit` are unchanged.

Measured on this machine (`git status`, 7-spawn median, matching
`scripts/dev/hook-probe.ps1`'s own methodology): fast path 196ms vs full hook
542.7ms - a bare `python -c "pass"` spawn alone measures 102ms here, so
interpreter-startup overhead dominates both numbers on Windows and the fast
gate's own logic adds roughly 94ms of that 196ms, not the full hook's several
hundred. The in-process verdict itself is far cheaper still: 1000 calls to
`fast_verdict` complete in under 1 second (well over 1000/sec), and the allow
path opens zero files (proven by an instrumented `open()` count in
`tests/test_gate_fast.py`).
