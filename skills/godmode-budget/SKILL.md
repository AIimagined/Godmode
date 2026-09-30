---
name: godmode-budget
description: "Account for what a session or a release spent and hold it to declared ceilings: check reported tokens, tool calls and seconds against the run ceilings, read the per-session spend series with its measurement gaps, fold burn beside gate activity per session and per release, and measure the brief budgets and verb timings locally. Use when a session is burning more than it should, a release cost more password rounds or suite reruns than planned, or a ceiling needs to be checked before more work is spent. Not for detecting a repeating retry loop, and not for release notes."
---

# Godmode Budget

## Outcome

Spend is read from local records and compared with declared ceilings before
more is spent, the series of past sessions is shown with its unmeasured gaps
stated, and a release's burn is one table of counts beside the gate activity
it paid for, with no causal claim attached.

## Use

- A session's token, tool-call or wall-clock spend looks out of proportion to the task.
- A run ceiling is declared and the current spend must be checked against it before continuing.
- A release took more password rounds, preflight minutes or suite reruns than planned.
- The brief budget or a verb's timing needs a local measurement, not a guess.

## Do Not Use

- Detecting and cutting off a repeating fix-and-retry loop - that is `godmode-loop-warden`.
- Checking fragments or building the release notes - that is `godmode-changelog`.
- Scoring a skill's routing against its baseline - that is `godmode-skill-eval`.

## Deterministic Execution Flow

1. **Check the spend against the ceilings.** `godmode ceilings --spent tokens=<n>,tool_calls=<n>,seconds=<n>` - the reported spend against every declared run ceiling; a breached ceiling is the stop, not a warning.
2. **Read the series, gaps included.** `godmode trends --sessions 20` - per-session token, tool-call and test-run counts as a time series; an unmeasured session reads as a gap, never interpolated.
3. **Fold burn beside the gate.** `godmode roi --sessions 20` - counts only: burn beside refusals and asks, no causal claim; `godmode roi --releases` - per release tag range: password rounds, refusals by category, preflight runs and minutes, suite runs repeated for one HEAD.
4. **Measure what a guess would have stood in for.** `godmode benchmark` - brief budgets and timings, locally; `godmode metrics --window 500` - whether the product works, from local records only.
5. **Record the decision the numbers support.** `godmode remember --kind decision --subject "budget:<session or release>" --value "<what is cut, kept or raised, and why>" --evidence seq:<the ceilings or roi record>`.
   - Fallback: a ceiling breached with no decision recorded stays a breach; the next session start names it until a decision cites it.

Read [PURPOSE.md](PURPOSE.md) for the archive records this skill exists to close.

## Must Not

- Never raise a ceiling to make a breach disappear; instead record the decision that raises it, with its reason and evidence.
- Never fill an unmeasured session with an estimate; instead report it as the gap the series shows.
- Never read a burn count as a cause of a gate outcome; instead report the two side by side as the counts they are.
- Never quote a timing without a local measurement behind it; instead run the benchmark and cite its record.

## Acceptance

- Every ceiling breach on the record has a decision citing it.
- The reported series names each unmeasured session as a gap.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
