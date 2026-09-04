# Godmode v0.3.18

Delivery patch for v0.3.17, plus the control its own red CI demanded.

Two test pins were stale against v0.3.17's deliberate changes - the
manifest contract expected the pre-launcher command form, and a packaging
test asserted the pre-init silence that release deliberately ended. Both
pins now enforce the new doctrine. Every other leg was green, including
the first stock-host run (macOS, no installed Python, bare `python`
poisoned).

The recurring miss got its ratchet: `precheck --designate-suite "<cmd>"`
records the pre-push suite once, and every later preflight runs it
without being asked, reporting a non-zero exit as a judgment finding
that quotes the failing summary lines. A control that depends on
remembering a flag is willpower; this gate now remembers for itself.

The ratchet earned its keep before shipping: its first live runs caught
sentinel-scoping assertions failing only inside the gate - the preflight
worktree lived under the system temp dir, which is the sentinel's own
scratch allowance, so the controls were being tested from inside the one
zone they deliberately exempt. (A second try under the repo's .git
failed the opposite way - plain-file fixtures correctly classified as
git-internals mutations.) The worktree now lives beside the repo:
ordinary filesystem to every classifier, and the location the green
full-suite experiment ran from.

## One day of field reports

Three effectiveness reports from live sessions arrived while the gate
was running, and each named a friction with a pin behind it now:

- **A readout is not a claim.** The done-bar blocked a status report
  whose every figure was godmode's own output seconds earlier. A
  sentence whose numbers all appear in this turn's tool results, with a
  word of context beside them, is an observation; promise-verb claims
  carry no number and stay gated.
- **The answer is not an unfinished promise.** The reply that served
  "check godmode continuity" was told to close it. A reply restating
  three-quarters of the ask's keywords is serving it; a related progress
  line shares half the words of an ask it has not served, and stays
  surfaced. The ledger still holds the ask until a person closes it.
- **A remedy applied is a signal silenced.** The capacity warning fired
  on every call after the checkpoint it asked for existed. A checkpoint
  among the newest 25 records covers the brief; the due message carries
  the command.
- **Measure and accept in one call.** `context status --scan
  --rebaseline` records the scanned tree as the new baseline; `--scan`
  alone still only measures, and the drift finding says which verb moves
  it.
- **Build caches are not drift.** `.next` and its kin join the shared
  skip list.
- **"What is left" means now.** `status remaining` reports an age split
  on every call and takes `--since DAYS`; 303 items dominated by
  months-old obligations was a list nobody could use.

And the gate caught itself once more: round 7 outran the hour and died
as a bare `TimeoutExpired`, the suite output lost with the process. The
kill is a judgment finding now, quoting the last thing the suite wrote.

## Verifying

- `godmode precheck --designate-suite "python -m unittest discover -s tests"`
  then `godmode precheck --preflight` - the suite runs unprompted; the
  skipped line about an undesignated suite is gone.
- `godmode status remaining --since 30` - the hidden count is reported
  beside the window.
- `godmode context status --scan --rebaseline` - the response carries
  the accepted baseline record.
- CI: both refs green, stock-host leg included.
