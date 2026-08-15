- Commit-linked experiment ledger with epsilon adjudication (U-R3): each
  `run_experiment()` call is one cycle, and a next cycle is now REFUSED
  until the one before it has a `verdict` record (verdict-before-next-cycle,
  enforced at the API; `godmode_loop.unadjudicated_experiment_cycles` is the
  read-time half, for a raw append that bypasses `run_experiment` entirely -
  wired into `analyze()`). New `godmode_guardrails.record_experiment_verdict`
  adjudicates a cycle from `{metric, before, after, epsilon}`: improvement
  `>= epsilon` keeps, short of that discards, unless the result is exactly
  flat AND declared `simpler=True` (`keep-simpler`) - a regression is never
  rescued by "simpler" alone. Every verdict is commit-linked (`run_git
  rev-parse HEAD`, `run_git` from `godmode_anchor`). A declared `max_cycles`
  in `.godmode-experiment.json` bounds the series itself: exhausting it with
  no explicit completion claim on record writes a closing `verdict` with
  `run_state: "truncated"` and refuses to run again - loop exhaustion is
  never read as completion (E78's positive completion sentinel); a
  completion claim, once made, is audited by U-V1's own unmodified
  citation-grading (`godmode_attest._citation_resolves`), not reimplemented
  here. `acquitted_by="self"` (the default) never sets `disposition`, so a
  self-graded cycle can never trip the archive-seam invariant; a caller
  asserting `acquitted_by="independent"` is held to the same
  `godmode_invariants._verdict_invariants` rules as every other verdict kind
  - a truncated (exhausted or budget-cut) cycle can still never be recorded
  "confirmed". CLI: `godmode experiment` is now `experiment run` /
  `experiment verdict` (was a single flat command).
