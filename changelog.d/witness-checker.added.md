- `verdict` record kind (U-V1): a claim of "fixed X" becomes admissible only
  as a claimed value plus a data-only witness plus an independent checker
  that recomputes from the witness alone and asserts against the claim.
  Three dispositions, never two - `confirmed`, `refuted`, `witness-malformed`
  - with the witness validated structurally before the checker ever runs, so
  a missing witness or a checker that cannot start/finish is stored as
  "never judged," not silently folded into "judged false." Two invariants
  are refused at append time: a self-acquitted `confirmed` (quality needs an
  independent checker), and a `confirmed` on a `truncated` run (a budget
  cutoff cannot impersonate completion). `godmode verdict record|show`; a
  `--grade verified` claim citing `verdict:<seq>` resolves only when that
  verdict's disposition is `confirmed`.
