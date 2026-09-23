"""Stable Godmode runtime constants."""

from __future__ import annotations

import hashlib
import os
import shlex

# Tools that read and cannot write. Named rather than inferred: a tool
# absent from this set is treated as capable of mutation and pays the full
# check.
#
# One owner because two had the same six names as separate literals - the
# gate hook deciding what skips the full check, and the Claude adapter
# deciding what an event reports as a read. They agreed by coincidence, and
# a disagreement about what can mutate is not the kind of drift worth
# discovering from behaviour.
READ_ONLY_TOOLS = frozenset({
    "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite",
    # Host control tools (2026-09-10): they carry no operation text and
    # touch no file or shell - stopping a background task, reading its
    # output, arming a monitor, loading a tool schema, asking the operator a
    # question. The gate refused `TaskStop` as "Operation description cannot
    # be empty", which is the fail-closed answer to a call that needed none.
    "TaskStop", "TaskOutput", "Monitor", "ScheduleWakeup", "ListAgents", "ToolSearch",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "Skill", "SendMessage",
    "NotebookRead", "PushNotification", "CronList",
})

# U-V2 disposition register vocabulary. It lives here rather than in
# `godmode_register` because two modules need it and neither may import the
# other: `godmode_invariants` is deliberately dependency-free so
# `godmode_chronicle` can import it without a cycle, while `godmode_register`
# imports `godmode_chronicle` - so invariants -> register would close exactly
# the loop that dependency-freedom exists to prevent.
#
# The previous arrangement kept two copies in step by hand with a test
# asserting they still agreed. This module has no runtime imports at all, so
# both sides can read one definition and the drift becomes unrepresentable
# rather than merely detected.
REGISTER_STATES = (
    "established", "superseded", "refuted", "worse-than-baseline",
    "matched-baseline", "rejected-precedent", "open",
)
REGISTER_EVIDENCE_PREFIXES = ("witness:", "verdict:", "file:")

AGENT_ENV = "GODMODE_AGENT_ID"


def agent_id() -> str:
    """Which agent is writing: declared if the host set one, else derived.

    Lives here, in the module with no runtime dependencies, because both
    the chronicle (which stamps it on every record) and the fleet layer
    (which coordinates between agents) need it. Putting it in either one
    makes the other import it and closes an import cycle - deferring that
    import inside a function hides the cycle from the interpreter but not
    from the atlas, which reads imports statically and enforces the
    no-cycle invariant.

    **Only the host can truly separate concurrent agents, and this does not
    pretend otherwise.** Two undeclared agents on one project share this
    id; separating them requires `GODMODE_AGENT_ID`, and one honest
    identity per project beats a fabricated per-agent one.

    Derived from the state home rather than the process, because the gate
    runs as a fresh subprocess per tool call - anything process-scoped
    would give ONE agent a different id per record. Hashed and truncated
    because the id travels inside records that may be shared, and a raw
    path is local detail that should not leave the machine.
    """
    declared = os.environ.get(AGENT_ENV, "").strip()
    if declared:
        return declared
    seed = os.environ.get("GODMODE_STATE_HOME") or os.getcwd()
    return "agent-" + hashlib.sha256(
        seed.encode("utf-8", "replace")).hexdigest()[:12]


PRODUCT = "Godmode"
RUNTIME_VERSION = "0.3.28"
SCHEMA_VERSION = 1
ARCHIVE_DIRNAME = "godmode-state"
MAX_HASH_BYTES = 5 * 1024 * 1024
DEFAULT_CONTEXT_BUDGET = 1_200
DEFAULT_RECORD_LIMIT = 24

