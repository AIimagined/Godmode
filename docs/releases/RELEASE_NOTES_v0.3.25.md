# Godmode v0.3.25

The one-item cut. Cut the same day as 0.3.24 because the item is the
password gate itself, and a gate that is off is a field blocker, not a
batch item.

## What changed

- **An ask is only a gate when a person answers it.** On Claude Code in
  `auto`, `dontAsk`, or `bypassPermissions` mode a hook's "ask" is
  answered by the host, not by the operator. Three releases on
  2026-09-10 were pushed, tagged, and published with no password: the
  gate asked, the host's auto classifier said yes, and the record held a
  `gate-asked` row that read like consent. A would-ask in those modes
  now folds to deny with the staged-capability remedy in the reason,
  the same fold hosts with no ask dialog already had. `gate-asked`
  records carry the permission mode.
- **`doctor` names an `ask_only` entry for an external-write category**
  (`git-history-or-remote`, `release-or-external-write`): under those
  modes it is an allow.
- **README** describes the 0.3.24 surface: the iteration controls, the
  scope gate and the oracle, the ledger after a compaction, the new
  sentinel shapes, the node scan, and the numbers as of this cut.

## Known limits

- The fold is in the hook; the session that found the gap runs the
  installed plugin from its cache, so it is live only after the plugin
  is reloaded to a release carrying it. Until then the operator's
  staged capability must accompany every outbound write.
- Other hosts' auto modes are not enumerated; a host that sends no
  permission mode keeps the ask.

## Verifying

- `tests/test_ask_only_hook.NoHumanAskModeTests` fails against 0.3.24:
  `git push origin main` with `permission_mode: auto` rendered "ask".
- `python -m unittest tests.test_hook_end_to_end tests.test_ask_only_hook
  tests.test_sweep_0_3_24` green; the eight hook and gate modules green
  (198 tests).
