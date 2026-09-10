# Godmode v0.3.23

Field report 27 arrived the morning 0.3.22 shipped, from the same project.
Two of its three cons were new and one was a closure that never took. All
three are behaviours here, each with a test that failed against 0.3.22.

## What changed

- **A filter is not the run.** "Final suite exit 0" had been graded
  `verified` because the cited `grep` over a log exited 0. A run-shaped
  claim whose cited command ends in a read or filter tool now stays
  `observed`, and the record names the filter and the run that must be
  cited instead.
- **A closure that names no open ask is refused.** Typing the ask's words
  as the subject matched no digest, closed nothing, and was accepted
  silently, so the ask kept nagging. The closure now refuses with every
  open ask listed as `ask:<hex> '<its words>'`, paste-ready.
- **`privacy --repo`.** The docs-privacy pass a reviewer does by hand with
  `git ls-files` and grep: emails, home paths, private or host-positioned
  IP addresses, secret shapes, and oversized tracked files, each named by
  path, line and kind with the value masked.

- **A verdict on an unread repository is named.** Self-observed the same
  morning: two repositories were judged from README and file tree and the
  gate said nothing, because the prose had no number or done-verb. When a
  prompt named a GitHub repository, the reply judges it, and no source file
  of it was fetched this session, Stop names the repository and the count.
- **Numbers must be in the cited lines.** A number-bearing claim cited to
  lines that carry none of its numbers is graded unsupported: the triage a
  cite-checker runs before reading, taken from reading one.

- **Process sentences are not claims.** "Checkpoint complete" and "Claim
  recorded" describe the ledger, not the work (report 28).
- **`remember --kind lesson --subject --guard` records**, as the repair
  skill shows; the guard is the lesson's value when no other is given.
- **A tree written by a command is named as such.** The Stop turn-diff line
  now separates files a command wrote from files Edit or Write touched;
  a mid-run sync that rewrote a skills tree had read like ordinary edits
  (report 29).

## Known limits

- `privacy --repo` reads text suffixes under 2 MB; binaries are judged by
  size only. Placeholder domains and no-reply mailboxes are skipped by
  rule, so a real address at a placeholder-looking domain is not named.

## Verifying

- `tests/test_field_report_27.py` (6 tests) fails against 0.3.22.
- `python -m unittest` across eight shards, `tests/test_repo_privacy.py`,
  `tests/test_docs_lint.py`, `tests/test_changelog_gate.py`, and
  `godmode integrity --base HEAD~1` green before the tag.
