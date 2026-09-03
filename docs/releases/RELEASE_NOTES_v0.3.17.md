# Godmode v0.3.17

Godmode now works on stock macOS in every host. A field install on a
machine with no bare `python` had all eight hooks die silently - stock
macOS ships only `python3`. Every hook command in every host surface now
routes through a polyglot launcher (one file, valid under both POSIX sh
and cmd.exe) that resolves `python3`, `python`, then `py` per platform
and execs so gate-block exit codes pass through untouched;
`GODMODE_PYTHON` overrides everything, and a machine with no interpreter
at all says so loudly instead of dying silently. A session opened on an
uninitialized project is told at the open that nothing is being gated.
And CI now proves the class dead, not just the code correct: a stock-host
job runs every hook entry the way a host invokes it, on a runner with no
installed Python and bare `python` poisoned.

The claim payload leads with a support line naming what was executed
versus what is taken on the author's word - an honest "observed" grade
that never says so reads as noise, and the line names the path up:
re-run with `--verify` when a cmd: citation sits unexecuted.

A quiet gate says why it is quiet. The session brief now states the gate
posture at open in BOTH modes: observe mode already announced itself with
its would-have counts and promotion prompt; enforce mode now says plainly
that reads and working-tree writes run free by design and that asks are
reserved for the protected classes - a field project measured a zero-ask
day of allow-tier work and concluded the gate existed on paper, which is
exactly the misread this line ends.

Two trip wires join the stop surface, measured against the archive's own
per-session baseline: recorded activity past twice the average draws the
runaway-loop advisory, and a spike of protected-class refusals draws the
permission-drift advisory. Doctor gains a guide-growth gauge - the week's
lessons and invariants, because zero growth means nothing was learned and
fast growth means patching instead of generalizing.

Stop-surface copy earns its reading: every unfinished-promise line
carries its own paste-ready closure command (the footer no longer
prescribes a kind the line above contradicts), and a truncated statement
list names its remainder with "(+N more)" instead of counting three and
quoting two.

## Verifying

- On a Mac with no bare `python`: `echo '{}' |
  <plugin>/hooks/run-hook.cmd godmode_gate_fast.py` exits 0.
- `godmode claim "<text>" --cite cmd:"<command>" --verify` - the payload's
  support line reads "executed and attested"; without `--verify` it says
  the cite is taken on the record's word.
- Open a session on an enforce-mode project: the brief carries "gate
  ENFORCING - reads and working-tree writes run free by design".
- `godmode grid` — thirteen adversarial probes prove the protected
  classes hold; `godmode capabilities` shows the allow/protect split.
