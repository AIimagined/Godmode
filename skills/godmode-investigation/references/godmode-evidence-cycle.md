# Godmode Evidence Cycle

An attempt record should contain:

- symptom and smallest reproduction, recorded on the incident as `--repro "<command>"`
  so its red run is on record before any patch;
- relevant identity: version, branch, HEAD, worktree, or migration state;
- boundary observations and the earliest known divergence;
- at least two competing hypotheses, each a `hypothesis` record with a kill experiment,
  and which of them survived it;
- one experiment and its outcome;
- evidence references with secrets removed;
- next action or architectural question.

Before a fix claim, verify the original symptom - the same reproduction command, now
green (`claim --fixes <incident-seq> --verify`), the regression check, the directly
affected suite, and any integration boundary changed by the remedy. For a new regression
test, prove that it fails without the remedy and passes with it when safe and practical.

Stop conditions are insufficient evidence, nondeterministic reproduction, invalid test
premise, missing authority, or three repeats of the same failed causal hypothesis. These
conditions require a finding or user decision, not another speculative edit.

A postmortem adds the six-step RCA checklist (what, when, where, why, fix-root, lock) and
a 5-Whys record whose chain is validated backwards from the root, whose countermeasures
are immediate, preventive and detection (a check or ratchet), and whose root is a
process, check, invariant or design cause - never a person or "human error".
`method --check-record` names every gap until it holds.