# Final review S2: the untrusted-content scan cap used to be two hand-synced
# literals (`godmode_attest._UNTRUSTED_SCAN_CAP`,
# `hooks.godmode_post_edit._TOOL_RESULT_SCAN_CAP`) plus a third hardcoded
# copy in `tests/test_untrusted_marker.py`, tied together only by a "must
# match" comment - exactly the duplication `BOOKKEEPING_SUBJECTS` and
# `checker_commands_match` exist to avoid elsewhere. `godmode_attest.py`
# imports this directly; `hooks/godmode_post_edit.py` cannot import runtime
# at module level (see that module's own docstring), so it keeps its own
# module-level literal but `tests/test_untrusted_marker.py` pins the two
# equal to this one value, so a drift on either side fails the test instead
# of silently reopening the >64 KB file-hash-laundering path (Task 7's own
# S2 fix: a flagged fetch saved to a file and cited as `file:`).
UNTRUSTED_SCAN_CAP_BYTES = 64 * 1024

EVENT_KINDS = frozenset(
    {
        "action", "assumption", "attestation", "branch", "change", "checklist", "checkpoint",
        "claim", "criterion", "perimeter", "ratchet", "database", "decision", "differential", "documentation",
        "incident", "invariant", "inventory", "lesson", "loop_halt", "loop_step", "metric",
        "obligation", "pattern", "pin",
        "checker_bond", "claim", "criterion", "perimeter", "ratchet", "database", "decision",
        "differential", "documentation",
        "improvement_proposal", "improvement_verdict", "skill_impact",
        # NS-2 + NS-10j (0.3.28 Plan 5 Task 2): a lesson graduates into the
        # compiled law only through a promotion a DIFFERENT actor approves
        # with an independent re-run - see godmode_lessons.py and
        # godmode_law.promote_candidate. `lesson_candidate` is the rotation
        # archive note (never a delete: the chain is append-only).
        "lesson_promotion", "lesson_approval", "lesson_candidate",
        "incident", "invariant", "inventory", "lesson", "metric", "obligation", "pattern", "pin",
        "plan", "receipt", "refusal", "request",
        # NS-11e (0.3.28 Plan 5 Task 7): `godmode forget`'s contradiction pass
        # writes this - never a finding about who is right, only that the
        # archive holds two active, disagreeing records on one subject.
        "review",
        # NS-13f (0.3.28 Plan 7 Task 5): a competing hypothesis with its kill
        # experiment; a kill result is a new record whose `of` names the first.
        "hypothesis",
        "session", "sprint", "upstream-diff", "verdict", "version",
    }
)

# Every subject an `action` record is written under. The kinds above are
# pinned; the action subjects were inline literals a reader matched by
# string, so a typo on either side was a silently dead rule (absorbed from
# a threat-detection harness's KnownActions census, 2026-09-10). A new
# subject is added here first; `tests/test_action_subjects.py` greps every
# writer and reader for the literal and fails on one this set lacks.
# Fix round 2 (Task 8 review, B3): the one canonical spelling of the
# per-edit bookkeeping subject `hooks/godmode_post_edit.py` writes, so
# every reader that must treat it specially - `godmode_loop`'s mutation
# reset, `godmode_watchdog`'s unattested-run counter,
# `godmode_metrics._action_transparency`/`_plan_adherence` - names it once,
# never a second, independently-typed literal that could drift from the
# writer's own.
EDIT_RECORD_SUBJECT = "edit-recorded"

# NS-8f: a PostToolUse scan finding instruction-shaped text in a tool
# result records the fact that it happened - a fact about the read, not
# about a step this trajectory took. Same reasoning as `EDIT_RECORD_SUBJECT`
# above, so it joins the same bookkeeping set rather than a second,
# independently-typed one.
UNTRUSTED_CONTENT_SUBJECT = "untrusted-content-seen"

# NS-8o: the retry runner's record of one isolated rerun of a registered
# flake. A retry is bookkeeping about the flake, never a step this
# trajectory took, so it joins the same excluded set rather than a fourth,
# independently-typed literal.
FLAKY_RETRY_SUBJECT = "flaky-retry"

