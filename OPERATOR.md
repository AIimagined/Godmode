# Operator Profile

Who operates this project and what they authorize.

This repository is developed under a small set of standing directives that
apply regardless of which session or agent is doing the work.

- Godmode owns its capabilities natively: stdlib only, and never a
  third-party tool depended on at runtime.
- Execution is sequential: no parallel agents, one task worked at a time.
- Commits favor conventional-commit messages grouped by deliverable family,
  with a changelog fragment per change.
- Internal planning artifacts — checkpoints, working notes, sprint
  specs — are proprietary and must never reach the shippable surface.
  `capabilities.json` in particular is scoped to ids and neutral one-line
  statements only, with internal prose left out.
- Release and push decisions remain the operator's explicit call, and are
  never inferred from a green suite alone.
- Writer trust: `remember`, `plan --close`, `version`, `skill
  retire`, and `session open --role checker` accept `--as-operator` to
  claim a write as the human operator - outranks agent/checker/hook
  records for that subject and is exempt from the single-writer close
  guard. A bare flag is not a credential: it is verified against
  `authorize setup`'s password when one is configured (piped in via
  `--password-stdin` - the only non-interactive path, e.g. from a file or
  a secret manager - or typed at an interactive prompt), else an
  interactive y/N confirmation. With a password configured but neither a
  terminal nor `--password-stdin` available, the write is refused outright
  rather than silently downgraded to `agent`.
- `session open --role checker` declares a session's role, but `checker`
  is OPERATOR-GRANTED, never self-declared: it requires the same
  `--as-operator` verification above, and is refused with a remedy message
  otherwise. A granted session is chronicled with `role_granted_by:
  operator` and `writer: operator` on the session record itself, and its
  session id is exported as `GODMODE_SESSION` for the rest of that
  process. A later write only reads as `checker` when it names THAT exact
  session id AND that record carries the operator grant
  (`Chronicle._chronicled_session_role`) - a different session's id, an
  unverified `checker` session, or a hand-set env var alone all mint
  nothing. The grant is also bound to the process that opened it: naming
  someone else's genuinely-granted session id mints nothing either, because
  the record's own agent identity has to match the caller's. "Operator-
  granted, never self-declared" holds literally only once `authorize setup`
  has a password configured; without one, the verification above falls
  back to an interactive y/N that any process holding the terminal (a pty)
  can answer for itself, so a configured password - not the prompt - is
  the real boundary.

## Unattended gating policy

Every gate decision applies one of two rows, depending on whether an
operator is presumed present to answer an `ask`:

- **Attended** (the default): the refuse-outright floor is R5 only; a
  staged capability keeps the full configured TTL; `authorize stage
  --without-preflight` is available on the operator's own say-so.
- **Unattended**: the refuse-outright floor drops to include R4 too - an
  ask nobody is there to answer becomes a deny instead of a stall; a
  staged capability's TTL is halved (never below the 10-second floor
  `issue --ttl` itself validates against); `--without-preflight` is
  refused outright, since nobody is present to accept that risk.

`godmode operator --policy` prints both rows and names which one is
active. `godmode_sentinel.attended()` decides which row applies, in this
order - the first signal that answers wins:

1. `GODMODE_ATTENDED` - an explicit override. `0`/`false`/`no`/`off` is
   unattended; anything else present is attended. Always wins over every
   other signal, including `CI`. This is also the way back out of a
   refusal the unattended row issues: run the same command from an
   attended session, or set `GODMODE_ATTENDED=1` if one truly is one.
2. `CI` - set to anything non-empty by every CI system's own convention.
   Nobody is watching a CI run. (Any module built on `tests/_host_env.py`'s
   `scrubbed_environment`/`scrubbed_env` strips both `CI` and an ambient
   `GODMODE_ATTENDED` before pinning `GODMODE_ATTENDED=1` for itself - opt-in
   per module, not suite-wide; `tests/test_attendance_scrub.py` statically
   scans for hook-spawning modules that have not opted in - direct spawns
   and spawns through a helper's parameter, not every possible indirection,
   and never an in-process `attended()` call with no subprocess at all.
   `.github/workflows/godmode-verify.yml` sets `GODMODE_ATTENDED: "1"` in
   the verification job's own env as a second, job-wide layer for the
   modules that the scan still leaves unscrubbed, since the suite runs attended
   by design on that job's `workflow_dispatch` trigger. A test that wants
   to exercise the unattended row asks for it explicitly, through
   `scrubbed_environment`'s `extra`.)
3. `permission_mode` - the host payload's own declared mode. Claude Code's
   `auto`, `dontAsk`, `bypassPermissions` mean an ask on this call is
   answered by the host's own classifier, denied silently, or skipped
   entirely - never by a person - so this tier reads the same signal the
   older ask-to-deny fold already trusted for the identical reason.
   `default`, `plan`, `acceptEdits` still prompt a person and are not
   evidence either way.
4. `session_type` - the host payload's own declaration (`unattended`,
   `background`, `scheduled`, `headless`, `batch`, `cron`, `ci` are
   unattended; `attended`, `interactive`, `foreground` are attended). No
   in-tree host adapter sends this field today; it is read in case one
   ever does.
5. An interactive TTY on stdin - a positive signal only, since a host's
   own subprocess pipe is never a TTY even when a human IS driving it.

The default, when nothing above resolves either way, is **attended**:
piping a payload over stdin is how every host invokes a hook regardless of
whether an operator is present, so a TTY's absence alone proves nothing.
