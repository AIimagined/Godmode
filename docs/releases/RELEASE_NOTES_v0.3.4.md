# Godmode v0.3.4

The loops maintain themselves.

v0.3.3 delivered advisories to the right audience; the day after, the
maintainer session and four live hosts stress-tested every loop, and this
release is that feedback closed. Fourteen fragments, each traceable to a
live session's finding.

## The law loop learns to run itself

`law debrief` closes the amendment loop: per law it measures delivered,
cited, and recurred-after-delivery, and triages recommendations - promoting
a ready candidate stays autonomous behind the ladder, while amending or
retiring a guard needs the operator, because a guard is reviewed prose.
The report states its own read window and stopping reason, and receipts
itself counts-only, so `law show` and the session brief now carry the
debrief gauge (last receipt, records since, stale). `law amend --law
--guard` executes a recommendation with newest-wins making it the law, and
a candidate cluster can finally be dismissed - retiring its subject removes
it from `law candidates`, the exit that is not promotion.

The detector sharpened on its own live noise: an instruction marker now
needs an imperative verb within five tokens, every matching marker is
checked rather than only the first, and the three chat-noise captures that
prompted the rule are dismissed on the record.

## The posture loop reads the era the gate actually ran

`roi --digest` gains an enforce section: asks and silences by category
from real enforcement records, an `ask_only` re-proposal computed over
both eras, and the drift against the installed policy. Its first live run
proposed one addition and two removals from a night of 209 actual asks -
proposal only, the operator still edits the file.

## Fixes the night's field reports demanded

- SessionEnd's budget rises from 3s to 10s: a live exit on a large archive
  was cancelled mid-checkpoint, and the old bound's reason - Codex's
  3-second budget - is moot because Codex ignores plugin-bundled hooks.
- The Codex project fallback invokes machine-PATH `python`, not `py -3`:
  the launcher resolves to the user-local interpreter, which Codex's
  sandbox accounts are denied.
- The charter never mints rules from the generated Code of Law: the
  ADVISORY cap still produced twenty rules the checkability review then
  demanded per-law decisions for; the law file is delivery, not source.
- The OpenCode shim with no GODMODE_PLUGIN_ROOT warns once and allows
  instead of refusing every tool call (a live session was bricked down to
  `dir`); a configured gate still fails closed, and the shim runs under
  Node as well as Bun.
- A downgraded claim superseded by a later claim on the same subject
  leaves `status remaining`; the bare-host control in the brief-echo pins
  strips every host marker; the landing page installs all four hosts as
  peers; the action description fits the GitHub Marketplace cap; and
  `tests/KNOWN-FLAKY.txt` names batch-load flakes with their justifying
  lesson while the retry runner reruns only registered failures, isolated,
  reporting every retry.

## Verifying

- `python -m unittest discover -s tests` - run in shards
  (`scripts/dev/run_with_flaky_retry.py` retries only registered flakes);
  2,737 tests across five shard runs at the release commit, zero failures.
- `godmode bindings` - every generated manifest current, 0 drifted.
- `godmode version --reconcile` - every surface agrees.
- `godmode changelog check` - satisfied; fourteen fragments folded.
- `python -m unittest tests.test_law_debrief tests.test_s11_loops
  tests.test_s11_roi` - the loops' own pins.
