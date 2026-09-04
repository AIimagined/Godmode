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

## Verifying

- `godmode precheck --designate-suite "python -m unittest discover -s tests"`
  then `godmode precheck --preflight` - the suite runs unprompted; the
  skipped line about an undesignated suite is gone.
- CI: both refs green, stock-host leg included.