# NS-10c: the retry runner's circuit breaker trips - a registered flake
# that failed isolated `n` times inside a window is parked, and skipped
# (never retried) until `cooldown_hours` past the park record elapses.
# Bookkeeping about the flake, same as `FLAKY_RETRY_SUBJECT` above, so both
# join the same excluded set rather than independently-typed literals.
FLAKE_PARKED_SUBJECT = "flake-parked"
FLAKE_READMITTED_SUBJECT = "flake-readmitted"

# NS-10d: one Stop/SessionEnd call's host-reported token usage. Bookkeeping
# about what the host declared, never a step this trajectory took, so it
# joins the same excluded set rather than a fifth, independently-typed
# literal.
USAGE_OBSERVED_SUBJECT = "usage-observed"

# C-9 (0.3.28 Plan 3 Task 3, fix round 1): one tick per real Stop pass
# while a builder done-bar check has a live escalation - `godmode_donebar
# .note_turn`'s own record, counted against to retire the escalation.
# Bookkeeping about the check, never a step this trajectory took, so it
# joins the same excluded set rather than a sixth, independently-typed
# literal. Task 3's first commit (6af4ff0) wrote this subject as a bare
# module-local string, invisible to every reader below and to the census
# `tests/test_action_subjects.py` runs to catch exactly that - the review
# that followed measured the fallout: an ordinary session that stops
# three times read as a blocking loop, and five stops with no attestation
# tripped the watchdog. Both were the record itself, never the operator.
DONEBAR_TURN_SUBJECT = "donebar-turn"

# NS-10h (0.3.28 Plan 3 Task 11): `godmode_cooldown`'s own record of one
# resurface of an idle anchor (an obligation or an operator ask this
# session's replies have gone quiet on) - the primitive NS-14e's bounded
# verify nudges will call later against its own anchors. Bookkeeping about
# an anchor's silence, never a step this trajectory took, so it joins the
# same excluded set rather than a seventh, independently-typed literal.
COOLDOWN_SUBJECT = "cooldown"
# NS-13d review H2: an edit the plan-first gate let through only because it
# was small. It does not enroll its file in the change, so a later large
# edit to that file is judged as a new file.
PLAN_FIRST_EXEMPT_SUBJECT = "plan-first-small-edit"

# NS-11e fix round 1 (review B, cadence / N9): the subject of the one
# bookkeeping `action` a real `godmode forget` pass writes about itself -
# counts and outcomes, never a narration. Nothing else could say when a
# pass last ran: a pass that found nothing eligible left no cold segment
# and no other trace, so `recurring` had to re-derive "is a pass due" with
# a full dry run on every call, and NS-11f's "scheduled (forget pass ran)"
# test had no evidence to assert on.
FORGET_PASS_SUBJECT = "forget-pass"

# Subjects that are bookkeeping ABOUT an action, never an operation or step
# the loop/watchdog/metrics detectors should reason about when they count
# repeated or unattested work (Task 7 review, finding C5: `EDIT_RECORD_SUBJECT`
# used to be the only member, checked by two separate `!= EDIT_RECORD_SUBJECT`
# exclusion literals - `godmode_watchdog.py`'s unattested-run counter and
# `godmode_metrics.py`'s `_action_transparency` - that would silently miss a
# second bookkeeping subject added later; Tasks 11 and 12 extend this same
# set instead of adding a third and fourth literal. `godmode_metrics.py`'s
# `_plan_adherence` (and `edit_records`) is deliberately NOT one of these
# sites: it *selects* `edit-recorded` specifically rather than excluding
# bookkeeping, and reading this set there instead would silently break plan
# adherence for every subject this set later grows to hold).
BOOKKEEPING_SUBJECTS = frozenset({
    EDIT_RECORD_SUBJECT, UNTRUSTED_CONTENT_SUBJECT, FLAKY_RETRY_SUBJECT, USAGE_OBSERVED_SUBJECT,
    FLAKE_PARKED_SUBJECT, FLAKE_READMITTED_SUBJECT, DONEBAR_TURN_SUBJECT, COOLDOWN_SUBJECT,
    PLAN_FIRST_EXEMPT_SUBJECT,
})

