# Purpose

This skill exists so an answer that did not land gets re-pitched in a form the
operator can actually act on, with a record of why the first form failed, instead of
repeating the same shape of answer.

## Gap evidence

- seq:9034 — a status report was blocked by an evidence gate even though every
  figure in it came from that same turn's own tool output; the answer was correct
  and still could not land.
- seq:9035 — an automatic follow-up nag misread a reply that had, in fact, already
  answered the operator's open question.
- seq:15968 — a status question asked mid-turn was answered only after another round
  of work had already been dispatched, arriving too late to be useful.

## Promise

When the operator signals confusion, repetition, or an unanswered wait, this skill
restates the answer in a different, more actionable form and records what the first
attempt got wrong so the same miss is not produced again.

Future edits to this skill append their own seq: citation above.
