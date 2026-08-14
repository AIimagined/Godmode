`godmode init --detect` writes a starter charter from what a repo already proves about itself, instead of leaving a new project staring at an empty one.

It reads manifests (`package.json` scripts, `pyproject.toml`, `go.mod`, `Cargo.toml`), CI workflow `run:` lines, lint/format configs, `.gitignore` build markers, a migrations directory, and the default branch - all pure reads, stdlib-only, capped at 400 files with the cap always reported. Every candidate it writes is SOFT with its provenance named inline (`(detected: package.json scripts.test)`); the emitter hard-refuses to write anything else, because a wrong guess must never become a blocking gate uninspected - promotion stays a human decision made in the charter document itself.

Tighten-only: a project with an existing authority document gets a report of detected candidates and nothing is overwritten. A repo with no signal at all still gets an honest minimal stub instead of silence.
