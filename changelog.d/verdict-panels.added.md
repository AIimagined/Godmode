- `verdict` panels (U-E4): `record_verdict`'s `--checker` is now repeatable
  (1..N; a single command still works unchanged - every caller from before
  panels existed is unaffected). Each checker runs independently against the
  same witness, never invoking the producer, and its own
  `{checker, exit, disposition}` is recorded verbatim in `checks`. The panel
  folds to one disposition by a closed rule, never a score: all confirmed ->
  `confirmed`; any refuted -> `contested` when at least one other checker
  confirmed, else `refuted` outright; a checker that could not judge is
  recorded as a stated gap and excluded from the fold, unless none of them
  judged anything, in which case the whole panel is `witness-malformed`.
  `contested` joins the disposition enum. The archive-seam invariant now
  also refuses a `confirmed` fold whose own `checks` carry a refuting entry,
  whether that record comes from `record_verdict` or a raw append. A
  `verdict:<seq>` citation still resolves only on `confirmed` - `contested`
  is refused by that same existing rule, with no separate code path needed.
  `godmode verdict record --checker <cmd> [--checker <cmd> ...]`.
