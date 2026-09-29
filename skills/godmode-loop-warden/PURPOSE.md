# Purpose

This skill exists so a retry cycle is bounded before it starts and stopped
when it stops making progress, instead of being noticed only after the
budget is gone and the same hunk has been rewritten a dozen times.

## Gap evidence

- An agent retried one failing test across many iterations with edits that
  touched the same lines each time, and nothing in the session named the
  repetition until the operator read the transcript.
- Loop files were written without a stop contract, so the first cycle ran
  with no cap, no verdict path and no escalation threshold.
- A stalled loop was blamed on the model with no non-model control on the
  record to support that reading.

## Promise

Every loop is declared with a cap and stop conditions, ticked with evidence
per iteration, read for repetition from the transcript, and closed as
finished or cut off with the evidence that decides which.

Future edits to this skill append their own plain-language evidence above.
