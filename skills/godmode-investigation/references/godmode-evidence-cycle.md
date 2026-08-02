# Godmode Evidence Cycle

An attempt record should contain:

- symptom and smallest reproduction;
- relevant identity: version, branch, HEAD, worktree, or migration state;
- boundary observations and the earliest known divergence;
- one hypothesis and its falsifying result;
- one experiment and its outcome;
- evidence references with secrets removed;
- next action or architectural question.

Before a fix claim, verify the original symptom, the regression check, the directly
affected suite, and any integration boundary changed by the remedy. For a new regression
test, prove that it fails without the remedy and passes with it when safe and practical.

Stop conditions are insufficient evidence, nondeterministic reproduction, invalid test
premise, missing authority, or three repeats of the same failed causal hypothesis. These
conditions require a finding or user decision, not another speculative edit.
