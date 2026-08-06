Authored evaluation cases live in each skill's `skills/<name>/godmode-evals.json`; this directory holds any future cross-skill cases, and `../fixtures/` holds the last-accepted routing snapshots the behaviour check diffs against.
Regenerate snapshots deliberately with `godmode evals --write-snapshots` (or `check_snapshots(project, write=True)` from `godmode_runtime.godmode_evals`) after an intended routing change.
Control coverage is reported by the adversarial grid (`godmode grid`), separately from code coverage: a line executed is not a control observed refusing an attack.
