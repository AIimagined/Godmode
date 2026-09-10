# Godmode v0.3.25

## Added

- **A would-ask is a deny when nobody answers it.** On Claude Code in
  `auto`, `dontAsk`, or `bypassPermissions` mode, a protected call that
  the gate would have asked about is refused instead, with the
  staged-capability remedy in the reason (`godmode authorize stage
  --from-last-refusal`). In `default`, `plan`, and `acceptEdits` mode the
  ask still reaches you. Every `gate-asked` record now carries the
  permission mode it was asked under.
- **`doctor` reads your `ask_only` list.** An entry for
  `git-history-or-remote` or `release-or-external-write` is named as a
  warning, because under an auto-answered mode it is an allow.
- **A check must be able to fail.** A `--verify` citation whose command
  only reports state (`git status`, `echo`, `ls`, `cat`) cannot contradict
  the claim, so the grade stays below `verified` and the support line says
  which citation is decoration.
- **A claim knows the code it describes.** Every existing file a claim's
  text names is hashed at record time; when that file changes, the claim
  shows as stale in `claim --stale` and in the session brief.
- **Project ratchets.** Declare the repository's own debt counters in
  `.godmode-ratchets.json` (name to command); `godmode ratchet run` records
  each value and names every counter that rose, and `integrity` carries
  the same finding as its thirteenth monitor.
- **Measurement environment.** `precheck` on a latency, duplicate-request,
  or re-render task lists the environment the deciding number must come
  from. A quoted sentence is no longer read as a claim. A process-control
  call's advisory names `checkpoint --owes` for the restore.
- **Release notes as a verb.** `godmode release-notes build <version>`
  derives the note from that version's CHANGELOG section, grouped by
  kind, with a Verifying section built from the tests the entries name;
  `release-notes check <version>` holds an existing note to the shape:
  present, every entry covered, no empty section, no process narration,
  a Verifying section. The docs lint names process narration in a note
  (`release-note-narration`), from the version set in
  `.godmode-docslint.json` under `narration_from`.
- **README** describes the current surface: the iteration controls, the
  scope gate and the oracle, the ledger after a compaction, the sentinel
  shapes added in 0.3.24, the node scan, and the numbers.

## Using it

- No configuration. The fold reads the `permission_mode` field the host
  sends with each tool call.
- To let a push through in an auto-answered mode, stage the exact
  command once with the operator password: `godmode authorize stage
  --operation "git push origin main"`. The capability is spent on the
  matching call.
- Run `godmode doctor` after upgrading; an `ask-only-external-write`
  warning means your policy file lists an external-write category under
  `ask_only`.

## Limits

- The fold covers the modes Claude Code documents. A host that sends no
  permission mode keeps the ask.
- A session keeps the plugin it started with; the fold applies from the
  first session after the plugin is updated.

## Verifying

- `python -m unittest tests.test_ask_only_hook.NoHumanAskModeTests`:
  a push with `permission_mode: auto` renders `deny`; with `default` it
  renders `ask`.
- `godmode history --kind action --limit 5` after a gated call shows
  `permission_mode` on the `gate-asked` row.
