# Purpose

This skill exists so a drafted or edited skill's routing claim is scored by
running the harness, before it ships - not asserted from a read-through of
its own prose.

## Gap evidence

- An offline routing check scores lexical overlap between a prompt and a
  skill's own description, with no model consulted: an authored example
  scored well while the same intent phrased naturally by a real user
  scored far lower and routed to the wrong skill — one instrument, one
  number, accepted alone.
- A separate, live evaluation found a skill was not invoked at all on
  natural phrasing, even though the offline lexical check had asserted
  that routing passed. The two results disagreed about the same routing
  claim and nothing reconciled them.

## Promise

A skill's routing and behavior claims are validated, linted, and scored
against the committed baseline by running the harness twice (lexically and
for determinism) before the skill lands, so two instruments never disagree
about the same claim with nobody asked to reconcile them.

Future edits to this skill append their own plain-language evidence above.
