# Godmode v0.3.34

## Added

- `godmode remember --kind request --subjects-file <file> --status answered` closes every ask id listed in the file in one process, after checking all of them against the open list; closing 150 asks one launch at a time took 45 minutes on a 29,000-record archive.

## Changed

- The host reach table cites a fresh live deny for Claude Code on Windows (2026-10-04, hook 0.3.33) in place of the 0.3.26 one.
- The host reach table marks Grok's pre-tool gate as partial: in single-turn mode (`grok -p`) Grok 1.0.41 loads no hooks and approves every tool call itself, so the gate is never asked there (observed 2026-10-05 on Windows). Interactive sessions are unchanged.
- `godmode forget` now rotates repository snapshots older than 14 days to the cold tier and always keeps the newest one; on one archive 27 snapshots held 18.7 MB of a 42.9 MB read index that every record-reading command parsed. `retention_days` accepts `inventory` like the other kinds.

## Fixed

- In a project Godmode was never initialized in, a harm-class command (a force push, a history rewrite, a delete outside the tree, a release) is now refused when the host runs in auto, dontAsk or bypass mode. It used to get an ask, and in those modes the host answers its own ask, so the command ran with no person approving it. With a person at the prompt it still asks.
- `gh run watch` is classified as the read it is and runs free, like `gh run view` and `gh pr checks --watch`; `gh run rerun` and `gh run cancel` still ask.
- A command that reads no archive record no longer scans every record file first: the scan now happens on the first read. Reading one record by sequence on a 29,000-record archive went from about 3.7 s to about 2.6 s.
- `godmode --version` prints its banner without loading the runtime or building the command parser (about 0.1 s instead of 0.4 s or more).
- A launcher test fired the real gate against the checkout with the live environment, so its refused sample command was written to the project's own archive and `authorize stage --from-last-refusal` could offer a force push nobody had attempted. The test now runs under its own state home.

## Verifying

- `python -m unittest discover -s tests` for the whole suite.
