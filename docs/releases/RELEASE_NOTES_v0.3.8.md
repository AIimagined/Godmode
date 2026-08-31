# Godmode v0.3.8

Willpower is not a control.

Cut on the night the matrix went fully green for the first time - nine
jobs, three platforms, two Pythons - after a six-round CI campaign
whose post-mortem became this release's feature list. The campaign's
finding: every control that held was compiled into the environment;
everything that failed had been left to discipline. v0.3.8 compiles in
the rest.

## The last alias falls

The scratch allowance's anti-swallow guard compared unresolved path
spellings, so on a runner whose temp directory is reached through an
alias (Windows 8.3, macOS's /var symlink) a project genuinely under
temp went unrecognized - the allowance stayed armed and swallowed the
outside-the-tree denials containment owed. All three paths in the
check now canonicalize the way containment does, alias resolution is
unified across every platform, and the suite's own state leaks
(an open session poisoning later modules, tests assuming an archive a
fresh checkout lacks, a line-ending-dependent freshness digest) are
closed. The cross-platform proof: the matrix itself.

## Two reversals stop the third try

A scored claim resolved failed is a recorded reversal. When two
reversals share their subject, the next verified-or-scored claim on it
downgrades with both named - until an incident or decision recorded
after the second reversal is cited on it. Rewording does not clear a
wire that matches salient terms.

## The fix-loop shape summons the investigation

The stop hook reads the session's own timeline: one command failing
three or more times with edits between draws a single notice naming
the investigation workflow - reproduce first, bounded hypotheses,
evidence per fix - unless an incident shows the loop is already open.
Counts only, never command text.

## Dormancy with demand is the alarm

The demand-vs-use census: the doctor pairs what the record demanded
with what fired, per capability family - investigation, learning,
verification, criteria, planning, assumptions, independent-check, and
(when the tree holds database files) db. Dormant machinery with
standing demand is named; idle is health; demand counts open work
only. Demand meets its moment too: a work item entering active
without a pre-registered criterion is named at the write, an incident
opened without stated assumptions carries its remedy, and the push
preflight renders every dormant family as a judgment finding - a
person decides, nothing blocks, nothing passes unseen.

## The learnings travel

`docs --emit-agentsmd` renders the project's top laws as a bounded
Learnings section: a hookless agent reads AGENTS.md, and a law that
never reaches it governs nothing.

## Verifying

- `python -m unittest discover -s tests` - run in shards
  (`scripts/dev/run_with_flaky_retry.py` retries only registered flakes).
- The cross-platform proof: godmode-verify run 33442046668 - nine of
  nine jobs green on the commit this release ships.
- `godmode doctor` - calibration and utilization blocks render.
- `godmode changelog check` - fragments folded at release time.
- `godmode version --reconcile` - every surface answers 0.3.8.
