# Purpose

This skill exists so a failure is diagnosed from reproducible evidence and one
discriminating test, instead of from a plausible-sounding story about the mechanism.

## Gap evidence

- A test asserted the wording of a claim rather than the exit code of the
  check meant to verify it, and stayed green even after the verifier it
  depended on had stopped running at all.
- A guard regression was only confirmed once a controlled before/after
  comparison actually ran; the mechanism story that preceded it was not
  evidence on its own.
- Four separate test failures traced back to one exception that had been
  silently swallowed, never marked as an intentional, deliberate case.
- A root-cause method stopped at a cited root with no backward validation
  of the chain, no countermeasures, and nothing refusing a root that names
  a person — reproducing the failure first lived only as prose, never as a
  checkable requirement.
- Planning before acting and reproducing a failure before fixing it were
  treated as advice rather than as gates, with no checkable record that
  either had actually happened.

## Promise

An investigation restates the observed failure without proposing a fix first, records
its reproduction red, weighs competing falsifiable hypotheses, runs the discriminating
check, and reports either a verified remedy - the same reproduction green - or exactly
what remains unknown. A postmortem is complete only when `method --check-record` says so.

Future edits to this skill append their own plain-language evidence above.
