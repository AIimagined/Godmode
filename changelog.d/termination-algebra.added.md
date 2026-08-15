- Composable termination algebra with fail-loud lifecycle (U-R1): new
  `godmode_stop.py` - `Stop` predicates (`MaxRecords(n)`, `MaxWall(seconds)`,
  `OperatorStop(flag_path)`, `MetricPlateau(name, eps, patience)`) consulted
  over the record-delta since the last call, so cost stays O(new) regardless
  of run length. Compose with `&`/`|`; a composed reason names WHICH leaf
  fired. A fired `Stop` is spent - consulting it again without `reset()`
  raises `SpentStopError` rather than quietly re-answering. `attempt(budget_s)`
  bounds one subprocess attempt: overrun kills the process outright and the
  result carries `run_state: "truncated"` (U-V1's vocabulary), so feeding a
  truncated result into a `disposition: "confirmed"` verdict hits the
  existing archive-seam refusal in `godmode_invariants._verdict_invariants` -
  budget exhaustion cannot impersonate completion. `godmode watchdog`
  consumes an `OperatorStop` flag (`.godmode-stop`) so an operator can
  interrupt the boundary scan regardless of the skip pattern; `godmode
  experiment` gains an optional `--budget-s` wall-time bound over the whole
  bounded series, independent of `max_runs`.
