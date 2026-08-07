# Godmode v0.2.2

A patch release for one defect and its shadow. **Anyone running v0.2.1 with the
pre-tool gate enabled should update**: on Windows that build denies every
command, and on any platform a newline could hand a whole line the risk tier of
its first word.

## The gate knew only one shell

The pre-tool hook fires on PowerShell calls, but the classifier held POSIX
vocabulary only. `Get-ChildItem` matched nothing, fell through to
`unclassified-mutation`, and was denied — as was every other cmdlet. Failing
closed on an unrecognised mutation is the correct default; applying it to a
directory listing is the approval fatigue the threat model names, and it left
the session unable to do anything at all.

v0.2.1 fixed this same defect for POSIX and did not catch it here. The
usability corpus that drove that fix was lifted from a real session's command
history, which is a good way to know the commands are real and a poor way to
know they are representative: the session ran a POSIX-shaped shell, so the test
inherited its platform along with its commands.

PowerShell's approved-verb convention now classifies it. `Get`, `Test`,
`Measure`, `Select`, `Resolve`, `Compare` and their peers read, by a contract
Microsoft enforces on cmdlet authors rather than by a list that goes stale.
Naming the read verbs is the safe direction — `Set-Content`, `Remove-Item`,
`Invoke-Expression` and anything nobody enumerated are absent on purpose and
still fail closed. `find`, `findstr` and `where` are recognised too, while
`find … -delete` and `find … -exec` are named as the mutations they are.

## A read allowance is something to hide behind

While `ls` failed closed, a separator the splitter missed cost nothing. Once
`ls` was a recognised read, it cost the tier of everything after it: a newline
and a bare `&` never ended a segment, so `ls⏎Invoke-WebRequest …` classified as
a listing. Both now end a segment.

A command substitution cannot be split out at all — it never appears as a
segment, so there is nothing to classify. `$( )`, backticks and `${ }` now
withhold the read allowance instead of extending it over an operation the gate
never saw. A plain `$VAR`, PowerShell's `$env:` or `$_` expands to a value
rather than running a command and is unaffected.

## Also in this release

Three fixes that landed on `main` after v0.2.1 was tagged and were never
published:

- The injection scanner no longer reads vocabulary as instruction. An
  exfiltration verb must govern its object within a few words, so a threat model
  describing "memory leak" and "secret scan" on one line is documentation.
- The composite action loads again. An input description interpolated
  `${{ github.base_ref }}`, and expressions are evaluated in a manifest where
  that context is not bound, so the file failed to parse — since the day it was
  written, because nothing but GitHub had ever read it. It is now asserted
  locally.
- Two behaviour probes were machine-dependent: they called commands needing an
  initialised archive, so they passed on a developer's machine and failed on a
  fresh checkout.

## Verifying

```
python -m unittest discover -s tests        # 417 tests
python scripts/godmode.py --project . selftest --brief
python scripts/godmode.py --project . version --reconcile --brief
```

The usability suite now carries a Windows corpus alongside the POSIX one and
asserts the laundering cases directly, so neither half of the contract — the
work that must pass, the mutations that must not — rests on which shell the
last session happened to use.
