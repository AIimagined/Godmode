# Godmode v0.3.34

## Added

- `godmode remember --kind request --subjects-file <file> --status answered` closes every ask id listed in the file in one process, after checking all of them against the open list; closing 150 asks one launch at a time took 45 minutes on a 29,000-record archive.

## Changed

- The host reach table cites a fresh live deny for Claude Code on Windows (2026-10-04, hook 0.3.33) in place of the 0.3.26 one.

## Fixed

- `gh run watch` is classified as the read it is and runs free, like `gh run view` and `gh pr checks --watch`; `gh run rerun` and `gh run cancel` still ask.
- A command that reads no archive record no longer scans every record file first: the scan now happens on the first read. Reading one record by sequence on a 29,000-record archive went from about 3.7 s to about 2.6 s.
- `godmode --version` prints its banner without loading the runtime or building the command parser (about 0.1 s instead of 0.4 s or more).

## Verifying

- `python -m unittest discover -s tests` for the whole suite.
