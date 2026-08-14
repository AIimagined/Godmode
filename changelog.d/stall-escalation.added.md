- Graduated stall escalation - redirect at 2, human at 4 (U-R2):
  `godmode_loop.analyze` gains `stall_escalation`, an empty-round counter
  joining the existing oscillation/spent-hypothesis detectors. A round
  closes at each checkpoint; it is empty when no change, attestation, or
  verdict was recorded since the previous one. Two consecutive empty rounds
  produce a blocking `stall-redirect` finding ("record what you'll do
  differently"); four produce a governance `stall-escalation` halt ("human
  escalation required"), cleared only by an operator-sourced record
  (`data.source == "stated"` on a `request`/`decision`) - an agent's own
  inference does not count. `godmode watchdog` gains a matching freshness
  check (`state_freshness`): a loop that claims activity (`--loop-active`)
  but has not touched the archive within the age ceiling routes to the same
  `human-escalation` verdict as a stall streak.

  Task 10b (amendment): a loop/experiment declaration now states `maturity:
  "report-only"|"assisted"`; `"unattended"` is refused by name, not silently
  downgraded - nothing here reads a cycle's output before the next one
  starts. `godmode loop --preflight` audits `.godmode-loop.json` before
  cycle one via `loop_ready`: a declared stop contract (U-R1), a positive
  `budget_s`, a named `verdict_path`, and sane escalation thresholds
  (`n1 < n2`, both positive) are all required, each missing piece its own
  blocking finding.
