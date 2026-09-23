---
name: godmode-skill-eval
description: Score a drafted or hand-edited skill's authored routing rows against the committed baseline, and confirm its bundle validates, before it ships or is enabled by default. Use when a new or edited skill needs its overlap scores measured and its ratchet checked before landing. Not for authoring a brand-new skill, and not for judging whether a change is correct.
---

# Godmode Skill Eval

## Outcome

Before a drafted or edited skill starts routing live traffic, prove its structure validates, its routing rows score the way its author intends against the committed baseline, and its behavior assertions actually execute - rather than shipping on the strength of a read-through.

## Use

- A skill was just forged (`godmode-skill-forge`) or hand-edited and needs checking before it lands.
- A skill's positive/near-negative routing rows need real overlap scores, not an eyeballed guess at whether they will hold.
- Before raising the committed routing baseline, confirming the whole suite shows no regression first.
- After editing a skill's description or positive examples, confirming sibling skills' near-negatives still reject it.
- Distilling a new skill's routing rows from one already-verified task trace, then scoring the draft the same way.

## Do Not Use

- Creating a new skill from a proven, repeated capability gap - that is `godmode-skill-forge`; this skill only validates and scores what forge (or a hand edit) already produced.
- Reviewing a pull request or diff for correctness bugs - that is a code review, not a routing or behavior check.
- Reading a skill's prose and judging by feel whether it will route correctly - every claim here is scored by a command, not asserted.

## Deterministic Execution Flow

1. **Validate the structure.** `godmode skill validate --path skills/<name>` - reports `valid`, `positive_cases`, `near_negative_cases`, `assertions`, and the file's line count.
   - Fallback: `valid: false` names the reason (missing `agents/openai.yaml` or `godmode-evals.json`, malformed frontmatter, or too few routing rows). Fix that before any scoring step - a structurally invalid skill cannot be scored meaningfully.
2. **Lint the bundle.** `godmode skill lint --path skills/<name>` - four structural facets: `scope` (an explicit trigger in the description), `delivery` (every backticked term the description promises appears in the body), `safety` (no injection-shaped content), `bundle` (every file is reachable from a link, nothing bundled is orphaned).
   - Fallback: a `safety` finding is never waived. A `bundle` orphan is fixed by linking the file from `SKILL.md` (or `PURPOSE.md`) or removing the file, never by ignoring the facet.
3. **Read the whole-suite verdict before touching anything.** `godmode evals --brief` - prints `evals-sound` or `evals-unsound: charter=..., ranking=...`. A pre-existing, unrelated failure (a stale charter or ranking snapshot from role-document drift) is not this skill's regression to fix; only a routing or behavior-assertion change this pass introduced is in scope.
4. **Score the drafted skill's routing against the committed baseline.** `godmode evals --ratchet --brief` - runs every skill's authored `godmode-evals.json` rows through the same offline lexical router and compares the scores to `evals/baseline.json`; prints `clean` or names every skill whose score fell.
   - Fallback: a named regression on a *sibling* skill (not the one just drafted) means the new suite's vocabulary bled into that sibling's near-negative rows - tighten the new skill's description or positive examples, never the sibling's rows.
5. **Check the harness is deterministic.** `godmode evals --determinism --brief` - runs the offline routing harness twice and prints `deterministic`, or names any prompt whose route differed between the two runs.
   - Fallback: the router is a pure function of the suite files on disk, so a nondeterministic result means something outside the suites leaked in (an unordered directory walk, an environment variable). Investigate the leak; never re-run hoping for agreement.
6. **Only once steps 3-5 are all green, raise the floor.** `godmode evals --write-baseline --brief` - raises the committed routing-score baseline to the current scores; refuses outright on any regression. Run it immediately after a `--ratchet --brief` that itself printed `clean`, so the new floor is exactly the state just proven clean.
   - The floor exists once per mode. `godmode evals --write-baseline --withhold-memory --brief` records the score with this project's lessons and compiled law withheld from the subject brief - what the skill does on its own words - in its own block of `evals/baseline.json`. The two modes are measurements of different things and are never compared, so raise each floor with its own run and read each verdict against its own block.
7. **Ship only after every step is green.** The drafted skill is committed under `skills/` (and is therefore enabled by default) only once steps 1, 2, 4, and 5 all pass for it, and step 6 has recorded its baseline.

Read [PURPOSE.md](PURPOSE.md) for the archive evidence this skill exists to close.

## Must Not

- Never run `godmode evals --write-snapshots` to turn a red routing case green. `--write-snapshots` accepts the *current* routing outcomes as the new fixture; run against a failing draft, it erases exactly the drift the eval exists to catch instead of fixing the drift.
- Never run `godmode evals --write-baseline` while `--ratchet` reports a regression - that enshrines the regression as the new floor instead of fixing the wording that caused it.
- Never run `godmode evals --write-snapshots --withhold-memory`; it is refused - use `godmode evals --write-baseline --withhold-memory` instead to record that mode. The committed fixtures record routes taken with memory present, and freezing a withheld run over them would redefine what the fixture means and make every later ordinary run read as drift.
- Never hand-edit `evals/fixtures/*routing*.json`, `evals/baseline.json`, or a skill's `godmode-evals.json` scores to match a wanted outcome; every number in those files comes from running the harness, never from typing the answer you want.
- Never enable a skill by default (leave it committed under `skills/`) with a `skill lint` `safety` finding outstanding, or before its own `godmode-evals.json` carries at least two positive and two near-negative rows; fix the finding or add the missing rows first, then re-run step 2.

## Acceptance

- `godmode evals --ratchet --brief` prints `clean` for the drafted skill and every sibling, with no hand-edited fixture behind it.
- `godmode evals --determinism --brief` prints `deterministic` for the same suite set, twice, from the files on disk alone.

If an assertion cannot be proved, report the unmet assertion and the next safe action rather than the outcome it was meant to prove.
