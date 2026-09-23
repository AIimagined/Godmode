# Purpose

This skill exists so a failure is diagnosed from reproducible evidence and one
discriminating test, instead of from a plausible-sounding story about the mechanism.

## Gap evidence

- seq:11672 — a test asserted the wording of a claim rather than the exit code of the
  check meant to verify it, and stayed green after the verifier it depended on had
  stopped running at all.
- seq:12461 — a guard regression was only confirmed once a controlled before/after
  comparison actually ran; the mechanism story that preceded it was not evidence on
  its own.
- seq:12721 — four separate suite failures traced back to one exception that had been
  swallowed without ever being marked as an intentional, reviewed case.

- seq:14909 — a code read of the method selector found the 5-Whys contract stopped at a
  cited root: no backward validation of the chain, no countermeasures, nothing refusing a
  root that names a person, and reproduce-first living only as skill prose rather than a
  record requirement.
- seq:14913 — the same finding answered to the operator: plan-first and reproduce-first
  were advice, not gates, and the RCA ritual existed nowhere as a checkable record. The
  postmortem flow (validated 5-Whys, competing hypotheses with kill experiments, `repro:`
  red-then-green, the RCA checklist) is the answer to both.

## Promise

An investigation restates the observed failure without proposing a fix first, records
its reproduction red, weighs competing falsifiable hypotheses, runs the discriminating
check, and reports either a verified remedy - the same reproduction green - or exactly
what remains unknown. A postmortem is complete only when `method --check-record` says so.

Future edits to this skill append their own seq: citation above.
