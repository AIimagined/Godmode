`branches --claim` declares this agent active in the worktree and exits
non-zero when another agent's live claim exists — the collision surfaces before
mutation; `--release` hands it back. No merge driver ships: per-record
append-only files make state conflicts structurally impossible (decision
recorded).