# Task 7 re-review (fix round 2, N1): `BOOKKEEPING_SUBJECTS` minus
# `EDIT_RECORD_SUBJECT` - the subset of bookkeeping that is a genuinely
# inert READ, never a run boundary. `edit-recorded` is bookkeeping too,
# but it is ALSO the one record that marks "something changed here" - the
# loop detector's own mutation branch (`godmode_loop._MUTATION_SUBJECTS`)
# and the watchdog's repeat-operation counter both rely on seeing it (a
# distinct operation digest, or a mutation-branch reset) to tell an edit-
# rerun-edit-rerun cycle apart from the same command failing the same way
# three times running. A detector that skips `edit-recorded` outright
# loses that separator - the watchdog regression this set fixes: skipping
# the whole of `BOOKKEEPING_SUBJECTS` in the repeat-operation counter made
# an ordinary edit-then-rerun cycle read as one unbroken repeated run.
# `untrusted-content-seen`, `flaky-retry`, and `usage-observed` carry no
# such "something changed" meaning - each is a read or an observation
# about a rerun, not itself the run boundary - so all three stay skippable
# everywhere `BOOKKEEPING_SUBJECTS` used to be read for that purpose.
RUN_INERT_SUBJECTS = BOOKKEEPING_SUBJECTS - {EDIT_RECORD_SUBJECT}

ACTION_SUBJECTS = frozenset(
    {
        # I-9: a subagent's hand-back message is data about work done, not
        # an operator ask - recorded as the lightweight fact that a relay
        # arrived, never minted as a request the operator is waited on to
        # close.
        "agent-relay-seen",
        "atlas-query", "capability-consumed", "capability-issued", "chain-reanchored",
        # A compaction is a context eviction that destroys the evidence it
        # happened. Without a record, a session cannot say it compacted at all,
        # and every later "what I have seen so far" rests on an invisible gap.
        "context-compacted",
        # C-9 (0.3.28 Plan 3 Task 3): the done-bar's own per-Stop turn
        # tick, joined to `BOOKKEEPING_SUBJECTS` above.
        DONEBAR_TURN_SUBJECT,
        # NS-10h (0.3.28 Plan 3 Task 11): one resurface of an idle
        # anchor - bookkeeping about the anchor's silence, joined to
        # `BOOKKEEPING_SUBJECTS` above.
        COOLDOWN_SUBJECT,
        # U-N-1: the one per-edit fact a PreToolUse gate write never carries
        # (category/tier/gate, never a path) - `godmode_post_edit.py` fires
        # once per PostToolUse call already scoped by the host matcher to
        # edit-shaped tools, so it is the one real writer that both sees
        # every edit and already resolves the repo-relative path. Bookkeeping
        # about an edit, never an "operation" - excluded by name
        # (`EDIT_RECORD_SUBJECT` above) from every detector that reasons
        # about repeated or unattested operations.
        EDIT_RECORD_SUBJECT,
        "failure-nudge",
        # NS-10c: the breaker's own trip/readmit records - bookkeeping about
        # the flake, joined to `BOOKKEEPING_SUBJECTS` above.
        FLAKE_PARKED_SUBJECT, FLAKE_READMITTED_SUBJECT,
        # NS-8o: one isolated rerun of a registered flake - bookkeeping
        # about the flake, joined to `BOOKKEEPING_SUBJECTS` above.
        FLAKY_RETRY_SUBJECT,
        # NS-13d: bookkeeping about an edit the plan-first gate exempted
        # as small, joined to `BOOKKEEPING_SUBJECTS` above.
        PLAN_FIRST_EXEMPT_SUBJECT,
        # NS-11e (0.3.28 Plan 5 Task 7): one record per real `godmode forget`
        # pass - the evidence that the scheduled pass ran at all.
        FORGET_PASS_SUBJECT,
        "gate-asked", "git-hook-inspection-failed", "git-hook-malformed-input",
        "git-hooks-installed", "host-payload-capture", "interpreter-inline-read-only",
        "interrupted-intent", "law-debrief", "laws-delivered", "observe-advisory",
        "preflight-skipped", "prompt-shape-nudge", "recurrence-nudge", "registry-nudge",
        "sources-gate", "tripwire-nudge",
        # NS-8f: a fetch/search/read-of-external tool result that scanned as
        # instruction-shaped text - bookkeeping about the read, joined to
        # `BOOKKEEPING_SUBJECTS` above.
        UNTRUSTED_CONTENT_SUBJECT,
        # NS-10d: one Stop/SessionEnd call's host-reported usage - bookkeeping
        # about what the host declared, joined to `BOOKKEEPING_SUBJECTS` above.
        USAGE_OBSERVED_SUBJECT,
        "verify-promotion-nudge", "would-have-required-read",
        "would-have-required-reobserve", "would-have-required-restore", "would-have-stopped-loop",
    }
)

