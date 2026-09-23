# Godmode v0.3.29

Godmode now enforces harm and advises on quality. Checks that guard what is hard to
undo - pushes, tags, releases, deletes - still refuse. Checks about how work is
finished - the completion bar, stall detection, claim and obligation reminders - now
report once per session and never block. A project that wants the previous behaviour
sets `godmode config mode strict`.

The pre-tool gate also got stricter where it matters. A host runs the tool when a hook
outlives its timeout, so a slow check on a large archive used to let a protected call
through; the gate now refuses a call its full check could not decide within 25 seconds,
and every shipped manifest gives it 30. Publishing a release needs a staged capability
in every permission mode: a green CI run is still required first, but it no longer
stands in for your approval. Chained commands are checked command by command.

Development got faster too: a preflight verdict is reused when the file tree is
unchanged, a push to a branch CI already verifies needs no local preflight, and two
developer scripts run only the affected tests and CI's own checks before a push.

## Added

- Godmode now advises on quality by default: the completion, stall and claim checks report once per session and never block. `godmode config mode strict` restores blocking. Checks on pushes, tags and releases are the same in both modes.
- `scripts/dev/affected_tests.py` runs only the test modules affected by the current change, plus a small smoke set, for a fast loop during development.
- `scripts/dev/ci_local.py` runs the workflow's gate list and the affected tests on HEAD in a disposable worktree, and `scripts/dev/pre-push` runs it before every push.

## Changed

- A plain push to a branch the verify workflow runs on stages without a local preflight, since CI checks it; pushes to main, tags, forced pushes and chained commands still need one.
- A push stages over a green preflight whose file tree matches HEAD, so rewording or squashing a commit keeps its verdict; any file change still requires a new run.
- Publishing a release (a tag push or a GitHub Release write) needs a staged capability in every permission mode; a green CI run is required first but no longer stands in for the operator's approval. Chained commands are checked command by command.
- The second-look review skill states its review defaults: advisory, diff-only, Important versus nit, at most five nits, and Important findings only after the first pass.

## Fixed

- The pre-tool gate now refuses a call when its full check has not answered within 25 seconds, instead of leaving the host to run the tool after a hook timeout; every shipped host manifest gives the gate 30 seconds.

## Verifying

- Advise and strict modes: `python -m unittest tests.test_mode_switch tests.test_stop_completion_gate tests.test_donebar_roles`
- The gate deadline and host timeouts: `python -m unittest tests.test_gate_fast tests.test_manifest_timeouts tests.test_host_manifests`
- Releases need a staged capability: `python -m unittest tests.test_tag_push_ci_gate`
- Preflight reuse and CI-verified branches: `python -m unittest tests.test_preflight_gate tests.test_affected_tests`
- `python -m unittest discover -s tests` for the whole suite.
