# Godmode v0.3.7

The fence holds in every spelling.

A hotfix cut from v0.3.6's first hours in the field: two external
agents and the first cross-platform CI matrix run filed findings the
same day, and every one closes here. The CI matrix's first run earned
its keep - it found two containment gaps a single development machine
never could.

## Short names and foreign drives cannot slip the fence

On a Windows volume that keeps 8.3 aliases, a short-name spelling
(RUNNER~1) of an in-tree path read as outside the working tree: an
in-tree write was misjudged, and a pinned evaluator path stopped
matching - a deny became an allow. Canonicalization now expands short
names before comparing (Windows only), and a mid-name tilde is a
literal filename character rather than an unexpanded home marker. On a
posix host, a drive-lettered Windows path read as relative and a
PowerShell mutation aimed at C:\Windows passed containment; such a
path is now absolute wherever the gate runs.

## The stop hook speaks once

A reply that both touched an open obligation and made an unrecorded
claim got two JSON objects printed to stdout - each valid alone,
unparseable together, so the host dropped the whole delivery. Notices
accumulate into one systemMessage printed once.

## Field findings close the same day

The hosted-escape-hint test pins the host dialect it asserts, so a
suite run inside another host's session no longer reads that host's
own (correct) refusal envelope as a regression. The ranking snapshot
records its freshness instrument (full git, shallow git, path) beside
its scorer, and a cross-mode comparison reports ranking-mode-differs
instead of drift. The evals verdict names its failing gates instead of
echoing routing-sound while exiting non-zero. Host-sensitive hook
tests pin the dialect they assert, and the Windows-casefold probe
skips on posix instead of asserting the host.

## Verifying

- `python -m unittest discover -s tests` - run in shards
  (`scripts/dev/run_with_flaky_retry.py` retries only registered flakes).
- `godmode evals --brief` - exit 0, and a failure now names its gate.
- `godmode changelog check` - fragments folded at release time.
- `godmode version --reconcile` - every surface answers 0.3.7.
- The cross-platform proof: the godmode-verify workflow matrix
  (windows, ubuntu, macos x 3.11, 3.13) against this tag.