# Statuses that put a record out of force. Read by the contradiction check
# (a value that no longer binds cannot contradict one that does) and by the
# reversal check (an answer that was withdrawn is not a competing answer).
# One owner, because two readers asking "is this still in force?" with two
# different word lists is a disagreement waiting for a release to expose it.
SETTLED_STATUSES = frozenset({"retired", "superseded", "withdrawn", "revoked"})

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git", ".hg", ".svn", ".godmode", ".godmode-private", ".godmode-repo",
        ".godmode-state", ".research", ".planning", ".sprints",
        ".checkpoints", ".handovers", ".evidence", ".decisions", ".lessons",
        "node_modules", "coverage", "dist", "build", "target", "__pycache__",
        ".venv", "venv",
        # Tool caches. These lived only in `godmode_structure`'s private
        # copy of this list, so every other walk - the atlas, the database
        # inventory, the scope fence - descended into them.
        ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        # Framework build caches. Field report 2026-09-04: a Next.js
        # project's `.next` output polluted every drift count - hundreds
        # of "added/changed" paths no person had touched.
        ".next", ".nuxt", ".svelte-kit", ".turbo", ".cache",
        ".parcel-cache", ".angular", ".vercel", ".output",
        # Other agent tooling's local session state. It exists on a developer
        # machine and never in CI, so scanning it makes a gate red locally and
        # green in CI for reasons that have nothing to do with the repository -
        # which is exactly how `test_ci_gates` failed on 2026-09-12.
        ".remember",
    }
)

MANIFEST_NAMES = frozenset(
    {
        "package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml",
        "build.gradle", "composer.json", "gemfile",
    }
)
DOCUMENT_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt", ".adoc"})
DATABASE_SUFFIXES = frozenset({".sql", ".sqlite", ".sqlite3", ".db"})
CODE_SUFFIXES = frozenset(
    {
        ".c", ".cc", ".cpp", ".cs", ".go", ".java", ".js", ".jsx",
        ".kt", ".php", ".py", ".rb", ".rs", ".swift", ".ts", ".tsx",
    }
)


