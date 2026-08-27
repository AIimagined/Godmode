"""CX-1/CX-5: a chronicled, live proof that a host actually calls the pre-tool boundary.

The claim `tool_call_interception: HARD` used to rest on an environment
variable (`GODMODE_PRETOOL_GATE`) nothing ever set - so it was wrong in both
directions: silently UNAVAILABLE while a host really was calling the hook,
and trivially fakeable by anyone who exported the variable by hand. Neither
direction is acceptable for a claim this product makes to an operator about
its own enforcement.

The replacement is a synthetic challenge instead of a self-report. A marker
operation, `godmode-probe:<nonce>`, is sent through the exact path a real
host tool call takes. The hook (`hooks/godmode_session_hook.py`) treats any
operation with this prefix as protected, denies it unconditionally - no
staged capability, no observe-mode conversion, no ceiling short-circuit can
turn it into an allow - and records the denial here. The denial IS the proof:
nothing about a probe that was never received could ever get this far to
write one.

Doctrine, verbatim, and load-bearing for every grading decision this module
makes: **Silence from a failed verifier is never evidence of permission.**
A probe that cannot be run, a payload that cannot be parsed, a hook process
that times out, or a host whose runtime state cannot be inspected all read
as "unknown" or "not proven" - never, under any code path in this module, as
an implicit allow or an implicit HARD claim.

## CX-5: the five-level interception scale

CX-1 reported exactly two answers, `HARD` or `UNAVAILABLE`. That binary
collapsed two honestly different situations into one word: a host that has
never heard of Godmode (truly `UNAVAILABLE`) and a host that ships the
skills+CLI cooperation layer today, on all six hosts this project packages
for (Addendum 4), with no hook boundary proven at all (`SOFT` - reporting
that as `UNAVAILABLE` understated real, working capability). It also let a
hook that used to be proven, then quietly broke, read exactly the same as a
hook that was never proven at all - both `UNAVAILABLE` - hiding the
regression a fresh install and a broken upgrade look identical from an
operator's chair.

`interception_state` now returns one of five levels, in this order (best to
worst):

- `HARD` - a fresh, unexpired, session-anchored live proof exists, and
  nothing has superseded it. The only level that may back an "enforced"
  claim.
- `DEGRADED` - a live proof was on record and PROVABLY fresh (session-
  anchored, CX-5-enriched, unexpired) but something now says it no longer
  holds: a newer `hook-uninstalled`/`probe-failed`/`hook-health-degraded`
  record, an expired TTL, an `expiry` that implausibly exceeds the record's
  own maximum age (`PROOF_MAX_TTL_SECONDS` - fix round 1, C1(b)), or a
  `hook_version`/`trusted_hook_hash` mismatch between what the proof
  recorded and what is true right now. "Previously HARD, now broken" - the
  regression case CX-1's binary scale could not distinguish from a fresh
  install.
- `PARTIAL` - the pre-tool hook is structurally discovered/registered (the
  shipped manifest wires it, per `hook_manifest_status`/
  `godmode_bindings.registration_report`), OR a real denial was recorded for
  this host at some point but is not fresh for THIS session - either way,
  no FRESH live proof exists right now.
- `SOFT` - the plugin/skills layer is installed for this host (one of the
  six Addendum-4 hosts) but no pre-tool hook is discovered/registered at
  all. Skills+CLI cooperation, nothing more - the true floor for every host
  this project ships to today.
- `UNAVAILABLE` - no compatible boundary: an unrecognised host, or (for the
  git backstop specifically, which has no skills+CLI floor to fall back to)
  no godmode-owned hook file installed at all.

CX-1's own binary distinction survives unchanged as the two poles of this
scale (`HARD`/`UNAVAILABLE` are still exactly what CX-1 defined them to be);
CX-5 widens what sits between them using evidence CX-1 already collects
(proof records) plus registration state CX-3 added and supersession records
either unit already writes.

## CX-5: receipt enrichment (privacy-safe, hashes and counts only)

`record_interception_proof` now writes, in addition to CX-1's original
`{host, tool, request_id, proof}`: `hook_version` (the running godmode
version string), `project_identity_hash` (the archive's own project key -
already a hash, never a path), `trusted_hook_hash` (sha256 of the probed
hook script's own bytes - defaults to hashing the shipped session hook
file when no explicit `hook_script` is given, so this is populated on
every ordinary write, not merely "when a caller remembered to pass one"),
`nonce_hash` (sha256 of `request_id`, redundant with the field itself but
named per the CX-5 contract), `observed_decision` (what the hook actually
rendered - `"deny"` for every probe this codebase writes today),
`host_acknowledgement` (a best-effort bool from structural registration
state - see `_host_acknowledgement_from_registration` - `None` when
genuinely unknowable, never a live shell-out from inside a record write),
`expiry` (an ISO-8601 timestamp, `PROOF_TTL_SECONDS` after mint, and
bounded at `PROOF_MAX_TTL_SECONDS` past the record's own `recorded_at` -
see fix round 1, C1(b), below). Freshness for `HARD` now means
"session-anchored AND unexpired" - both, not either.

**Uniform enrichment rule (fix round 1, C1(a), Critical - tightened from
the original round):** the original migration rule read "a pre-CX-5
minimal record ... caps at PARTIAL," checked at the time by `expiry`'s
presence ALONE. A live review repro showed that gate was gameable: a
record carrying `expiry` but omitting `hook_version`/`trusted_hook_hash`
still reached the `enriched` branch and then sailed through both drift
checks by ABSENCE (each, correctly on its own, treats "cannot compare" as
"not a drift claim" - see `_version_drifted`/`_hash_drifted`) - a
forgeable path to a permanent `HARD` grade for anything with plain
`archive.append` access, no live hook subprocess required. The rule is now
uniform (`_fully_enriched`): a record must carry ALL FIVE HARD-eligible
fields (`expiry`/`hook_version`/`trusted_hook_hash`/`nonce_hash`/
`observed_decision`), as non-empty strings, or it is treated exactly like
a pre-CX-5 minimal record regardless of which fields ARE present - capped
at `PARTIAL`, never reaching a drift comparison at all. "Unresolvable
never treated as drift" now applies ONLY to comparing two PRESENT values,
never to absence, matching the doctrine line's own "worse of the two
possibilities" test.

**Expiry ceiling (fix round 1, C1(b), Critical):** even a fully-enriched
record's `expiry` is bounded - more than `PROOF_MAX_TTL_SECONDS` past the
record's own `recorded_at` is refused outright at append time
(`KIND_INVARIANTS`, `godmode_invariants.py`) and, redundantly, graded
`DEGRADED` (never `HARD`) at read time (`_expiry_out_of_bounds`) should a
record somehow reach disk anyway. Closes the reviewer's other live repro:
`expiry: "9999-12-31T23:59:59+00:00"` used to have no sanity ceiling
anywhere in the stack.

**Backward compatibility, stated honestly rather than silently patched
around:** a CX-1-shaped minimal record (missing any of the five
HARD-eligible fields - every proof this codebase wrote before CX-5, and
now also any record an attacker or a bug produced with only some fields
present) still reads without error, and can never claim `HARD` - a record
that cannot prove ALL of "unexpired," "the right version," and
"untampered" grades at most `PARTIAL`. This is a real behavior change for
any archive holding such records, disclosed here rather than treated as a
compatibility shim: an incomplete shape proves less than it might have
claimed to, and CX-5 stops crediting it for more than it can actually
show.

## Who writes each supersession/degradation subject, and when

- `SUBJECT_PROOF` (`hook-interception-proof`) - `record_interception_proof`,
  called from the hook's probe-marker branch every time a
  `godmode-probe:<nonce>` operation is denied.
- `SUBJECT_ANCHOR` (`hook-session-anchor`) - `record_session_anchor`, called
  automatically from the hook's `session-start` branch on every real
  session. Also effectively supplied by `kind="session"` records from the
  explicit `godmode session open` CLI (`godmode_attest.open_session`) - see
  `_session_anchor_sequence`.
- `SUBJECT_PROBE_FAILED` (`probe-failed`) - written by `run_probe` itself,
  whenever an attempt's own `denied`/`proof_recorded` isn't both true
  (including a genuine subprocess timeout, reason `"timeout"`, and an
  unexpected exit code, reason `"unexpected-exit"` - CX-5 additions).
- `SUBJECT_UNINSTALLED` (`hook-uninstalled`) - real writers: CX-3 (native
  manifest install/uninstall, where implemented) and CX-4 (git-hook
  backstop uninstall, `godmode_githooks.git_hooks_uninstall`).
- `SUBJECT_HOOK_DEGRADED` (`hook-health-degraded`, CX-5) - written by
  `record_hook_degradation`, called from the hook's own main path the
  moment it detects its OWN health failed on a real (non-probe) call: a
  payload that failed to parse as JSON (`malformed-payload`). Every level
  this reason can supersede down to is `DEGRADED`, never lower, following
  the same "a real denial happened here once" reasoning `interception_state`
  applies to a stale-but-real proof.
- `SUBJECT_LATENCY_CHECK` (`hook-latency-check`, CX-5) - written by
  `run_probe`, every attempt, successful or not: this attempt's own
  self-injection round-trip time against the host's declared PreToolUse
  timeout budget, so `hooks status` can surface a standing latency warning
  for a fail-open host (Grok/Gemini/Cursor-default - Addenda 5/6/4a) without
  having to run a fresh probe on every status read.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import RUNTIME_VERSION
from .godmode_errors import ArchiveError

# The operation prefix the hook recognises as a probe, never a real command.
# Followed by a per-probe nonce so a stale proof can never be replayed as a
# fresh one, and so a staged capability (which matches exact operation text)
# can never coincidentally cover the next probe.
PROBE_PREFIX = "godmode-probe:"

# The `action`-kind subjects `interception_state` reasons about. One module
# owns all of them so a caller cannot spell "the hook came down" a second,
# drifting way. See the module docstring's "who writes each" section for
# which of these are actually written by shipped code today.
SUBJECT_PROOF = "hook-interception-proof"
SUBJECT_ANCHOR = "hook-session-anchor"
SUBJECT_UNINSTALLED = "hook-uninstalled"
SUBJECT_PROBE_FAILED = "probe-failed"
SUBJECT_HOOK_DEGRADED = "hook-health-degraded"  # CX-5
SUBJECT_LATENCY_CHECK = "hook-latency-check"  # CX-5

# Subjects whose mere presence, newer than the last proof, means the
# boundary demonstrably broke - "supersession" in `interception_state`'s own
# terms. `SUBJECT_HOOK_DEGRADED` joins CX-1's original two (uninstalled,
# probe-failed) in CX-5: a hook that is provably mishandling real payloads
# is exactly as broken as one that failed its own self-test.
_SUPERSEDING_SUBJECTS = frozenset({SUBJECT_UNINSTALLED, SUBJECT_PROBE_FAILED, SUBJECT_HOOK_DEGRADED})

# Bounded, enum-valued reasons `record_hook_degradation`/`run_probe` may
# record - never free text, so a chronicle read can enumerate every reason
# this codebase has ever meant, and so a caller cannot accidentally leak
# payload content into a "reason" string.
DEGRADE_REASON_MALFORMED_PAYLOAD = "malformed-payload"
DEGRADE_REASON_IDENTITY_MISMATCH = "identity-mismatch"
DEGRADE_REASON_TIMEOUT = "timeout"
DEGRADE_REASON_UNEXPECTED_EXIT = "unexpected-exit"
DEGRADE_REASONS = frozenset({
    DEGRADE_REASON_MALFORMED_PAYLOAD, DEGRADE_REASON_IDENTITY_MISMATCH,
    DEGRADE_REASON_TIMEOUT, DEGRADE_REASON_UNEXPECTED_EXIT,
})

# CX-5's five-level scale. Ordered worst-to-best for readability only - no
# code here compares levels by position, every comparison is by explicit
# name, so the order of this tuple is documentation, not logic.
LEVEL_UNAVAILABLE = "UNAVAILABLE"
LEVEL_SOFT = "SOFT"
LEVEL_PARTIAL = "PARTIAL"
LEVEL_HARD = "HARD"
LEVEL_DEGRADED = "DEGRADED"
INTERCEPTION_LEVELS = (LEVEL_UNAVAILABLE, LEVEL_SOFT, LEVEL_PARTIAL, LEVEL_HARD, LEVEL_DEGRADED)

# How long a fresh proof stays claimable as HARD, wall-clock, independent of
# the session-anchor check (which answers a different question - "is this
# proof about THIS session's hook" - and can stay satisfied for a session
# left open for days). 24 hours: long enough that an ordinary work session
# never sees a proof expire out from under it, short enough that a proof
# genuinely never means "this was true forever." Named here, not buried in
# a magic number, so a test or an operator can see exactly what "fresh"
# bounds to.
PROOF_TTL_SECONDS = 24 * 60 * 60

# Fix round 1, C1(b) (Critical): the reviewer's live repro minted a record
# claiming `expiry: "9999-12-31T23:59:59+00:00"` - nothing anywhere bounded
# how far past `recorded_at` an `expiry` may plausibly sit, so a record that
# LOOKS enriched (once C1(a) below closes the "omit a field to dodge its
# check" gap) could still claim permanence outright. `PROOF_MAX_TTL_SECONDS`
# is the absolute ceiling ANY record's `expiry` may claim, checked at TWO
# layers, deliberately redundant: `KIND_INVARIANTS` (`godmode_invariants.py`)
# refuses to even ARCHIVE a record whose `expiry` exceeds it (closes the
# normal-append path outright), and `interception_state` independently
# checks it again at GRADING time (`_expiry_out_of_bounds`) - a record that
# somehow reached disk anyway (an older archive format, a hand-edited file,
# a future bug in the append-time check) still cannot grade above `DEGRADED`.
# Ruling value: 24 hours, same as `PROOF_TTL_SECONDS` above - a legitimate
# record never needs to claim more than that, so the ceiling costs nothing
# to an honest write and closes the gap for a forged one.
#
# `godmode_invariants.py` keeps its OWN copy of this literal rather than
# importing it from here - that module's own docstring documents why it
# stays import-free of every archive-owning module (this one included, since
# it imports `godmode_chronicle`), the same "kept in sync BY HAND" discipline
# already used there for `TOOL_ERROR_ACK`. `tests/test_failure_semantics.py`
# pins the two literals equal so they can never silently drift apart.
PROOF_MAX_TTL_SECONDS = 24 * 60 * 60

# scripts/godmode_runtime/godmode_hookproof.py -> parents[2] is the package
# root. __file__-relative, never `${CLAUDE_PLUGIN_ROOT}` - the same
# resolution `godmode_scenarios.py`'s own hook-subprocess scenario already
# uses, so a probe run from any installed location finds the same hook a
# real host would.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

# The six hosts the skills+CLI core ships to today (Addendum 4: "the skills
# +CLI core therefore runs on all six TODAY"). Grading a host outside this
# set never rests on SOFT - an unrecognised host has no established floor
# to credit it with.
_SOFT_ELIGIBLE_HOSTS = frozenset({"claude", "codex", "grok", "cursor", "gemini"})

# Fail-open hosts (Addenda 5/6/4a, quoted verbatim in each): Grok's default
# timeout path allows the action; Gemini treats any exit other than 0/2 as a
# non-fatal warning that proceeds; Cursor fails open by default unless the
# specific hook sets `failClosed: true` (godmode's own manifest does, on its
# gate hooks - naming Cursor here is about the HOST's own default, not
# godmode's manifest choice). `hooks status` surfaces the latency warning
# more prominently for these three, per the plan's own naming.
FAIL_OPEN_HOSTS = frozenset({"grok", "gemini", "cursor"})

# Declared PreToolUse timeout, read from the SHIPPED manifest a host would
# actually load - never re-typed as a duplicate literal. `(relative path,
# event key, seconds-to-ms scale)`; Gemini's fragment already states its
# timeout in milliseconds (scale 1), every other manifest states seconds
# (scale 1000).
_PRETOOL_MANIFEST_SPECS: dict[str, tuple[str, str, int]] = {
    "claude": ("hooks/hooks.json", "PreToolUse", 1000),
    # Sprint 4: Codex fires the shared CamelCase `PreToolUse` block (captured
    # live), and the snake_case key it used to read here is retired - naming
    # an event Codex cannot fire made this return "budget unknown".
    "codex": ("hooks/hooks.json", "PreToolUse", 1000),
    "grok": ("hooks/hooks.json", "PreToolUse", 1000),
    "cursor": (".cursor-plugin/hooks.json", "preToolUse", 1000),
    "gemini": (".gemini-plugin/hooks-fragment.json", "BeforeTool", 1),
}


# Fix round 1, I1 (Important): a caller-omitted `host_acknowledgement`
# used to hard-default to `None` outright - the docstring claimed "a
# best-effort bool from structural registration state," but nothing ever
# computed one. `None` is ALSO a legitimate, explicit, caller-supplied
# value ("I looked, genuinely unknowable") - so a plain `None` default
# cannot tell "the caller never said" apart from "the caller looked and
# found nothing." This sentinel makes that distinction real: only the
# UNSET case triggers the automatic computation below.
_UNSET = object()


def _host_acknowledgement_from_registration(host: str) -> bool | None:
    """Fix round 1, I1: the REAL best-effort value the docstring always
    claimed, computed from the same CX-3 registration evidence
    `_auto_registration_grade` already reads for the SAME host -
    `True` when the host's own shipped manifest/registration state
    confirms this hook is structurally registered (`"partial"`), `False`
    when it structurally confirms the opposite (`"soft"` - plugin
    installed, hook not registered - a real, determined negative, not a
    guess), `None` when genuinely unknowable (`"none"` - an unrecognised
    host, or the registration report itself could not be read). Never
    consulted by `interception_state`'s grading (a dedicated test in
    `tests/test_failure_semantics.py` pins that a record's grade is
    identical regardless of what this field holds) - this is a
    descriptive fact for an operator/auditor reading a proof record back,
    never a grading input.
    """
    grade = _auto_registration_grade(host)
    if grade == "partial":
        return True
    if grade == "soft":
        return False
    return None


def record_interception_proof(
    archive: Chronicle, host: str, tool: str, request_id: str,
    *, hook_script: Path | None = None, observed_decision: str = "deny",
    host_acknowledgement: bool | None | object = _UNSET,
    ttl_seconds: int = PROOF_TTL_SECONDS,
) -> dict[str, Any]:
    """Record that the pre-tool boundary demonstrably received and denied a probe.

    Privacy-safe per doctrine: every enrichment field here is a hash, a
    count, a bounded enum string, or a version string this project already
    ships publicly - never a command body, a path, or any other free text.

    `hook_script` (fix round 1, C1(a)) defaults, when omitted or `None`, to
    the SHIPPED session hook file (`_PACKAGE_ROOT/hooks/godmode_session_
    hook.py`) rather than staying unset - a caller with a more specific
    file to attest to may still pass its own path, but "no hook_script
    given" is no longer a way to skip hashing entirely: every ordinary
    write now resolves and hashes a REAL file by default and stores it as
    `trusted_hook_hash` - the CX-5 drift signal `interception_state`
    compares against the CURRENT file's hash on every later read, so a hook
    silently edited after the proof was written (this project's own
    git-backstop tamper detector proves that class of edit is real, not
    hypothetical) downgrades a once-HARD proof to `DEGRADED` instead of
    staying HARD forever on stale evidence. The hash is genuinely absent
    only when even the default file cannot be read (a broken install) -
    never a guessed or blank hash that could coincidentally "match" a
    tampered file's absence of one.

    Fix round 1, C1(a): as of this round, EVERY enrichment field this
    function writes (`hook_version`/`project_identity_hash`/
    `trusted_hook_hash`/`nonce_hash`/`observed_decision`/`expiry`) is
    always populated on an ordinary call - `interception_state`'s own
    uniform-enrichment rule (`_fully_enriched`) requires all five
    HARD-eligible fields to be present, and this function is the one and
    only shipped writer, so an honest write is never itself the reason a
    record caps below `HARD`.

    `host_acknowledgement` defaults (fix round 1, I1) to the REAL
    best-effort value (`_host_acknowledgement_from_registration`), computed
    from the SAME registration evidence `hooks status` already reads for
    this host - not the permanently-`None` placeholder the docstring used
    to claim without ever computing. A caller may still pass an explicit
    override (including an explicit `None`, told apart from "unset" by the
    `_UNSET` sentinel above) when it has stronger evidence than the generic
    registration check can see.
    """
    if hook_script is None:
        hook_script = _PACKAGE_ROOT / "hooks" / "godmode_session_hook.py"
    if host_acknowledgement is _UNSET:
        host_acknowledgement = _host_acknowledgement_from_registration(host)
    data: dict[str, Any] = {
        "host": str(host)[:80],
        "tool": str(tool)[:80],
        "request_id": str(request_id)[:200],
        "proof": True,
        "hook_version": RUNTIME_VERSION,
        "project_identity_hash": str(getattr(archive.anchor, "project_key", "") or ""),
        "nonce_hash": _sha256_hex(str(request_id)),
        "observed_decision": str(observed_decision)[:40],
        "host_acknowledgement": host_acknowledgement,
        "expiry": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    trusted_hash = _hash_file(hook_script)
    if trusted_hash is not None:
        data["trusted_hook_hash"] = trusted_hash
    return archive.append("action", SUBJECT_PROOF, data, evidence=[])


def _sha256_hex(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str | None:
    try:
        return _sha256_hex(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def last_proof(archive: Chronicle, host: str | None = None) -> dict[str, Any] | None:
    """The newest interception-proof record, optionally scoped to one host."""
    records = archive.select(kind="action", subject=SUBJECT_PROOF, limit=500)
    if host is not None:
        records = [record for record in records if record["data"].get("host") == host]
    return records[-1] if records else None


def record_session_anchor(archive: Chronicle, host: str) -> dict[str, Any]:
    """The lightweight, counts-only freshness anchor a real session start produces.

    Called automatically from `hooks/godmode_session_hook.py`'s
    `session-start` branch, on every session, unconditionally - not gated
    on whether the operator ever runs `godmode session open`. See
    `_session_anchor_sequence` for how this reconciles with that heavier,
    explicit, opt-in record.
    """
    return archive.append("action", SUBJECT_ANCHOR, {"host": str(host)[:80]}, evidence=[])


def record_hook_degradation(archive: Chronicle, host: str, reason: str) -> dict[str, Any]:
    """CX-5: the hook records ITS OWN health failure on a real, non-probe call.

    `reason` must be one of `DEGRADE_REASONS` - a raw exception message or
    payload fragment must never reach here, matching the doctrine line this
    module opens with: a failure is recorded as a bounded fact, never as
    free text that could carry content. Superseded, in `interception_state`,
    exactly like `SUBJECT_UNINSTALLED`/`SUBJECT_PROBE_FAILED`: a newer
    record of this subject downgrades any HARD-shaped standing proof to
    `DEGRADED`.
    """
    if reason not in DEGRADE_REASONS:
        raise ValueError(f"unknown hook-degradation reason: {reason!r}")
    return archive.append(
        "action", SUBJECT_HOOK_DEGRADED,
        {"host": str(host)[:80], "reason": reason}, evidence=[],
    )


def record_latency_check(
    archive: Chronicle, host: str, *, latency_ms: float,
    timeout_budget_ms: int | None, warning: bool,
) -> dict[str, Any]:
    """CX-5: persist one probe attempt's own round-trip latency, counts only.

    Written on every `run_probe` attempt regardless of outcome, so
    `hooks status` (which never runs a live probe itself - see
    `godmode_bindings.registration_report`'s own docstring for the same
    "status never shells out" discipline) can surface the LAST measured
    margin without needing a fresh probe on every read.
    """
    return archive.append(
        "action", SUBJECT_LATENCY_CHECK,
        {
            "host": str(host)[:80],
            "latency_ms": round(float(latency_ms), 3),
            "timeout_budget_ms": int(timeout_budget_ms) if timeout_budget_ms is not None else None,
            "warning": bool(warning),
        },
        evidence=[],
    )


def last_latency_check(archive: Chronicle, host: str | None = None) -> dict[str, Any] | None:
    """The newest latency-check record, optionally scoped to one host."""
    records = archive.select(kind="action", subject=SUBJECT_LATENCY_CHECK, limit=200)
    if host is not None:
        records = [record for record in records if record["data"].get("host") == host]
    return records[-1] if records else None


def _session_anchor_sequence(archive: Chronicle) -> int:
    """The sequence a proof must be at or after to still count as fresh.

    Two DIFFERENT record kinds can each mark "a session started", and this
    reads whichever is newer - so neither can make the other's anchor
    stale, and an operator using both never sees them fight:

    - `kind="session"` (`godmode_attest.open_session`, driven by the
      explicit `godmode session open` CLI command). This is the heavier,
      opt-in unit of TRACKED work: it is also what attestation coverage
      (`attested_rule_ids`), the watchdog's skip-pattern detector, and
      `close_session`'s unattested-command check key off of. Reusing it
      directly as CX-1's freshness anchor - writing one automatically on
      every hook session-start - would have pulled every ordinary Claude
      Code session into that tracked-work machinery whether or not the
      operator ever asked for it: a materially bigger behavior change than
      an honesty fix needs to make.
    - `kind="action", subject=SUBJECT_ANCHOR` (`record_session_anchor`,
      written automatically by `hooks/godmode_session_hook.py`'s
      `session-start` branch on every real session). Lightweight,
      counts-only, and carries no attestation/watchdog side effects at all
      - CX-1's own anchor, scoped to exactly the honesty question this
      module answers.

    A project that also runs `godmode session open` inside a Claude Code
    session gets one anchor of each kind, close together in sequence;
    taking the max is exactly "the freshness bar is set by whichever
    anchor is more recent, whichever kind wrote it" - sound regardless of
    order, so the two never need to agree on which one governs.

    Neither kind ever written (no session-start hook installed, and
    `session open` never run) returns 0 - nothing to be stale relative to,
    so any existing proof counts.
    """
    session_sequence = 0
    sessions = archive.select(kind="session", limit=200)
    if sessions:
        session_sequence = sessions[-1]["sequence"]
    anchor_sequence = 0
    anchors = archive.select(kind="action", subject=SUBJECT_ANCHOR, limit=200)
    if anchors:
        anchor_sequence = anchors[-1]["sequence"]
    return max(session_sequence, anchor_sequence)


def _superseded_since(archive: Chronicle, since_sequence: int,
                      host: str | None = None) -> bool:
    """Whether this HOST's boundary demonstrably broke after its last proof.

    Sprint 4 found this unscoped: it counted any superseding record from any
    host, so running three hosts' live probes in one session had a Codex
    failure drop Claude's and Grok's freshly-proven boundaries to DEGRADED -
    each reporting that it "demonstrably broke" on another host's evidence.
    Supersession is per-host evidence; a Codex hook coming down says nothing
    about Claude's.

    A superseding record carrying NO host still supersedes for every host:
    an unattributed breakage cannot be ruled out for any of them, which is
    the fail-closed direction and the one to keep when the attribution is
    missing.
    """
    for record in archive.select(kind="action", limit=500):
        if record["sequence"] <= since_sequence:
            continue
        if record["subject"] not in _SUPERSEDING_SUBJECTS:
            continue
        if host is None:
            return True
        recorded_host = (record.get("data") or {}).get("host")
        if not isinstance(recorded_host, str) or not recorded_host.strip():
            return True
        if recorded_host == host:
            return True
    return False


def _expiry_passed(expiry: Any, now: datetime) -> bool:
    if not isinstance(expiry, str) or not expiry:
        # No parseable expiry: never itself a reason to call something
        # expired - callers only reach this once `expiry` is already known
        # to be present (an enriched record). An unparseable string is
        # treated the same as "expired" - honest failure, not a free pass.
        return True
    try:
        deadline = datetime.fromisoformat(expiry)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return now >= deadline


def _version_drifted(data: dict[str, Any]) -> bool:
    recorded = data.get("hook_version")
    if not isinstance(recorded, str) or not recorded:
        return False  # unresolvable, never itself treated as drift
    return recorded != RUNTIME_VERSION


def _hash_drifted(data: dict[str, Any], hook_script: Path | None) -> bool:
    recorded = data.get("trusted_hook_hash")
    if not isinstance(recorded, str) or not recorded:
        return False  # unresolvable at proof time, never itself treated as drift
    if hook_script is None:
        hook_script = _PACKAGE_ROOT / "hooks" / "godmode_session_hook.py"
    current = _hash_file(hook_script)
    if current is None:
        return False  # can't read the current file either - not a drift claim
    return current != recorded


# Fix round 1, C1(a) (Critical): the exact fields a record must carry ALL
# of to be HARD-eligible. `project_identity_hash` and `host_acknowledgement`
# are deliberately excluded - neither is a freshness/trust signal
# `interception_state` grades on (`project_identity_hash` is descriptive
# metadata; `host_acknowledgement` is descriptive per fix round 1's own I1
# order) - this list is exactly the five the fix-round order named.
_REQUIRED_HARD_FIELDS = (
    "expiry", "hook_version", "trusted_hook_hash", "nonce_hash", "observed_decision",
)


def _fully_enriched(data: dict[str, Any]) -> bool:
    """Fix round 1, C1(a) (Critical): the UNIFORM enrichment rule.

    The reviewer's live repro minted a record carrying `expiry` alone
    (omitting `hook_version`/`trusted_hook_hash` entirely) and it still
    graded `HARD` - because the old rule only asked "is `expiry` present,"
    and `_version_drifted`/`_hash_drifted` each (correctly, on their own)
    treat a MISSING field as "cannot compare, not a drift claim." Neither
    check was wrong in isolation; the gap was that "enriched enough to be
    HARD-eligible" was decided by ONE field's presence while the other
    checks silently no-op on the rest being absent - an omission gap, not a
    comparison gap. This closes it: a record must carry ALL FIVE
    HARD-eligible fields, as non-empty strings, to be treated as enriched
    at all. Missing even one puts it back in exactly the same bucket as a
    genuine CX-1-shaped pre-CX-5 record - capped at `PARTIAL`, never
    reaching the drift-comparison checks at all. "Unresolvable never
    treated as drift" (the reasoning inside `_version_drifted`/
    `_hash_drifted`) now applies ONLY to comparing two PRESENT values,
    exactly as the fix-round order specifies - it can no longer be reached
    with a field absent, because absence is caught here first.
    """
    return all(
        isinstance(data.get(field), str) and bool(data[field])
        for field in _REQUIRED_HARD_FIELDS
    )


def _expiry_out_of_bounds(proof: dict[str, Any]) -> bool:
    """Fix round 1, C1(b) (Critical): `True` when a proof's own claimed
    `expiry` sits more than `PROOF_MAX_TTL_SECONDS` past the record's own
    `recorded_at` timestamp - the reviewer's exact repro
    (`expiry: "9999-12-31T23:59:59+00:00"`). Checked independently of
    whether `expiry` has actually passed relative to `now`: a record dated
    2026 claiming a 9999 expiry is out of bounds the MOMENT it is graded,
    not only once 9999 arrives - the fix-round order's own wording, "a
    tampered-looking record must never grade above a stale one," is why
    this returns the SAME `DEGRADED` level `_expiry_passed` does, never a
    worse or better one. Unparseable timestamps fail closed (`True`),
    matching `_expiry_passed`'s own discipline; a record with no
    `recorded_at` (should be impossible - the chronicle always sets it) or
    no `expiry` at all has nothing to bound-check here (the uniform
    enrichment rule above already caught a missing `expiry`).
    """
    recorded_at = proof.get("recorded_at")
    expiry = proof.get("data", {}).get("expiry")
    if not isinstance(recorded_at, str) or not isinstance(expiry, str):
        return False
    try:
        recorded_dt = datetime.fromisoformat(recorded_at)
        expiry_dt = datetime.fromisoformat(expiry)
    except ValueError:
        return True
    if recorded_dt.tzinfo is None:
        recorded_dt = recorded_dt.replace(tzinfo=timezone.utc)
    if expiry_dt.tzinfo is None:
        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
    return expiry_dt > recorded_dt + timedelta(seconds=PROOF_MAX_TTL_SECONDS)


def _grade_from_registration(registration: str) -> str:
    return {
        "none": LEVEL_UNAVAILABLE,
        "soft": LEVEL_SOFT,
        "partial": LEVEL_PARTIAL,
    }.get(registration, LEVEL_UNAVAILABLE)


def _at_least_partial(grade: str) -> str:
    return LEVEL_PARTIAL if grade in (LEVEL_UNAVAILABLE, LEVEL_SOFT) else grade


def _auto_registration_grade(host: str, package_root: Path | None = None) -> str:
    """`"none"`/`"soft"`/`"partial"`, from structural evidence only.

    Never shells out to a host and never reads a project's own governed
    directory - this is godmode's own SHIPPED manifest state (the same
    `_PACKAGE_ROOT`-relative resolution `hook_manifest_status` and
    `godmode_bindings.registration_report` already use), read fresh on
    every call. `"git"` is deliberately excluded (returns `"none"`, i.e.
    UNAVAILABLE, unless a caller passes an explicit `registration=`
    override) - the git backstop has no skills+CLI floor to credit it with;
    `godmode_githooks.git_hooks_status` is the module that can actually see
    which git hooks are installed, and passes its own answer in rather than
    this module reaching into a file `godmode_hookproof.py` cannot import
    without creating an import cycle (`godmode_githooks` already imports
    THIS module).

    Fix round 1, C2 (Critical): the non-`claude` branch used to answer
    `"soft"` BOTH when `registration_report` succeeded and genuinely found
    no manifest for this host (the deliberate, documented case - "we know
    this host's plugin bundle is simply not wired," still a defensible
    `SOFT`) AND when reading it raised at all (an empty/missing
    `packaging/hosts.json`, a malformed source file - "we could not
    determine anything about this host," the doctrine line's own named
    case: *"silence from a failed verifier is never evidence of
    permission"*). Collapsing those into the same answer treated a verifier
    FAILURE as the BETTER of the two possibilities, the opposite of what
    this module's own docstring promises. The exception path now returns
    `"none"` (UNAVAILABLE) - strictly worse than `"soft"` - so a broken or
    absent registration source can never read as "the skills+CLI floor is
    confirmed installed." The two cases are told apart in code now, not
    just in this comment: `report is None` means "read attempted, nothing
    found" (still `"soft"`-eligible below); the `except` means "could not
    even attempt the read" (`"none"`).
    """
    if host == "claude":
        manifest = hook_manifest_status(package_root)
        if manifest["pretool_hook_seen"]:
            return "partial"
        return "soft" if manifest["plugin_installed"] else "none"
    if host in _SOFT_ELIGIBLE_HOSTS:
        try:
            from .godmode_bindings import registration_report
            report = registration_report(package_root)
        except Exception:  # noqa: BLE001
            # Fix round 1, C2: a verifier FAILURE, not a verified negative -
            # the worse of the two possibilities, per doctrine, never the
            # better one.
            return "none"
        entry = report.get(host) if isinstance(report, dict) else None
        if isinstance(entry, dict) and entry.get("manifest_present"):
            return "partial"
        # The read SUCCEEDED and genuinely found nothing for this host -
        # the deliberate, documented "plugin installed, hook not wired"
        # case, still `"soft"`.
        return "soft"
    return "none"


def interception_state(
    archive: Chronicle, host: str | None, *,
    registration: str | None = None, hook_script: Path | None = None,
    now: datetime | None = None,
) -> str:
    """CX-5's five-level grade: `HARD`/`DEGRADED`/`PARTIAL`/`SOFT`/`UNAVAILABLE`.

    `registration`, when given, overrides the automatic structural grade
    (`"none"`/`"soft"`/`"partial"`) - the escape hatch `godmode_githooks.py`
    (host `"git"`) and tests use to supply evidence this module cannot see
    on its own without an import cycle. Omitted, it is computed from
    godmode's own shipped manifest state via `_auto_registration_grade`.

    Every branch below reads from the chronicle or from structural manifest
    state - never from an environment variable, never from an unproven
    assumption. Doctrine: silence from a failed verifier is never evidence
    of permission - a proof this function cannot fully evaluate (missing
    fields, unparseable expiry) is treated as the WORSE of the two
    possibilities it could mean, never the better one.
    """
    now = now or datetime.now(timezone.utc)
    registration = registration if registration is not None else _auto_registration_grade(host or "unknown")
    try:
        proof = last_proof(archive, host)

        if proof is None:
            return _grade_from_registration(registration)

        if _superseded_since(archive, proof["sequence"], host):
            return LEVEL_DEGRADED
    except ArchiveError:
        # B4-1: a chain reporting tail-truncated (or any tamper verdict) is
        # DEGRADED evidence by definition - the proof this grade would have
        # ridden on may be exactly what was removed. Worse-of-the-two, per
        # this function's own doctrine.
        return LEVEL_DEGRADED

    data = proof.get("data", {})
    # Fix round 1, C1(a): ALL FIVE HARD-eligible fields must be present -
    # not merely `expiry` - for a record to be considered enriched at all.
    enriched = _fully_enriched(data)
    fresh_by_session = proof["sequence"] >= _session_anchor_sequence(archive)

    if not fresh_by_session:
        # A real proof exists, just not for the current session's hook. Its
        # mere existence is stronger evidence than bare manifest presence -
        # a real denial was demonstrably recorded for this host at some
        # point - so this never reads worse than PARTIAL.
        return _at_least_partial(_grade_from_registration(registration))

    if not enriched:
        # CX-1-shaped minimal record - or (fix round 1, C1(a)) any record
        # missing even ONE of the five HARD-eligible fields, uniformly,
        # regardless of which fields ARE present - fresh by session anchor,
        # but unable to itself prove "unexpired" or "untampered." Capped at
        # PARTIAL, exactly as the migration note in the module docstring
        # promises - never silently upgraded to HARD on a shape that cannot
        # support the claim.
        return LEVEL_PARTIAL

    # Fix round 1, C1(b): a record whose own claimed `expiry` sits beyond
    # the absolute ceiling checked FIRST, deliberately - a tampered-looking
    # record (the reviewer's year-9999 repro) must never grade above a
    # merely stale one, and checking it alongside (not instead of) the
    # other drift checks keeps that guarantee regardless of which other
    # fields also happen to be present or absent.
    if (_expiry_out_of_bounds(proof) or _expiry_passed(data["expiry"], now)
            or _version_drifted(data) or _hash_drifted(data, hook_script)):
        return LEVEL_DEGRADED

    return LEVEL_HARD


def degraded_reason(
    archive: Chronicle, host: str | None, *,
    registration: str | None = None, hook_script: Path | None = None,
    now: datetime | None = None,
) -> str | None:
    """The specific reason `interception_state` graded this host `DEGRADED`, or `None`.

    For `hooks status`/the session brief's persistent warning line - a
    grade alone ("DEGRADED") tells an operator something broke; this names
    which check caught it, so the warning line can say more than "trust me."
    """
    now = now or datetime.now(timezone.utc)
    if interception_state(
        archive, host, registration=registration, hook_script=hook_script, now=now,
    ) != LEVEL_DEGRADED:
        return None
    proof = last_proof(archive, host)
    if proof is None:
        return None
    if _superseded_since(archive, proof["sequence"], host):
        for record in reversed(archive.select(kind="action", limit=500)):
            if record["sequence"] <= proof["sequence"]:
                break
            if record["subject"] == SUBJECT_HOOK_DEGRADED:
                return str(record["data"].get("reason") or "hook-health-degraded")
            if record["subject"] == SUBJECT_UNINSTALLED:
                return "hook-uninstalled"
            if record["subject"] == SUBJECT_PROBE_FAILED:
                return "probe-failed"
        return "superseded"
    data = proof.get("data", {})
    # Fix round 1, C1(b): checked first, matching `interception_state`'s
    # own priority - a tampered-looking expiry is a distinct, more specific
    # fact than "it happened to also be past."
    if _expiry_out_of_bounds(proof):
        return "expiry-out-of-bounds"
    if _expiry_passed(data.get("expiry"), now):
        return "expired"
    if _version_drifted(data):
        return "version-drift"
    if _hash_drifted(data, hook_script):
        return "hash-drift"
    return "unknown"


def hook_manifest_status(package_root: Path | None = None) -> dict[str, Any]:
    """What the shipped hook manifest itself declares - not what any host has done with it.

    `plugin_installed` means the manifest is present at the resolved package
    root; `session_hook_seen`/`pretool_hook_seen` mean the manifest wires
    that lifecycle event to a Godmode script. None of the three says a host
    actually loaded or calls any of it - that gap is exactly what
    `interception_state`'s live proof exists to close, and CX-3's
    install-verify closes the remaining one (whether the host's own state
    shows the hook enabled).
    """
    root = package_root or _PACKAGE_ROOT
    manifest_path = root / "hooks" / "hooks.json"
    status = {
        "plugin_installed": False,
        "session_hook_seen": False,
        "pretool_hook_seen": False,
    }
    if not manifest_path.is_file():
        return status
    status["plugin_installed"] = True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return status
    hooks = manifest.get("hooks", {})
    if not isinstance(hooks, dict):
        return status

    def _wired(event: str) -> bool:
        for group in hooks.get(event, []) or []:
            if not isinstance(group, dict):
                continue
            for entry in group.get("hooks", []) or []:
                if not isinstance(entry, dict):
                    continue
                # Shell form (`command` is one string naming the script) is
                # the shipped shape since 2026-08-28; the exec form
                # (`command` + `args`) is still read so an older checkout
                # grades the same.
                tokens = [str(entry.get("command") or "")] + [
                    str(arg) for arg in (entry.get("args") or [])]
                if any(
                    script in token
                    for token in tokens
                    for script in ("godmode_session_hook.py", "godmode_gate_fast.py")
                ):
                    return True
        return False

    status["session_hook_seen"] = _wired("SessionStart")
    status["pretool_hook_seen"] = _wired("PreToolUse")
    return status


def _pretool_timeout_ms(host: str, package_root: Path | None = None) -> int | None:
    """CX-5: the declared PreToolUse timeout (ms) for `host`'s SHIPPED manifest.

    Read from the same file a real host would actually load, never
    re-typed as a duplicate literal. `None` when the host has no manifest
    spec, the file is missing, or the timeout is not a plain number - an
    honest "budget unknown," never a guessed default.
    """
    spec = _PRETOOL_MANIFEST_SPECS.get(host)
    if spec is None:
        return None
    relative_path, event_key, scale = spec
    root = package_root or _PACKAGE_ROOT
    path = root / relative_path
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    groups = manifest.get("hooks", {}).get(event_key)
    if not isinstance(groups, list):
        return None
    for group in groups:
        if not isinstance(group, dict):
            continue
        for entry in group.get("hooks", []) or []:
            if not isinstance(entry, dict):
                continue
            timeout = entry.get("timeout")
            if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
                return int(timeout * scale)
    return None


def run_probe(
    project: Path, archive: Chronicle, host: str, *, timeout: int = 20
) -> dict[str, Any]:
    """Self-inject a marker operation through the real hook process and verify the proof.

    "Self-injection" here means the CLI spawns the same hook script a host
    invokes, with the same PreToolUse payload shape - proving the mechanism
    (recognise, deny, record) works end-to-end. It does NOT prove a live
    host's own runtime is wired to call this script on real tool calls; that
    stronger claim is CX-3's install-verify.

    `state` (and the caller's exit code, which is derived from it) is THIS
    ATTEMPT's own verdict, and nothing else: `"HARD"` iff `denied` and
    `proof_recorded`, both computed fresh from what just happened, never
    from `interception_state`'s standing answer (a per-attempt self-test is
    deliberately binary - it either observed a fresh denial right now, or it
    did not; the five-level scale describes the STANDING state, which a
    caller reads separately via `interception_state`/`hooks status`).

    CX-5 additions: a `subprocess.TimeoutExpired` is now distinguished from
    any other subprocess failure (`reason="timeout"`, matching the plan's
    explicit "timeout marker honored" requirement); a response whose exit
    code is neither 0 nor 2 fails with `reason="unexpected-exit"` before its
    stdout is even parsed; every attempt also measures and persists its own
    round-trip latency against the host's declared timeout budget
    (`record_latency_check`), win or lose.
    """
    hook_script = _PACKAGE_ROOT / "hooks" / "godmode_session_hook.py"
    nonce = uuid.uuid4().hex[:16]
    operation = f"{PROBE_PREFIX}{nonce}"
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": operation},
    }
    timeout_budget_ms = _pretool_timeout_ms(host)
    result: dict[str, Any] = {
        "nonce": nonce,
        "host": host,
        "denied": False,
        "proof_recorded": False,
        "state": "UNAVAILABLE",
        # Pre-attempt history, captured before this probe runs, so it can
        # never be conflated with this attempt's own outcome below.
        "last_proof": last_proof(archive, host),
        "latency_ms": None,
        "timeout_budget_ms": timeout_budget_ms,
        "latency_warning": False,
        # The scope of this result, carried IN the result. This limitation
        # was documented in this function's docstring from the start and a
        # reader still published `state: HARD` as evidence that two hosts'
        # gates were live; they were not. A caveat only reaches the person
        # who quotes the number if it travels with the number, and it must
        # be present on every outcome, because a failed probe is exactly
        # when someone goes looking for a reason to discount it.
        "proves": ("this plugin's own hook script recognises the operation, "
                   "denies it, and records the denial - the mechanism works "
                   "end to end when invoked"),
        "does_not_prove": ("that this host's runtime actually calls the hook "
                           "on real tool calls; the probe self-injects, so it "
                           "reaches the script without the host's involvement"),
        "to_prove_wiring": ("run a PROTECTED command inside the host's own "
                            "session and confirm a refusal record lands in "
                            "the archive; a read-only command proves nothing "
                            "either way, because it is allowed silently and "
                            "records nothing"),
    }

    def _record_latency(latency_ms: float) -> None:
        margin = (
            None if timeout_budget_ms is None or timeout_budget_ms <= 0
            else (timeout_budget_ms - latency_ms) / timeout_budget_ms
        )
        warning = margin is not None and margin < 0.5
        result["latency_ms"] = round(latency_ms, 3)
        result["latency_margin"] = margin
        result["latency_warning"] = warning
        try:
            record_latency_check(
                archive, host, latency_ms=latency_ms,
                timeout_budget_ms=timeout_budget_ms, warning=warning,
            )
        except Exception:  # noqa: BLE001
            pass

    def _fail(detail: str, reason: str) -> dict[str, Any]:
        result["detail"] = detail
        try:
            archive.append(
                "action", SUBJECT_PROBE_FAILED,
                {"host": str(host)[:80], "reason": reason},
                evidence=[],
            )
        except Exception:  # noqa: BLE001
            pass
        return result

    if not hook_script.is_file():
        return _fail(
            "hook script not found at the resolved package root", "hook-script-missing")

    environment = dict(os.environ)
    environment["GODMODE_HOST"] = host
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(hook_script), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, env=environment,
        )
    except subprocess.TimeoutExpired:
        _record_latency((time.perf_counter() - started) * 1000)
        return _fail(f"probe subprocess exceeded its {timeout}s timeout", "timeout")
    except OSError as exc:
        _record_latency((time.perf_counter() - started) * 1000)
        return _fail(f"probe subprocess failed: {exc}"[:200], "subprocess-failed")
    _record_latency((time.perf_counter() - started) * 1000)

    if completed.returncode not in (0, 2):
        return _fail(
            f"probe subprocess exited {completed.returncode}, neither 0 nor 2",
            "unexpected-exit",
        )

    try:
        response = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        response = {}
    decision = (response.get("hookSpecificOutput") or {}).get("permissionDecision")
    result["denied"] = decision == "deny"

    proof = last_proof(archive, host)
    result["proof_recorded"] = bool(
        proof is not None and proof["data"].get("request_id") == nonce
    )

    if result["denied"] and result["proof_recorded"]:
        result["state"] = "HARD"
        return result
    if not result["denied"]:
        return _fail("hook did not deny the probe operation", "not-denied")
    return _fail("hook denied the probe but wrote no matching proof record", "proof-not-recorded")
