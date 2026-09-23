# Purpose

This skill exists so a drafted or edited skill's routing claim is scored by
running the harness, before it ships - not asserted from a read-through of
its own prose.

## Gap evidence

- seq:12266 - the offline routing snapshot scores lexical token overlap
  between a prompt and a skill's own description plus its sibling prompts,
  with no model consulted: an authored positive scored 0.5714 to `godmode`
  while the same intent in plain user phrasing scored only 0.1111 and routed
  to a different skill. One instrument, one number, accepted alone.
- seq:12268 - a later, independent instrument (a live plugin eval, three
  cases and 18 runs, overall score 1.0) found the `godmode` skill was
  invoked 0 of 3 times on natural resume phrasing, even though its own
  lexical snapshot asserted that route passes. Its own recorded advisory
  flags the disagreement directly: "quantities disagree with seq 12266 on
  the same subject ... if this corrects it, resolve the elder superseded;
  if both are true, say what differs." Nothing in the archive completes
  that resolution - the two instruments' scores for the same routing claim
  were left standing side by side, unreconciled.

## Promise

A skill's routing and behavior claims are validated, linted, and scored
against the committed baseline by running the harness twice (lexically and
for determinism) before the skill lands, so two instruments never disagree
about the same claim with nobody asked to reconcile them.

Future edits to this skill append their own seq: citation above.