# The doctrine and red flags, canonical (S19 item 4): the session hook
# injects these into every brief, and the rules emitter renders the same
# text into per-host instruction files - one source, generated never
# hand-edited, exactly the contract bindings enforces for manifests.
DOCTRINE_TEXT = (
    "You are an evidence-first engineer. Named reflexes, active "
    "every response - cite one by name when it decides "
    "something. THE RECORD RULE: a statement of fact costs a "
    "record or softer wording. THE DONE BAR: completion is "
    "evidence on the record, never a sentence. THE TWO-REVERSALS "
    "LAW: after two failed fixes, stop analysing and go read - "
    "the analysis is the suspect. GREEN ADDS NOTHING: re-running "
    "a passing check tells you nothing new; re-running a failing "
    "one with nothing changed cannot change its verdict. "
    "SUPERSEDE, DON'T RE-LITIGATE: replacement is not reversal. "
    "ASK THE RECORD FIRST: before mutating, check what was "
    "already refused. THE RATCHET RULE: a miss that recurs gets "
    "a guard that fails on the next instance, not a lesson "
    "telling you to be careful. LEAVE A TRAIL: end by recording "
    "what changed, what is verified, and the next step.")

RED_FLAGS_TEXT = (
    "RED FLAGS - if you catch yourself thinking one of these, "
    "stop: 'this is too simple to record' (the record rule "
    "exists for exactly this size of fact). 'I remember how "
    "this works' (memory of state is a lead; read the current "
    "state). 'one more rerun to be sure' (green adds nothing). "
    "'the definition says it does not run' (a gating claim is a "
    "call-site claim - read the callers). 'every probe returned "
    "zero' (a uniform result across many inputs is a tooling "
    "smell - check the instrument). 'the lesson does not apply "
    "here' (it was written because someone thought that).")


# N-11 re-review, finding B: `godmode_verdict.record_verdict` and
# `godmode_invariants._verdict_invariants` both need to decide whether a
# checker command is the same command as a witness ref, and both must
# agree - a raw `==` in either one is a weaker copy of the same rule the
# other enforces (finding 2's exact evasion: "cmd  x" vs "cmd x"). Neither
# archive-owning module may import the other (see `godmode_invariants.py`'s
# module docstring on why it stays dependency-free of `godmode_chronicle`/
# `godmode_verdict`), so the comparison lives here instead - the same
# reasoning `REGISTER_STATES` above already uses to keep one definition
# instead of two hand-synced copies.
def split_checker_command(command: str) -> list[str]:
    """Tokenize a checker/witness command, safe for a bare or quoted Windows path.

    Posix-mode shlex (the plain-`shlex.split(command)` default) treats
    backslash as an escape character, which mangles a bare Windows path
    (`C:\\Program Files\\...\\python.exe`) before the OS ever sees it. Non-posix mode
    leaves backslashes alone, at the cost of leaving surrounding quote
    characters attached to the token instead of consuming them - so a path
    quoted to protect embedded spaces (`"C:\\Program Files\\...\\python.exe"`)
    comes back as a single token that still carries its own quote marks and
    fails to resolve as a file. Stripping one matching pair of outer quotes
    off each token (the same thing posix mode would have consumed) covers
    that case without reintroducing the backslash-eating problem posix mode
    has on this platform. May raise ValueError on unbalanced quoting -
    callers treat that as "could not parse", not a crash.
    """
    if os.name != "nt":
        return shlex.split(command)
    return [_strip_command_quotes(token) for token in shlex.split(command, posix=False)]


def _strip_command_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def normalized_command(text: str) -> str | None:
    """Tokenize-and-rejoin so `cmd  arg` and `cmd arg` compare equal; `None`
    when the text does not parse as a command at all (unbalanced quoting)."""
    try:
        return " ".join(split_checker_command(text))
    except ValueError:
        return None


def checker_commands_match(a: str, b: str) -> bool:
    """A raw `==` on checker/witness strings lets one extra space evade the
    trust-boundary rule that a checker cannot also be the witness. Compare
    tokenized forms when both sides parse as a command; fall back to a
    stripped literal compare when either does not (the exact "could not
    parse" treatment `split_checker_command` documents for its own
    callers)."""
    norm_a, norm_b = normalized_command(a), normalized_command(b or "")
    if norm_a is not None and norm_b is not None:
        return norm_a == norm_b
    return a.strip() == (b or "").strip()
