# Godmode Host Adapter

`godmode_session_hook.py` is a bounded stdin/stdout adapter for hosts that support
lifecycle or pre-action hooks. Claude Code registers only its non-blocking
`SessionStart` path through `hooks/hooks.json`. That path is silent until the current
project has been explicitly initialized, then emits a structured continuity brief as
additional context. It does not read the Claude transcript; neither does `pre-compact`
or `pre-action`.

Supported explicit events are `session-start`, `pre-compact`, `session-end`, and
`pre-action`. Lifecycle checkpoints accept only the structured fields `summary`,
`status`, `next`, `hypothesis`, `outcome`, and `evidence`; unknown fields, prompts,
and messages are ignored. `session-end` is the one exception: it also reads
`transcript_path`, if the host supplies one, for a best-effort, counts-only
measurement pass (tool names from a closed enum, command shapes, and token
totals from the transcript's own usage blocks) - never transcript content, and
a missing or unreadable transcript is recorded as a stated gap rather than an
error. Pre-action mode classifies an exact operation and denies protected work
unless a matching one-use capability is supplied.

## The pre-tool gate

`PreToolUse` is registered for mutating tools (`Bash`, `PowerShell`, `Write`,
`Edit`, `NotebookEdit`), but the script the host actually calls is
`godmode_gate_fast.py`, not `godmode_session_hook.py` directly. The fast gate
is a zero-import table lookup against `gate_table.json`: a command whose every
segment head lands on a vetted, host-parity, read-only floor (`git status`,
`git log`, `git diff`, ...) is allowed silently, in-process, with no
subprocess spawned. Anything else — a real mutation, an unrecognized command,
a fenced tool (`Edit`/`Write`/`NotebookEdit`), or any ambiguity the table
can't resolve — escalates: the fast gate re-feeds the exact request bytes to
`godmode_session_hook.py pre-action` unchanged and mirrors its stdout, stderr,
and exit code verbatim. Every ambiguous path resolves to escalate, never to
allow; the fast gate never itself decides `ask` or `refuse`.

On escalation, the full hook derives an operation from the tool payload,
meters the call, and answers in the host's own contract: silence allows, and a
refusal returns `permissionDecision: "deny"` with the reason. Three things can
refuse:

1. a protected operation with no matching one-use capability;
2. a declared run ceiling already reached;
3. a skip pattern — three mandated steps skipped this session.

This is the boundary that makes `tool_call_interception` real. `godmode hooks
probe` sends a marker operation through this exact path, this hook denies it
unconditionally, and records the denial (`godmode_hookproof.py`). `godmode
hooks status` reads that record back and reports one of five levels, never a
claim the evidence cannot back: `HARD` (a fresh, unexpired, session-anchored
proof, unsuperseded — the only level that may back an "enforced" claim),
`DEGRADED` (a proof that WAS provably fresh but is now superseded — the hook
came down, a probe failed, a real call's payload could not be parsed — or its
`hook_version`/file hash drifted, or its TTL simply elapsed), `PARTIAL` (the
hook is structurally discovered/registered — the manifest wires it — but no
fresh proof exists), `SOFT` (the skills+CLI layer is installed for this host
with no hook proven at all — the true floor on every host this project ships
to today except a freshly probed Claude Code), or `UNAVAILABLE` (no
compatible boundary at all). A `DEGRADED` grade carries a persistent, named
reason in both `hooks status` and the session-start brief until a fresh probe
passes — never a silent downgrade.

**Costs and limits, stated.** `hooks.json` sets an 8s timeout on `PreToolUse`
(`SessionStart` gets 10s, `UserPromptSubmit` gets 30s). Measured directly
against `godmode_gate_fast.py` on Windows (2026-08-14, `python
hooks/godmode_gate_fast.py < payload.json`, 10 timed runs after one unmeasured
warm-up, median of the sorted sample): a fast-path allow (`git status`) has a
median wall time of **90.3ms** (range 82.8-108.2ms) — the table lookup plus
one Python interpreter start, no subprocess. An escalating call (`git push
--force origin main`, denied) has a median of **468.6ms** (range
334.6-514.6ms) — the fast gate's own startup plus the subprocess spawn of
`godmode_session_hook.py pre-action`, which resolves repository identity via
several `git` calls. Narrowing or widening the `PreToolUse` matcher narrows or
widens the meter with it: as shipped, the `tool_calls` ceiling counts mutating
calls, not every tool call. Tokens remain the host's figure and are labelled
`declared`, never `measured`, in the ceiling report. An uninitialized project
is never blocked, and an internal failure never blocks the host — a broken
gate must not brick a session.

The remaining events are not registered automatically because enforcement guarantees
vary by host. The adapter creates no listener, watcher, daemon, or background process.
A host must invoke a gate event and honor its exit code for enforcement to exist.

## The git-hook backstop (host-independent)

Every boundary above only fires while a specific host is driving the terminal.
`godmode hooks install --git` writes real, project-local git hooks
(`pre-commit`, `pre-push`, `pre-rebase`, `post-checkout`) that call
`python "<resolved godmode.py>" guard --git-hook <name> --json` and fail
closed on a protected verdict — a second boundary at git's own chokepoint,
independent of whatever (or nothing) invoked git. It is opt-in: install
refuses unless the project has declared `{"git_backstop": true}` in
`.godmode-authorization-policy.json`, and the declaration is tighten-only
once observed (`declared_gate_ratchet`). A pre-existing, non-godmode hook is
never overwritten — install skips it and reports it as `skipped_foreign`.

**What each hook can and cannot see, stated plainly:**

- `pre-push` reads the ref-update lines git writes to its stdin and can run
  `git merge-base --is-ancestor` on the shas it was given. It cannot see the
  `--force`/`--force-with-lease` flag itself — git never passes it. A
  non-fast-forward update is treated as the force-push surrogate this hook
  can honestly detect. Stdin that cannot be read, or that contains a line
  that fails strict 4-field parsing, is never folded into "nothing to
  push": under declared policy it fails closed (blocked, chronicled);
  undeclared it stays advisory-only — a genuinely empty stdin, with no
  lines at all, is the single case this hook treats as "no ref updates."
- `pre-commit` sees only the staged file-name list, never diff content. It
  can detect a pinned evaluator about to be committed, nothing else.
- `pre-rebase` receives at most an upstream ref and a branch name and cannot
  tell whether the commits it would rewrite were already pushed anywhere, so
  every rebase is treated as protected, uniformly, rather than guessed at.
- `post-checkout` runs AFTER git has already switched the working tree — a
  nonzero exit here can never prevent the checkout, only report a problem
  loudly (a pinned evaluator's on-disk content no longer matches its pinned
  hash). `hooks status --git` states this boundary explicitly, per hook.

A protected verdict under declared policy still honors a one-use capability
staged with `godmode authorize stage` — the same escape valve every other
R5-shaped refusal in this product already answers through, never a second,
unconditional wall. `godmode hooks status --git` distinguishes a real
godmode hook from an absent one, a git `.sample` template (never counted),
and a foreign hook (never overwritten) — and, for a hook it does own,
`godmode` (content matches what was installed) from `godmode-modified`
(edited since). That match is computed by re-hashing the file's actual,
current on-disk body (everything except its own digest header line) and
comparing it against what that same header line claims, every time status
runs — never by recomputing an independent "ideal" hash from the hook's
name and path alone, which would (and once did) miss a hand-edit entirely
as long as the header line itself was left untouched.
`godmode hooks verify --git` proves the mechanism live: it builds a
throwaway bare-remote-plus-working-repo pair, installs the real `pre-push`
hook into that scratch repo alone, attempts an ordinary unauthorized push,
and only on a confirmed block (exit code AND unchanged remote ref, never
inferred from silence) records a CX-1 proof record with `host="git"`.
Uninstalling (`hooks install --git --uninstall`) removes only the hooks this
module owns and is itself a chronicled, counts-only event; the
`git_backstop` declaration stays visible in `hooks status --git` regardless,
via the same tighten-only ratchet.

**Known, disclosed bypass.** `git push --no-verify` (and any client that
skips or reroutes hooks, e.g. `git -c core.hooksPath=<elsewhere>`) skips
every client-side hook including this one — git's own documented escape
hatch, not a defect here. The git backstop raises the floor for the
default/cooperative path; it is **not** an unbypassable wall for a caller
with ordinary git-CLI access. Only host-level interception (the CX-1/CX-2/
CX-3 adapters, where one exists for the host in use) closes that specific
gap. `godmode hooks status --git`'s own output states this same fact
(`known_bypass`) rather than leaving it only in this document.
