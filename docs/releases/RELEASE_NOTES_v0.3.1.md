# Godmode v0.3.1

The hooks run where they are loaded. Three field reports, one day.

v0.3.0 shipped one `hooks/hooks.json` that every host discovers and only
Claude could read. Codex and Grok reported it from opposite sides on the
same evening; a Claude session on another project reported what the brief
reads like when nothing has been recorded. Eight changelog fragments fold
into this release - three added, five fixed - each written before its
commit, per the changelog gate this repository enforces on itself.

## One hooks file, parsed by every host

Every entry in `hooks/hooks.json` is now one shell-form command string,
`python "${CLAUDE_PLUGIN_ROOT}/hooks/..."`. Claude substitutes the root
natively; Codex honours it as a documented compatibility alias; Grok
expands `${VAR}` and sets the alias, per its own hooks guide. The
`command` + `args` pair it replaces was Claude's exec form only: Grok took
the bare `python` token as a path beside the file and failed every hook
open in 0 ms, so the gate never ran; Codex refused the shape and its
`/hooks` panel listed zero. The dedicated `.grok-plugin/hooks.json` that
carried Grok's documented shape was never read - Grok's plugin guide lists
`hooks/hooks.json` as the only hooks component a plugin holds - and is
gone. Codex's and Grok's tool names ride the shared PreToolUse matcher;
`SessionEnd` fits Codex's 3-second budget; `PreToolUse` takes the 8-second
bound Grok's fail-open timeout needs. Cursor's generated manifest takes
the same shape.

Codex then reported the second half: with an unmodified Codex payload -
Claude's `Bash` tool name, none of Grok's or Claude's environment markers -
the detector called it Claude, answered R3/R4 with `ask`, and Codex, which
treats `ask` as a failed hook, ran the command. The detector now reads the
two markers Codex documents as its own, `PLUGIN_ROOT` in the environment
and `turn_id` in the payload, in both host chains. Codex receives `deny`
with the staged-capability remedy, the way the Grok contract already folds
it; two tests run the hook on the documented payload with no override.

The decision body carried every host dialect's keys in one object, on the
assumption that a host ignores keys it does not read. Codex's reference
says a legacy `decision` field is "parsed but not supported yet" and makes
it mark the hook failed and continue - a deny turned into a fail-open. A
positively detected host now receives exactly the keys its own contract
documents; only an undetected host still receives the union. On Claude
Code the live test of this release is on the record: a `git push --force`
in a real session was refused with the R5 reason and `git status` ran
silently (refusal records 4001 and later).

What this release does not claim: a live, chronicled proof that Codex's or
Grok's runtime calls the gate. `hooks probe` self-injects and proves the
script, not the wiring. The README host table still says which hosts are
proven; it changes when a `HARD` proof record exists for that host.

## The brief, read by an agent that has not recorded anything

A Claude session on another project read the observe-mode line -
`r5=0 r4=0 r3=12 r2=328` - as "340 would-have-refused ops, none mapped to
a real risk", and an eleven-day-old checkpoint as the project's state
while `docs/STATE.md` held the current one. The observe line now leads
with the count that means risk, zero stated - `0 would-have-denied at
R4/R5 - none` - and calls the rest what they are: `would-have-asked at
R2/R3 (friction, not risk)`, naming the `ask_only` posture `roi --digest`
proposes to trim them. When a project keeps its own state document
(`docs/STATE.md`, `STATE.md`, `HANDOVER.md`, `HANDOFF.md`, `RESUME.md`,
`STATUS.md`, root or `docs/`), the checkpoint entry carries `resume_doc`
and a stale checkpoint's note says to read that file first.

The earlier half of the same report, shipped after v0.3.0 was tagged:
record roles (lessons, state, sprint truth, decisions, inventory) compile
to ADVISORY at most, which took that project's unattested HARD count from
512 to 94; the brief carries the checkpoint's `age_days` and a note past a
week; `ask_only` in the authorization policy is the focused posture the
digest proposes from what was observed; PreCompact and SessionEnd are
wired in Claude's manifest, and a session that ends without a summary
writes a counts-only checkpoint.

## Two checkers that read their own records too literally

`status remaining` listed every obligation record whose status was not
closed, so an obligation closed later through `remember --status closed`
stayed on the list beside its own closure, and `retired` was not a word it
knew. The latest record per subject is now the obligation's state. The
absorption checker compared an import verdict to its five words exactly
while the sweep writes the reason beside the verdict - `n-a - different
surface (postgres table)` - which graded thirteen fully judged items as
half judged; the checker now reads the first token as the verdict and
keeps the text after it on the record as the reason.

## The Code of Law: the loop that maintains the project's own rules

Nine field reports in one day agreed on the mechanism and on the gap: the
one feature that changed outcomes was a rule written down before the work,
and the one line every report repeated was "claim still unused". This
release ships the loop that closes both. `godmode law compile` folds every
guarded lesson into a bounded `GODMODE-CODE-OF-LAW.md` - guard first,
archive provenance beside it - and a wrapper skill carries it to hosts
where hooks are weak; the file is a bound authority document, so the
charter, `attest` and the required-sources counter consume it unchanged,
and the SessionStart brief delivers the top laws inside its budget. A
correction-shaped prompt becomes a law candidate (keywords and a digest,
never the sentence); candidates cluster so repetition increments one
counter; `law promote` writes a reviewed guard and refuses below three
distinct sessions of recurrence; delivery receipts record which laws each
session was shown, and a law no receipt has named shows as dormant. The
claim gate reaches the message boundary: a Stop hook names any
claim-shaped sentence in the turn's final text that has no record behind
it - advisory, bounded, silent on prose and on the host's re-fire. An
enforce-mode ask is chronicled, counts only, so tuning can learn from
what the operator actually approves; the observe notice states its own
age; a claim resting on a test file that was read but not run grades
hypothesis until the run stands beside it; and `init --roles` generates
the law file on day one in its honest empty form.

## Also in this release

`NonFinite` stops an experiment on a non-finite metric; VS Code Copilot is
detected by the install path it actually presents; `experiment holdout`
runs a controlled holdout; the structure index carries an L2 call graph
(`calls`, `dependencies`, edge count) beside the L1 outline; an opt-in
PostToolUse hook runs the docs lint or swallow scan over an edited file
and returns an advisory, silent unless `post_edit_quality: true`.

## Verifying

- `python -m unittest discover -s tests` - 2755 tests across four shards
  at the release commit (`scripts/dev/run-suite.ps1`).
- `godmode bindings` - every generated manifest current, 0 drifted.
- `godmode version --reconcile` - ten surfaces agree, tagged tree checked.
- `godmode changelog check` - satisfied.
- `godmode claim --scan` - public-surface claims covered.
- `python -m unittest tests.test_host_manifests tests.test_grok_host_contract tests.test_hostevent` -
  the shared-file shape, the matcher union, and Codex detection on the
  documented payload.
