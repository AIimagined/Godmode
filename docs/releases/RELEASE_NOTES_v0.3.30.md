# Godmode v0.3.30

A small fix release. In the default advise mode, the push preflight no longer fails
on local bookkeeping that CI never sees - open operator asks, stale claims, flake and
falsifier aging, host reach. These findings are still reported; `strict` mode still
blocks on them. Failing tests, gates and mechanical findings fail the preflight in
both modes, as before.

The repository's own pre-push script also lets a branch delete or a tag push straight
through, since neither carries branch code to check.

## Fixed

- The push preflight's local bookkeeping findings (open operator asks, stale claims, flake and falsifier aging, host reach) now advise instead of blocking in the default mode; `strict` mode still blocks on them, and CI is unaffected either way.
- `scripts/dev/pre-push` no longer runs the local checks for a branch delete or a tag push; with no branch code in the push, it goes straight through instead of being refused after the full local run.

## Verifying

- Preflight in advise and strict modes: `python -m unittest tests.test_push_preflight`
- The pre-push script: `python -m unittest tests.test_dev_pre_push`
- `python -m unittest discover -s tests` for the whole suite.
