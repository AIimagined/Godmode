# Godmode Continuity Schema

Primary records are immutable, sequential, project-bound JSON files with a timestamp,
kind, subject, structured data, evidence references, prior-record hash, and content hash.
Supported kinds cover inventory, change, decision, invariant, incident, lesson,
checklist, checkpoint, version, branch, database, sprint, documentation, plan,
obligation, and action events.

The context brief prioritizes invariants, decisions, obligations, open checks, incidents,
and recent changes. Inventory file lists are summarized to stay within budget. Derived
briefs can be rebuilt from primary records and fresh repository observation.

Detector meanings:

- `no-baseline` or `stale-baseline`: inspection evidence is absent or old.
- `identity-drift`: the active branch, HEAD, worktree, or remote identity changed.
- `undocumented-drift`: current inventory differs from the saved baseline.
- `phantom-reference`: a recorded changed path no longer exists.
- `contradictory-invariants`: one invariant subject has multiple active values.
- `unproven-completion`: completion lacks an evidence reference.
- `repeat-loop`: one failed hypothesis was repeated three or more times.
- `capacity-overflow`: obligations exceed declared sprint capacity.
