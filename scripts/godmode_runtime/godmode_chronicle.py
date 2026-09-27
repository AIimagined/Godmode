"""Atomic, hash-chained local continuity records for Godmode."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
import sys
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Iterator
import uuid

import shutil

from .godmode_anchor import ProjectAnchor, anchor_fingerprint, current_host, nongit_archive_root


def writer_fingerprint() -> dict[str, str]:
    """Who is writing: host, model, effort, and the adapter's enforcement level."""
    return {
        # Delegates to `godmode_anchor.current_host()` rather than
        # re-reading the env vars here, so this record's `host` field can
        # never disagree with what `godmode_hookproof.py`'s proof records or
        # `godmode_hostevent.py`'s adapters call the same session.
        "host": current_host(),
        "model": os.environ.get("GODMODE_MODEL", "unknown"),
        "effort": os.environ.get("GODMODE_EFFORT", "unknown"),
        "enforcement": os.environ.get("GODMODE_ENFORCEMENT", "SOFT"),
        # Where it ran, because a result produced under another runtime is not
        # evidence about this one. Deliberately coarse: the platform family and
        # the interpreter's minor version, never a hostname or a home directory,
        # since this record travels.
        "platform": os.environ.get("GODMODE_PLATFORM_OVERRIDE") or sys.platform,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        # Which agent, not merely which host. Host and model are not an
        # identity when two agents run on the same host - without this,
        # concurrent lanes interleave into one indistinguishable stream and
        # the fleet layer can name a lease holder that cannot be found in
        # the archive afterwards. Sourced from `godmode_constants`, which
        # has no runtime dependencies: owning it in the fleet layer would
        # make this module import that one while it imports this, and the
        # atlas reads imports statically, so deferring it inside a function
        # hid the cycle from the interpreter without removing it.
        "agent_id": agent_id(),
    }
from .godmode_constants import (
    EVENT_KINDS,
    RUNTIME_VERSION,
    SCHEMA_VERSION,
    agent_id,
)
from .godmode_errors import ArchiveError
from . import godmode_invariants as _invariants
from . import godmode_law as _law
from .godmode_sentinel import enforce_private_payload


# Who wrote a record, and how much
# that writer is trusted. `writer` is what the approval checks compare actors by -
# the field name and its four values are load-bearing beyond this module.
# `record_writer` treats anything outside this set as the pre-Task-5
# default (`agent`) - a corrupt or hand-edited field is a missing one,
# never trusted at face value.
WRITER_KINDS = ("agent", "operator", "checker", "hook")

# operator > checker > hook > agent, exactly the spec's ordering. A plain
# int so `status` (and any later reader) can compare two records with `>`
# without importing an enum.
TRUST_ORDER: dict[str, int] = {"agent": 0, "hook": 1, "checker": 2, "operator": 3}

# The single-writer close guard used to match only
# the literal string "closed", while `status.remaining()` already treated
# `met`/`done`/`retired` as equally terminal - a foreign agent refused
# `--status closed` could close the very same obligation with `--status
# done` and the refusal never fired. One constant, imported by both this
# module's guard and `godmode_status.py`'s reads, so the two sets can never
# drift apart again.
CLOSING_STATUSES = frozenset({"closed", "met", "done", "retired"})

# A `lesson` has one more way to end than the terminal set above:
# `superseded` lifts its guard from the compiled law exactly as `retired`
# does (`godmode_law.LESSON_DORMANT_STATUSES`), so for a lesson it is a
# close and the single-writer guard below treats it as one. Lesson-only on
# purpose: for every other kind `superseded` is a supersession chain
# (`--supersedes`, validated on its own), not a terminal state, and
# `status.remaining()` reads `CLOSING_STATUSES` for obligations, which
# this must not widen. Before this, an agent lifted an operator's law with
# `remember --kind lesson --status superseded` at agent trust; `retired`
# was refused and `superseded` was not.
LESSON_CLOSING_STATUSES = CLOSING_STATUSES | frozenset({"superseded"})

# A `review` record - the contradiction
# `godmode forget` files - is closed by a different vocabulary than the rest
# of the archive. Its statuses are `open` / `acknowledged` / `dismissed`
# (enforced by `godmode_invariants._review_invariants`), and the two that end
# it must go through the same single-writer close guard every other kind's
# `closed` does: an operator deciding a flagged contradiction is accepted, or
# not a contradiction at all, is a closure, not an ordinary append.
REVIEW_CLOSING_STATUSES = frozenset({"acknowledged", "dismissed"})

# The two entrypoint files a hook process is launched as - see their own
# `if __name__ == "__main__":` guards. Matched by the running script's own
# name AND its own directory (see `_running_as_hook`
# below), never by anything a tool-call payload carries, so a transcript
# can never claim to BE the hook currently evaluating it.
_HOOK_ENTRYPOINTS = frozenset({"godmode_session_hook.py", "godmode_gate_fast.py"})

# The plugin's own installed `hooks/` directory - two levels up from this
# file (`scripts/godmode_runtime/godmode_chronicle.py` -> plugin root ->
# `hooks/`). A candidate entrypoint must resolve to a file INSIDE this
# exact directory, not merely share a hook script's basename.
#
# `.resolve()` on the WHOLE path, not only on the
# ancestors before appending "hooks" - a candidate's own `path.resolve()`
# below resolves every segment, including a symlinked leaf, so leaving
# this one segment unresolved could make a genuine hook process (launched
# through a symlinked `hooks/`) compare unequal to itself and read as
# `agent`. Fail-closed either way; this just makes the two sides compare
# on the same footing.
_PLUGIN_HOOKS_DIR = (Path(__file__).resolve().parents[2] / "hooks").resolve()


def _entrypoint_is_hook(path_text: str | None) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if path.name not in _HOOK_ENTRYPOINTS:
        return False
    try:
        return path.resolve().parent == _PLUGIN_HOOKS_DIR
    except OSError:  # godmode: swallow-ok: an unresolvable path is not the plugin's hooks dir
        return False


def _running_as_hook() -> bool:
    """True when THIS process's own entrypoint file is one of the hook
    scripts AND lives in the plugin's own installed `hooks/` directory -
    not merely importing hook code (a test importing `godmode_session_hook`
    for its helpers must not read as a hook process actually running), and
    not spoofable by naming an arbitrary file `godmode_gate_fast.py`
    somewhere else (a bare basename match let
    `sys.argv[0] = "/tmp/anything/godmode_gate_fast.py"` read as `hook`
    with no file needing to exist).

    `hook` IS now a trust boundary for one
    decision - `Chronicle._enforced_refusal` exempts `writer == "hook"`
    writes from every enforce guard (added in 0.3.28 so hook writes stay trusted), so an
    entrypoint that reads as a hook by this function's loose derivation
    (its own `sys.argv[0]` or `__main__.__file__`, matched only against a
    basename AND the plugin's installed `hooks/` directory - never
    anything a tool-call payload carries) now writes exempt from every
    enforce guard, not merely provenance-tagged. The single-writer guard
    still compares `agent_id`, and `status.remaining()`'s trust order still
    only ever folds records that were never written by a real hook process
    - this is the one place the value itself gates a write.
    """
    main_module = sys.modules.get("__main__")
    if _entrypoint_is_hook(getattr(main_module, "__file__", None)):
        return True
    return _entrypoint_is_hook(sys.argv[0] if sys.argv else None)


def derive_writer(*, role: str | None = None, as_operator: bool = False,
                   operator_verified: bool | None = None) -> str:
    """Which of `agent | operator | checker | hook` is writing right now.

    A PURE function: it reads no environment variable
    and never prompts. Every input arrives as an explicit argument, resolved
    by the caller BEFORE this is invoked - `Chronicle.append` resolves
    `role` from a chronicled session (see `_chronicled_session_role`) and
    the console resolves `operator_verified` from the password broker or an
    interactive confirmation, both before the write lock is ever entered.

    Order is the security property, not merely a style choice:
      1. A hook process's own identity outranks any role a caller
         claims - nothing a session declares can make an actual hook
         process read as anything else.
      2. `operator` requires `as_operator=True` AND `operator_verified=True`
         - both supplied by the caller. There is no flag-alone path and no
         environment-variable path: a caller minting its own trust by
         setting a variable in its own process is not verification.
      3. `checker` is only ever a declared session role, passed in as
         `role="checker"` - never read from an environment variable here.
      4. Anything else is a plain `agent` - the default, and the only
         value an old record (written before this field existed) is
         ever read back as.
    """
    if _running_as_hook():
        return "hook"
    if as_operator and operator_verified:
        return "operator"
    if (role or "").strip().lower() == "checker":
        return "checker"
    return "agent"


def record_writer(record: dict[str, Any]) -> str:
    """The writer of a stored record. A record sealed before this field
    existed carries none - backward compatible as `agent`, never refused,
    never rewritten (the record hash covers exactly the payload that was
    actually sealed)."""
    writer = record.get("writer")
    return writer if writer in WRITER_KINDS else "agent"


def record_trust(record: dict[str, Any]) -> int:
    """`record_writer`'s trust rank, for callers that only need to compare."""
    return TRUST_ORDER[record_writer(record)]


# `remember --supersedes <seq>` (console.py's
# `cmd_remember`, validated there against the archive - existence, same
# kind, not already superseded, and not outranked on
# trust, since none of that is checkable from a single record's `data` the
# way `KIND_INVARIANTS` validators are) stores `supersedes` on the NEW
# record. Once it is on disk, every reader that ever asked "what is the
# latest record for this subject" has to stop trusting recency alone: a
# record can be superseded by something that does not even share its
# subject (a rename, a re-ask in new words), so a per-subject "highest
# sequence wins" fold would keep presenting it as current forever.
# `superseded_sequences`/`latest_by_subject` are the ONE place that rule
# lives - every enumerated reader (`godmode_requests.open_stated_requests`,
# `godmode_status.remaining`'s obligation/claim folds,
# `godmode_iteration.open_scope`'s obligation fold, `godmode_hygiene.
# hygiene`'s lesson/decision fold, `godmode_mistakes.list_patterns`,
# `godmode_mistakes.obligation_sibling_advisory`, `godmode_attest.
# lesson_pipeline`, `godmode_attest.obligations_digest` (it
# feeds `status --digest` and the closure
# verdict), `godmode_obligations.review_obligations` (it
# feeds `checkpoint --review`)) routes through it rather than re-deriving
# the rule. Known un-routed folds and why: see `latest_by_subject`'s own
# docstring.
def _sequence_of(record: dict[str, Any]) -> int:
    """Safe int coercion of a record's `sequence` - a malformed or missing
    value reads as 0 rather than raising, everywhere this field is
    compared (`_newest_wins` used to call `int(...)`
    bare while this module's other two readers already guarded it; a
    record with a malformed `sequence` coerced to `0`, survived the
    exclusion check, then raised inside the default combine)."""
    try:
        return int(record.get("sequence", 0) or 0)
    except (TypeError, ValueError):
        return 0


def superseded_sequences(records: list[dict[str, Any]]) -> frozenset[int]:
    """Every sequence number some record in `records` names via its own
    `data["supersedes"]` AND is trusted to retire - the set nothing may
    ever again call "latest".

    Trust-aware, not "trust any stored citation
    unconditionally" as this docstring used to argue. A record is excluded
    only when the CITING record's writer trust (`record_trust`) is
    `>=` the trust of the record it names - a lower-trust writer naming a
    higher-trust record's sequence is a forged or mistaken edge, not a
    valid retraction, and must not erase what the writer trust order
    would have refused to overwrite by a plain status flip. `_validate_
    supersedes` (console.py) is the write-time half of the same gate,
    refusing the write outright before it ever reaches disk; this is the
    durable, read-time half, because a raw append that bypasses the CLI -
    a hand-edited record, a record written before this field existed - can
    still land the field on disk, by this function's own contract below.

    When the named target is not present in `records` at all, its trust is
    unknowable from this call's inputs alone, so it stays excluded
    unconditionally - unchanged from before this fix, and the one case
    where "trust any stored citation" is still the read-time answer,
    because there is no target record here to compare against.

    One field, not two: this reads `data["supersedes"]` and nothing else.
    A claim's `data["resolves"]` is NOT read here, even though
    `godmode_graph._supersedes_edges` renders it as a SUPERSEDES edge - a
    resolution answers a claim, it does not retire the record. The graph
    is therefore wider than this set by design, and the difference is
    stated at both ends so neither reads as an oversight.
    """
    by_sequence: dict[int, dict[str, Any]] = {}
    for record in records:
        by_sequence.setdefault(_sequence_of(record), record)
    superseded: set[int] = set()
    for record in records:
        target = (record.get("data") or {}).get("supersedes")
        if target is None:
            continue
        try:
            target_sequence = int(target)
        except (TypeError, ValueError):
            continue
        target_record = by_sequence.get(target_sequence)
        if target_record is None:
            superseded.add(target_sequence)
            continue
        if record_trust(record) >= record_trust(target_record):
            superseded.add(target_sequence)
    return frozenset(superseded)


def open_reviews(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every contradiction `godmode forget` flagged that nobody has closed
    yet, newest first.

    One entry per (subject, exact sequence set), carrying the LATEST status
    recorded for it: a `review` is written open by the forgetting pass and
    closed by a later `review` on the same subject with `status:
    acknowledged` or `dismissed` (the chronicle's single-writer close guard
    gates those two - see `REVIEW_CLOSING_STATUSES`). Folding them here is
    what lets `status`, `hygiene` and the context brief show the same open
    findings instead of three different answers, and what keeps the drawer
    from being one nothing opens.
    """
    latest: dict[tuple[str, tuple[int, ...]], dict[str, Any]] = {}
    for record in records:
        if record.get("kind") != "review":
            continue
        data = record.get("data") or {}
        sequences = data.get("sequences")
        if not isinstance(sequences, list):
            continue
        key = (
            str(record.get("subject", "")),
            tuple(sorted(int(s) for s in sequences
                         if isinstance(s, int) and not isinstance(s, bool))),
        )
        latest[key] = {
            "sequence": _sequence_of(record),
            "subject": key[0],
            "sequences": list(key[1]),
            "kind": str(data.get("kind", "")),
            "status": str(data.get("status", "open")).strip().lower(),
        }
    return sorted((entry for entry in latest.values() if entry["status"] == "open"),
                  key=lambda entry: entry["sequence"], reverse=True)


def latest_by_subject(
    records: list[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], str] | None = None,
    combine: Callable[[dict[str, Any] | None, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """The latest record per `key(record)` (default: its own `subject`),
    honouring supersession edges - the ONE fold every latest-per-
    subject reader in this codebase now goes through.

    THE RULE, precisely: a record is superseded the instant some OTHER
    record ANYWHERE in `records` names its sequence number in
    `data["supersedes"]` - regardless of what key either record carries,
    and regardless of how much later, chronologically, some OTHER,
    unrelated record on the SAME key sits with no edge of its own. That
    last clause is the whole reason this cannot be "highest sequence per
    key wins" without the exclusion step first: a plain per-key fold
    cannot see a link that crosses keys (a request re-asked in different
    words, a lesson restated under a new subject), so on its own it would
    keep presenting a record as current forever after something else on
    record has explicitly named itself that record's successor. Excluding
    every superseded sequence FIRST, then taking the highest-sequence
    survivor per key, is what makes the edge win even when it disagrees
    with plain recency.

    `combine` is how a caller composes its OWN fold with this one instead
    of being replaced by it: the default keeps the plain "later sequence
    wins" rule every caller used before this edge existed, but a caller
    like `godmode_status.remaining` passes its trust-contradiction
    rule (`_prefer_latest_unless_contradicted`) instead - this function
    decides which records are even IN the running (excluding the
    superseded ones), `combine` decides which of the remaining ones for a
    key wins. Neither rule replaces the other. `superseded_sequences`
    (above) makes the exclusion itself trust-aware (B1): a citation from a
    lower-trust writer than its target never excludes that target here
    either, since this function's exclusion set IS that one.

    Scope: "ANYWHERE in `records`" means exactly that -
    the argument this call received, not the archive as a whole. Every
    caller today passes a kind-filtered, often window-limited selection
    (`archive.select(kind="obligation", limit=500)`), so a supersession
    citing a record outside that window is invisible here, the same way
    the write-time same-kind check already makes cross-kind supersession
    unreachable. Tasks 7 and 8 read through this helper per the plan's
    Self-Review; a caller with a narrower selection than "all records of
    this kind" inherits a narrower blind spot, not a bug in this function.

    Known gap: `godmode_law._guarded_
    lessons` and `godmode_law.amend_law` still re-derive their own
    newest-record-per-subject fold instead of routing through this
    function, so a superseded standing/enforce lesson can still read as
    the compiled law until whoever owns `godmode_law.py` (Tasks 2/4/8)
    wires it through. `SupersededStandingLessonTests` in
    `tests/test_supersession.py` proves this helper already gives the
    right answer for that shape; only the wiring is missing.
    """
    key_fn = key or (lambda record: str(record.get("subject", "")))
    combine_fn = combine or _newest_wins
    excluded = superseded_sequences(records)
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if _sequence_of(record) in excluded:
            continue
        group_key = key_fn(record)
        latest[group_key] = combine_fn(latest.get(group_key), record)
    return latest


def _newest_wins(current: dict[str, Any] | None, record: dict[str, Any]) -> dict[str, Any]:
    """`latest_by_subject`'s default `combine`: plain recency, the rule
    every caller used before the supersession edge or the trust rule existed."""
    if current is None:
        return record
    if _sequence_of(record) >= _sequence_of(current):
        return record
    return current


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _record_hash(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


# A non-blocking lock attempt's errno falls into three families, and
# `write_lock`/`lock_is_held` classify it fresh on every single call -
# never latched on the `Chronicle` instance. An instance-level latch was
# tried and reverted: two different processes each open
# their OWN descriptor and see their OWN errno, so process A holding the
# kernel lock cleanly and process B latching "unusable" from one transient
# failure would serialize on two DIFFERENT sidecars and could both append
# at once - a silent chain fork, worse than anything a slow retry costs.
#
# 1. CONTENTION - another holder has it right now: EACCES/EAGAIN/
#    EWOULDBLOCK from `fcntl.flock`, EACCES (13) from `msvcrt.locking`.
#    Retry until the deadline, exactly as plain contention always has.
# 2. UNSUPPORTED - locking is importable but not usable on THIS
#    filesystem: ENOLCK, EINVAL, EOPNOTSUPP, ENOTSUP, ENOSYS. Fall back to
#    `_write_lock_exclusive_create` for THIS CALL ONLY.
# 3. ANYTHING ELSE (EIO, ENOMEM, a genuinely failing disk, ...) - not a
#    lock semantics question at all. `write_lock` raises `ArchiveError`
#    immediately, loud, rather than guess which regime is safe.
#
# Accepted residual: on a filesystem where kernel locking is USUALLY
# usable, a transient ENOLCK (e.g. under Linux memory pressure) can still
# put one call on the exclusive-create sidecar while another call, moments
# apart, holds the kernel lock cleanly - two regimes active briefly on the
# same archive. The unsupported family is otherwise PERMANENT per
# filesystem (a capability of the mount, not of one call), so a working
# filesystem never mixes regimes in practice; a per-call decision cannot
# eliminate a genuinely transient failure without either latching (which
# reintroduced the fork above) or serializing every append through a
# second lock to protect the FIRST lock's own retry logic, which is not
# worth it for a failure this rare.
_LOCK_CONTENTION_ERRNOS = {errno.EACCES, errno.EAGAIN}
if hasattr(errno, "EWOULDBLOCK"):
    _LOCK_CONTENTION_ERRNOS.add(errno.EWOULDBLOCK)
if hasattr(errno, "EDEADLOCK"):
    _LOCK_CONTENTION_ERRNOS.add(errno.EDEADLOCK)

_LOCK_UNSUPPORTED_ERRNOS: set[int] = set()
for _errno_name in ("ENOLCK", "EINVAL", "EOPNOTSUPP", "ENOTSUP", "ENOSYS"):
    if hasattr(errno, _errno_name):
        _LOCK_UNSUPPORTED_ERRNOS.add(getattr(errno, _errno_name))
del _errno_name

# The exclusive-create fallback's own age sweep window (a crashed holder's
# sidecar is reclaimed past this age) - also what `lock_is_held()` uses to
# answer "is anyone holding the fallback's lock right now" without a
# kernel probe to ask, since that regime has none.
_EXCLUSIVE_CREATE_SWEEP_SECONDS = 120
# The fallback's hard ceiling: a sidecar older than this is taken over
# whatever its pid says. A holder alive but hung (or a pid reused by an
# unrelated process) would otherwise wedge the archive for good, and no
# legitimate write holds the lock this long.
_EXCLUSIVE_CREATE_CEILING_SECONDS = 30 * 60
# A takeover claim is held only for one read and one unlink; one older than
# this was left by a writer that died holding it.
_TAKEOVER_CLAIM_STALE_SECONDS = 10


# Two different Godmode runtime versions writing the same project's
# archive disagreed about the lock's own shape, so a version mismatch
# surfaced as plain contention - "archive is busy", sampled 197 times in
# the field, never naming what was actually different.
# Every lock sidecar already carried a diagnostic pid/timestamp payload
# (never fsynced - a lock a crash releases by age-out does not need one);
# the payload now carries the owning runtime version as a third line, so a
# timed-out acquire can tell "a different version holds this, by name"
# apart from "the same version is legitimately still writing".
def _lock_host() -> str:
    """This machine's name, as a lock sidecar records it: a pid means
    nothing on another host or in another pid namespace."""
    import platform
    try:
        return platform.node().strip() or "unknown"
    except OSError:
        return "unknown"


def _lock_owner_payload(pid: int, when: float) -> str:
    return f"{pid}\n{when}\n{RUNTIME_VERSION}\n{_lock_host()}\n"


def _lock_owner_host(text: str) -> str | None:
    """The host line of a lock payload, or None when it predates the field."""
    lines = text.splitlines()
    return (lines[3].strip() or None) if len(lines) >= 4 else None


def _lock_owner_version(path: Path) -> str | None:
    """The runtime version recorded in a lock sidecar by
    `_lock_owner_payload`, or None when the file is absent, unreadable, or
    predates this field (a lock from a runtime older than this fix) - a
    caller that gets None knows only "no version to compare", never treats
    it as "same version"."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if len(lines) < 3:
        return None
    version = lines[2].strip()
    return version or None


def _busy_message(path: Path) -> str:
    """The message a timed-out lock acquire raises: named by runtime
    version when the current holder's sidecar proves it is a different
    Godmode version, the previous generic wording otherwise (same version,
    ordinary contention - or a sidecar with nothing to compare)."""
    owner_version = _lock_owner_version(path)
    if owner_version is not None and owner_version != RUNTIME_VERSION:
        return (
            f"Godmode archive lock is held by runtime {owner_version}; this "
            f"process is runtime {RUNTIME_VERSION}. This is a version "
            "mismatch, not ordinary contention - run the same Godmode "
            "version everywhere that writes this archive, then retry."
        )
    return "Godmode archive is busy; retry after the active write"


def _pid_alive(pid: int) -> bool:
    """Whether process `pid` is still running. Anything this cannot answer
    for certain reads as alive: the callers use "dead" as permission to
    take over a lock or a sequence claim, so a wrong "dead" is the only
    answer that can do harm.

    Never `os.kill(pid, 0)` on Windows - there, signal 0 is CTRL_C_EVENT
    and would interrupt the process being asked about."""
    if pid <= 0:
        return True
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                # 87 = ERROR_INVALID_PARAMETER: no process has this id.
                # Anything else (access denied, ...) means it exists.
                return ctypes.get_last_error() != 87
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return True
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: unanswerable reads as alive (fail closed)
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _unlink_shared(path: Path) -> None:
    """Remove a small sidecar other processes may be reading. On Windows a
    reader's open handle refuses the delete for a moment; retry briefly,
    then leave it - a stale queue ticket is cleared by the next writer once
    its owner is gone."""
    for _attempt in range(50):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.002)
        except OSError:
            return


def _payload_pid(text: str) -> int | None:
    """The pid on the first line of a lock or claim payload, or None."""
    first = text.split("\n", 1)[0].strip()
    return int(first) if first.isdigit() else None


class _SequenceTaken(ArchiveError):
    """Another writer already holds, or already sealed, the sequence this
    write was about to take. `append` re-derives the tail from disk and
    retries; any other caller surfaces it as an ordinary archive error."""


def _kernel_lock(fd: int) -> None:
    """Take a non-blocking exclusive kernel lock on `fd`'s open file.

    Imports `fcntl`/`msvcrt` locally rather than caching the module at
    import time, so a test can force "neither is importable" with
    `unittest.mock.patch.dict(sys.modules, {"fcntl": None, "msvcrt": None})`
    (Python's import machinery raises `ImportError` for any name mapped to
    `None` in `sys.modules`). Once a module is genuinely available, `import`
    is an O(1) `sys.modules` lookup, so resolving it on every call rather
    than once costs nothing measurable.
    """
    try:
        import fcntl  # POSIX
    except ImportError:
        import msvcrt  # Windows
        # msvcrt.locking locks byte(s) starting at the CURRENT file
        # position, so every caller seeks to a fixed position (0) first;
        # `_kernel_unlock` seeks to the same position before unlocking.
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _kernel_unlock(fd: int) -> None:
    try:
        import fcntl  # POSIX
    except ImportError:
        import msvcrt  # Windows
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _has_kernel_locking() -> bool:
    """Whether this runtime can take a kernel advisory lock at all."""
    try:
        import fcntl  # noqa: F401  POSIX
    except ImportError:
        try:
            import msvcrt  # noqa: F401  Windows
        except ImportError:
            return False
    return True


_WIN_LONG_PATH_PREFIX = "\\\\?\\"
_WIN_LONG_PATH_THRESHOLD = 230  # margin below MAX_PATH (260) for the OS's own overhead


def _syscall_path(path: Path | str) -> str:
    """The string an OS-level call should actually receive for `path`.

    Windows' legacy file APIs refuse any
    path past 260 characters unless the machine-wide "enable long paths"
    policy is on - off by default, and outside this process's authority
    to flip. An operator's own `GODMODE_STATE_HOME`/`TEMP` can be short
    enough for the archive root to resolve and still leave no room for an
    event file's own fixed-width name (`godmode-events/<12-digit
    seq>-<32 hex>.godmode.json`, ~73 characters past the root) -
    `_atomic_json`'s own comment already documents the identical failure
    from an earlier walk; that fix shortened the TEMPORARY name but left
    the final destination (and every read of it) exactly as long as
    before. The `\\?\\` extended-length prefix bypasses the limit for an
    already-absolute path, applied ONLY at this syscall boundary, never
    through `Path.resolve()` (which normalizes the prefix away) and never
    stored back onto any `Path` this module returns - callers keep
    passing ordinary `Path` objects; only the raw string reaching `os.*`
    changes.
    """
    text = str(path)
    if os.name != "nt" or text.startswith(_WIN_LONG_PATH_PREFIX) or text.startswith("\\\\"):
        return text
    if len(text) < _WIN_LONG_PATH_THRESHOLD:
        return text
    return _WIN_LONG_PATH_PREFIX + text


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    # A Codex sandbox (PermissionError outside
    # the workspace) and a field walk (Windows: the temporary
    # name built from the 60-character record name pushed a deep state
    # home past MAX_PATH, FileNotFoundError): both escaped as tracebacks.
    # The temporary name is short, and any OS refusal becomes an
    # ArchiveError that names the directory and the remedy. That walk
    # shortened the temporary name; it did not make the FINAL destination
    # (this function's own `path` argument) any shorter, so the plain call
    # below can still hit the same wall - only now on `os.replace`'s
    # destination rather than `mkstemp`'s. The syscall-safe retry (never
    # tried first, so every normal-length call behaves exactly as before)
    # covers exactly that gap.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".w", suffix=".tmp", dir=str(path.parent)
        )
    except OSError:
        long_parent = _syscall_path(path.parent)
        try:
            if long_parent == str(path.parent):
                raise
            os.makedirs(long_parent, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".w", suffix=".tmp", dir=long_parent
            )
        except OSError as exc:
            raise ArchiveError(
                f"cannot write the archive under {path.parent} ({exc.strerror or exc}); "
                "the state location is not writable from here - point "
                "GODMODE_STATE_HOME at a writable directory (a short path on "
                "Windows), or initialise inside a git checkout so the archive "
                "lives under its .git directory"
            ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
            pass
        try:
            os.replace(temporary, path)
        except OSError:
            long_path = _syscall_path(path)
            if long_path == str(path):
                raise
            os.replace(temporary, long_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# Kind-specific data-shape invariants, enforced by append() at the archive
# seam rather than left to whichever caller happens to build the record.
# append() must never grow one branch per kind - a validator lives in
# godmode_invariants.py (dependency-free, so importing it here creates no
# cycle) and append() only ever asks "does this kind have one?" without
# knowing what any of them actually check. A validator raises ArchiveError
# to refuse; a normal return accepts.
#
# KIND_INVARIANTS is seeded from godmode_invariants.KIND_VALIDATORS AT THIS
# MODULE'S OWN IMPORT, not left to populate itself as a side effect of some
# other module (e.g. godmode_verdict.py) being imported first. That
# distinction is load-bearing: a process that imports godmode_chronicle
# without ever importing the kind-owning module still gets the guarantee,
# because importing godmode_chronicle IS what populates it. (An earlier
# version of this mechanism relied on kind-owning modules self-registering
# at their own import time - a fresh interpreter that imported only the
# archive core saw an empty registry and could append either forbidden
# verdict combination unchecked. Eager seeding from a dependency-free module
# closes that import-order gap.) register_kind_invariant() remains available
# for a validator that genuinely cannot live in godmode_invariants.py, but
# every kind shipped today is seeded eagerly and needs no such call.
KindInvariant = Callable[[dict[str, Any]], None]
KIND_INVARIANTS: dict[str, KindInvariant] = dict(_invariants.KIND_VALIDATORS)


def register_kind_invariant(kind: str, validator: KindInvariant) -> None:
    KIND_INVARIANTS[kind] = validator


def _is_record_name(name: str) -> bool:
    """The one test of "is this file a record" every listing of the events
    directory uses. Case-insensitive, as the directory glob it replaced was
    on Windows and macOS: review 2026-09-23 found the glob reading a stray
    `.GODMODE.JSON` copy that the identity scan's case-sensitive suffix test
    ignored, so the two views of one directory disagreed."""
    return name.lower().endswith(".godmode.json")


class _ListedPaths:
    """The record paths of a directory listing, built on access: a read that
    trusts the on-disk index for the first N records only ever opens the
    files after N, so it need not build a Path for the other 20,000.
    Behaves as a sequence of Paths for indexing, slicing, iteration and len;
    a slice stays lazy."""

    def __init__(self, directory: Path, names: list[str]) -> None:
        self.directory = directory
        self.names = names

    def __len__(self) -> int:
        return len(self.names)

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return _ListedPaths(self.directory, self.names[index])
        return self.directory / self.names[index]

    def __iter__(self) -> Iterator[Path]:
        return (self.directory / name for name in self.names)

    def __bool__(self) -> bool:
        return bool(self.names)


class Chronicle:
    """A project-bound archive whose primary records are immutable files."""

    def __init__(self, anchor: ProjectAnchor) -> None:
        self.anchor = anchor
        self.root = Path(anchor.archive_root)
        self.events = self.root / "godmode-events"
        self.config = self.root / "godmode-archive.json"
        self.lock_path = self.root / "godmode-write.lock"
        # The exclusive-create fallback's OWN sidecar, never the kernel
        # lock's. The two regimes cannot share `self.lock_path`: the
        # kernel path opens it with O_CREAT (so the path exists whether or
        # not locking actually works there), and `_write_lock_exclusive_
        # create` needs its path ABSENT for O_EXCL to mean anything - on a
        # shared path, a kernel sidecar that merely EXISTS (locking simply
        # unusable, nobody holding it) would look identical to O_EXCL as
        # "someone holds this", spinning the fallback's full timeout on
        # every single append for a problem retrying can never fix.
        self.excl_lock_path = self.root / "godmode-write.excl.lock"
        # The kernel lock's owner metadata (pid/time/runtime
        # version) cannot live inside `self.lock_path` itself - on Windows,
        # `msvcrt.locking()`'s byte-range lock is MANDATORY, so a second
        # process's plain read of that same file (byte 0 onward) while the
        # lock is held fails with a sharing violation instead of returning
        # the content, exactly when a timed-out acquirer most needs to read
        # it. A separate, never-locked sidecar keeps the diagnostic
        # readable by a contending process throughout the hold - the
        # exclusive-create fallback below needs no equivalent: its own
        # sidecar's exclusivity comes from O_EXCL creation, not a byte
        # lock, so its content was always plainly readable.
        self.lock_owner_path = self.root / "godmode-write.lock.owner"
        self.head = self.root / "godmode-head.json"
        # Sequence claims: before a record file is written, its sequence is
        # claimed by creating `<sequence>.claim` here with O_EXCL. Record
        # names carry a random id, so the record file itself can never be
        # the exclusive object; the claim is. Two writers that ever derive
        # the same sequence (a stale view, or two lock holders at once)
        # cannot both claim it - the second re-derives the tail from disk
        # and retries instead of forking the chain. Only the newest claim
        # or two are kept; older ones are pruned after each seal.
        self.sequence_claims = self.root / "godmode-sequence-claims"
        # The write lock's waiting line: each contender takes the next
        # ticket here by exclusive create and enters the lock only once its
        # ticket is the lowest one standing. It orders the writers; the
        # kernel (or exclusive-create) lock alone still keeps them apart.
        self.lock_queue = self.root / "godmode-write.queue"
        # B4-1: the tail-truncation anchor. The hash chain is tamper-evident
        # mid-chain but silent on tail truncation (deleting the newest
        # record(s) leaves a shorter, internally valid chain), and the head
        # cache above is an explicitly disposable hint a deleter can refresh.
        # This sidecar records {length, head_hash} on every append and reads
        # may only ever catch UP to it - an anchor that over-counts the
        # files means records that existed are gone.
        self.chain_anchor = self.root / "godmode-chain-anchor.json"
        # The verified-checkpoint registry. Beside the
        # chain anchor, same trust class - written only after a FULL walk
        # (every record, from position 0, no acceleration) proves the chain
        # intact through a given checkpoint, and read-only for every other
        # caller. A checkpoint that is not IN this registry grants no
        # acceleration at all, no matter how internally consistent its own
        # bytes look - an attacker who appends a forged checkpoint (or
        # tampers an existing one) cannot register it themselves; only a
        # full walk can. `expunge`/`reanchor` clear it, since either one
        # can change what an earlier full walk actually proved.
        self.checkpoint_registry = self.root / "godmode-checkpoint-registry.json"
        # The cold tier's own
        # sidecar - which sequences `godmode forget`'s expire operation has
        # moved out of `self.events` into a rotated `events-cold-<n>.jsonl`
        # segment, and the record_hash each one sealed with, so `verify()`
        # can bridge the resulting gap in the hot chain without re-reading
        # the cold bytes on every ordinary read (see `verify()`'s own
        # comment on the gap-bridging check, and `verify_cold()` for the
        # thorough re-hash this sidecar is deliberately NOT a substitute
        # for). Same trust class as the checkpoint registry beside it:
        # written only by `rotate_to_cold()` under the write lock, from
        # records this process just verified itself - never a target a
        # caller can point elsewhere.
        self.cold_registry = self.root / "godmode-cold-registry.json"
        self._events_cache_key: tuple[Any, ...] | None = None
        self._events_cache: list[dict[str, Any]] | None = None
        self._events_verified_key: str | None = None
        # A pinned directory identity: set by `pin_identity()` for a
        # short-lived caller (a hook process) whose many reads would each
        # re-stat every record file; own appends refresh it, in-place
        # rewrites drop it, and nothing outside the pin's owner is affected.
        self._pinned_identity: tuple[bool, str | None] | None = None
        # The (identity, {name: (mtime_ns, size)}) of the last directory
        # scan `_events_identity` made - the read path reuses it for the
        # record list and the read index's prefix identity instead of
        # listing and stat-ing every record file again.
        self._last_listing: tuple[str, dict[str, tuple[int, int]]] | None = None
        self._accepted_keys_cache_key: tuple[int, int] | None = None
        self._accepted_keys_cache: set[str] | None = None
        # The enforce-lesson index. Keyed on how
        # much of the archive's head it has already folded in
        # (`_enforce_index_upto`, a record count) rather than re-deriving
        # from scratch every append - see `_sync_enforce_index`.
        self._enforce_index_upto: int = 0
        self._enforce_lessons_by_subject: dict[str, dict[str, Any]] = {}

    def initialized(self) -> bool:
        return self.config.is_file() and self.events.is_dir()

    def accepted_keys(self) -> set[str]:
        """Identities whose records this archive owns.

        Adopting a stranded archive must not rewrite its records: the ledger is
        immutable and hash-chained, so editing history to fit a new identity would
        destroy the very property that makes it trustworthy. Instead the archive
        remembers which identity it grew out of and accepts those records as its own.

        Cached on the config file's own (mtime_ns, size): verify() calls this
        once PER RECORD, so an uncached read re-opened and re-parsed the same
        rarely-changing file up to N times per verify pass - traced live at
        96 redundant reads per verify call on a 96-record archive. `adopt()`
        is the only writer, and a fresh stat on every call means a same-pass
        adopt is still seen on the very next call.
        """
        try:
            stat = self.config.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
        if key is not None and key == self._accepted_keys_cache_key \
                and self._accepted_keys_cache is not None:
            return self._accepted_keys_cache

        keys = {self.anchor.project_key}
        if self.config.is_file():
            try:
                config = self._read_json(self.config)
                # The identity this archive was born under is its own: a
                # checkout copied together with its `.git` (a harness copy,
                # a moved clone) resolves a new project key, and without
                # this line every record past the read index's trusted
                # prefix read as "project identity mismatch" while the
                # prefix passed unchecked - a verdict that depended on how
                # many records the index happened to cover.
                born = config.get("project_key")
                if isinstance(born, str) and born:
                    keys.add(born)
                keys.update(config.get("adopted_keys", []))
            except ArchiveError:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
                pass
        if key is not None:
            self._accepted_keys_cache_key, self._accepted_keys_cache = key, keys
        return keys

    def orphaned(self) -> dict[str, Any] | None:
        """Report an archive stranded at this project's previous identity.

        Running `git init` in an existing project switches the identity from the
        salted application-data key to the Git one, so everything recorded before
        becomes unreachable and the project reads as never initialized. Losing
        continuity silently is the failure this product exists to prevent, so the
        stranded archive is surfaced rather than left for the user to notice.
        """
        if not self.anchor.is_git:
            return None
        previous = nongit_archive_root(self.anchor.project_root)
        if previous == self.root:
            return None
        config = previous / "godmode-archive.json"
        events = previous / "godmode-events"
        if not config.is_file() or not events.is_dir():
            return None
        records = sorted(events.glob("*.json"))
        if not records:
            return None
        # Once adopted, the previous location is history, not a finding:
        # adopt() records the inherited key in this archive's config.
        try:
            inherited = str(self._read_json(config).get("project_key") or "")
            own = self._read_json(self.config) if self.config.is_file() else {}
            if inherited and inherited in set(own.get("adopted_keys") or []):
                return None
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable config reads as not adopted
            pass
        return {
            "source": str(previous),
            "records": len(records),
            "adoptable": not self.event_paths(),
            "reason": "project became a Git repository after these records were written",
        }

    def adopt(self, source: Path) -> dict[str, Any]:
        """Relink a stranded archive to this project's current identity.

        Copies the record files verbatim so the hash chain carries over, then
        rewrites only the identity in the config. Refuses to merge two histories:
        combining independent chains would produce a ledger that verifies against
        neither.
        """
        source = Path(source)
        source_events = source / "godmode-events"
        source_config = source / "godmode-archive.json"
        if not source_config.is_file() or not source_events.is_dir():
            raise ArchiveError(f"No adoptable archive at {source}")
        if self.event_paths():
            raise ArchiveError(
                "This archive already holds records; adopting would merge two "
                "independent hash chains. Move or clear the current archive first."
            )

        self.root.mkdir(parents=True, exist_ok=True)
        self.events.mkdir(parents=True, exist_ok=True)
        copied = 0
        for record in sorted(source_events.glob("*.json")):
            shutil.copy2(record, self.events / record.name)
            copied += 1

        payload = self._read_json(source_config)
        inherited = payload.get("project_key")
        payload["project_key"] = self.anchor.project_key
        payload["schema_version"] = SCHEMA_VERSION
        payload["adopted_from"] = "previous-identity"
        adopted = set(payload.get("adopted_keys", []))
        if inherited and inherited != self.anchor.project_key:
            adopted.add(inherited)
        payload["adopted_keys"] = sorted(adopted)
        payload["last_anchor"] = asdict(self.anchor)
        payload["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
        _atomic_json(self.config, payload)

        verified = self.verify()
        if not verified["ok"]:
            # Verify() reports rather than raises now, but
            # adopt() must not - a caller that copies a pre-tampered
            # stranded archive and gets back exit 0 has silently adopted a
            # broken chain. Mirrors reanchor()'s own check below.
            raise ArchiveError(verified["message"])
        return {"adopted": copied, "source": str(source), "chain": verified}

    def identity_drift(self) -> dict[str, Any] | None:
        """The recorded and resolved keys when this archive was born under
        a different identity than this checkout now resolves - a moved or
        copied checkout whose archive travelled with it - and no adopt has
        recorded the current one yet; None otherwise."""
        if not self.config.is_file():
            return None
        try:
            existing = self._read_json(self.config)
        except ArchiveError:
            return None
        recorded = existing.get("project_key")
        current = self.anchor.project_key
        adopted = existing.get("adopted_keys")
        if recorded == current or (isinstance(adopted, list) and current in adopted):
            return None
        return {"recorded_key": recorded, "current_key": current,
                "records": len(self.event_paths()), "archive": str(self.root)}

    def adopt_moved_identity(self) -> dict[str, Any]:
        """Relink THIS archive to the identity this checkout now resolves,
        as an operator-confirmed decision (`godmode adopt --confirm`).

        `adopt()` refuses here by design - the destination already holds
        records, and it exists to copy a separate, stranded archive in.
        A moved checkout needs no copy: the chain must still verify under
        the identities it already accepts, then the config's key becomes
        the current one and the old key is kept in `adopted_keys`, so every
        record it wrote still verifies. `initialize()`'s exact-match check
        is untouched: it passes afterwards only because the recorded key
        now IS the current one. The relink is chronicled."""
        with self.write_lock():
            drift = self.identity_drift()
            if drift is None:
                raise ArchiveError(
                    "This archive already carries this checkout's identity; "
                    "nothing to adopt.")
            existing = self._read_json(self.config)
            previous = existing.get("project_key")
            if not isinstance(previous, str) or not previous:
                raise ArchiveError("The archive config names no identity to adopt from.")
            if existing.get("schema_version") != SCHEMA_VERSION:
                raise ArchiveError("Archive schema requires an explicit migration")
            records = [self._read_json(path) for path in self.event_paths()]
            outcome = self.verify(records)
            if not outcome["ok"]:
                raise ArchiveError(
                    f"Refusing to adopt: the chain does not verify ({outcome['message']}).")
            current = self.anchor.project_key
            payload = dict(existing)
            adopted = {key for key in (existing.get("adopted_keys") or [])
                       if isinstance(key, str)}
            adopted.add(previous)
            adopted.discard(current)
            payload["project_key"] = current
            payload["adopted_keys"] = sorted(adopted)
            payload["adopted_from"] = "moved-checkout"
            payload["last_anchor"] = asdict(self.anchor)
            payload["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
            _atomic_json(self.config, payload)
        record = self.append(
            "action", "archive-identity-adopted",
            {"previous_key": previous, "current_key": current, "records": len(records)},
            evidence=[],
        )
        verified = self.verify(self.read_events(verify=False))
        if not verified["ok"]:
            raise ArchiveError(verified["message"])
        return {"adopted": "moved-checkout", "previous_key": previous,
                "current_key": current, "records": len(records),
                "record": f"seq:{record['sequence']}", "chain": verified}

    def initialize(self) -> None:
        # initialize() runs on every append, but creating and re-permissioning
        # directories only matters the first time; four syscalls per write for
        # directories that already exist was pure append overhead.
        if not self.initialized():
            self.root.mkdir(parents=True, exist_ok=True)
            self.events.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.root, 0o700)
                os.chmod(self.events, 0o700)
            except OSError:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
                pass
        if self.config.exists():
            existing = self._read_json(self.config)
            if existing.get("project_key") != self.anchor.project_key:
                # The check itself stays exactly as strict as before -
                # fail-closed, an exact match
                # only, never widened to accepted_keys() (which trivially
                # contains `self.anchor.project_key` by construction and so
                # cannot be used to loosen THIS comparison without making it
                # vacuous). What changed is the message: a moved or copied
                # checkout - the archive travels with it when it lives
                # inside `.git`, but its stamped identity does not - used to
                # get a bare "does not match", naming neither key nor a next
                # step. Both keys are named now, and the archive's own
                # `adopted_keys` (already how a genuinely relinked archive
                # is recognized) is checked directly, rather than via a
                # helper whose trivial self-inclusion would defeat the
                # point of asking.
                adopted = existing.get("adopted_keys")
                already_adopted = isinstance(adopted, list) and self.anchor.project_key in adopted
                if not already_adopted:
                    raise ArchiveError(
                        "Archive identity does not match this project: "
                        f"recorded {existing.get('project_key')!r}, this "
                        f"checkout resolves {self.anchor.project_key!r}. If "
                        "this checkout was moved or copied together with its "
                        "archive, that is the born identity drifting, not "
                        "tampering - `godmode adopt` previews relinking this "
                        "archive to this checkout's identity, and `godmode "
                        "adopt --confirm --as-operator` performs it (recorded, and the old "
                        "identity stays accepted for the records it wrote)."
                    )
            if existing.get("schema_version") != SCHEMA_VERSION:
                raise ArchiveError("Archive schema requires an explicit migration")
            refreshed = dict(existing)
            refreshed["last_anchor"] = asdict(self.anchor)
            refreshed["last_anchor_fingerprint"] = anchor_fingerprint(self.anchor)
            refreshed["runtime_version"] = RUNTIME_VERSION
            refreshed.pop("author", None)
            # initialize() runs on every append; rewriting an identical config
            # each time costs an fsync per write for zero information. Only
            # touch the file when the anchor or runtime actually moved.
            if refreshed != existing:
                _atomic_json(self.config, refreshed)
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "product": "Godmode",
            "runtime_version": RUNTIME_VERSION,
            "project_key": self.anchor.project_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_anchor": asdict(self.anchor),
            "last_anchor_fingerprint": anchor_fingerprint(self.anchor),
        }
        _atomic_json(self.config, payload)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        # Plain `Path.read_text` tried first, unchanged, so every
        # normal-length record reads exactly as before (including for
        # anything instrumenting that exact call); the syscall-safe retry
        # only engages once that has already failed AND a longer form
        # would actually be different (D-7).
        try:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                long_path = _syscall_path(path)
                if long_path == str(path):
                    raise
                with open(long_path, "r", encoding="utf-8") as handle:
                    text = handle.read()
            value = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            raise ArchiveError(f"Unreadable Godmode record: {path.name}") from exc
        if not isinstance(value, dict):
            raise ArchiveError(f"Invalid Godmode record: {path.name}")
        return value

    @contextmanager
    def write_lock(self, timeout_seconds: float = 20.0) -> Iterator[None]:
        """Serialize appends across processes with a kernel advisory lock.

        The sidecar stays; the lock lives on its descriptor and the OS
        drops it the moment the holder's process exits (normally or by
        being killed), so a crash cannot leave the archive busy until the
        old age sweep's window passes. Where neither locking module is
        importable, or where THIS call's lock attempt hits an errno in
        `_LOCK_UNSUPPORTED_ERRNOS`, `_write_lock_exclusive_create` below is
        used instead - on ITS OWN sidecar (`self.excl_lock_path`), never
        this one - for THAT CALL ONLY. The verdict is never remembered on
        the instance (see the module comment above `_LOCK_CONTENTION_
        ERRNOS`): a latch tried in an earlier round let two different
        processes, each reacting to their own errno, serialize on two
        different sidecars at once - a silent chain fork.

        Contenders queue first (`_take_queue_ticket`) and try the lock only
        at their turn, so under load each waits behind the writers ahead of
        it rather than losing every poll to whoever happens to retry first;
        `timeout_seconds` bounds the queue wait and the lock wait together.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        ticket = self._take_queue_ticket()
        try:
            self._wait_for_queue_turn(ticket, deadline)
            yield from self._write_lock_acquired(max(0.0, deadline - time.monotonic()))
        finally:
            if ticket is not None:
                _unlink_shared(ticket)

    def _write_lock_acquired(self, timeout_seconds: float) -> Iterator[None]:
        """The lock itself, entered once this writer's turn in the queue
        has come (see `write_lock`)."""
        if not _has_kernel_locking():
            yield from self._write_lock_exclusive_create(timeout_seconds)
            return

        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + timeout_seconds
        acquired = False
        try:
            while True:
                try:
                    _kernel_lock(descriptor)
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno in _LOCK_CONTENTION_ERRNOS:
                        if time.monotonic() >= deadline:
                            raise ArchiveError(_busy_message(self.lock_owner_path))
                        # Field feedback 2026-09-11 (Part 10): "busy; retry"
                        # twice in one pass with a hook and a CLI call
                        # writing together. A 20 s deadline with a growing,
                        # jittered wait outlasts any single append.
                        waited = timeout_seconds - (deadline - time.monotonic())
                        time.sleep(min(0.25, 0.05 + waited * 0.02) + (os.getpid() % 7) * 0.003)
                        continue
                    if exc.errno in _LOCK_UNSUPPORTED_ERRNOS:
                        # Locking is importable but not usable on this
                        # filesystem, for THIS call - spinning here for
                        # `timeout_seconds` would only misreport "busy" for
                        # a problem retrying cannot fix. Fall back below,
                        # never latched on the instance.
                        break
                    # Anything else (EIO, ENOMEM, a genuinely failing
                    # disk, ...): not a lock-semantics question at all.
                    # Loud and immediate - guessing which regime is safe
                    # here would risk the same silent fork the latch did.
                    # `os.strerror(None)` raises - some OSError instances
                    # (a handler-raised one, or a platform that leaves it
                    # unset) never populate errno, and the fallback string
                    # form of the exception still names the failure.
                    detail = os.strerror(exc.errno) if exc.errno is not None else str(exc)
                    raise ArchiveError(
                        f"archive lock failed: {detail} (errno {exc.errno})"
                    ) from exc
        finally:
            if not acquired:
                os.close(descriptor)

        if not acquired:
            # `self.lock_path` was just created above (O_CREAT) whether or
            # not locking turned out to be usable there, so the fallback
            # must NOT contend on that same path - its O_EXCL needs the
            # path ABSENT to mean anything, and a kernel sidecar that
            # merely exists (nobody holding it, locking just doesn't work
            # here) would otherwise look identical to "someone holds
            # this" and spin the fallback's full timeout for nothing.
            yield from self._write_lock_exclusive_create(timeout_seconds)
            return

        try:
            # Written to the SEPARATE sidecar (`lock_owner_path`),
            # never into `descriptor` itself - that file's byte 0 is what
            # `_kernel_lock` just locked, and on Windows a locked byte
            # range refuses even a read from another process, which is
            # exactly the moment a contending acquirer needs this content.
            # Best-effort like the payload always was ("diagnostic only");
            # a write that fails here must not cost the lock itself.
            try:
                self.lock_owner_path.write_text(
                    _lock_owner_payload(os.getpid(), time.time()), encoding="utf-8")
            except OSError:  # godmode: swallow-ok: diagnostic only, never the lock's own business
                pass
            yield
        finally:
            try:
                _kernel_unlock(descriptor)
            except OSError:  # godmode: swallow-ok: the descriptor close releases it anyway
                pass
            os.close(descriptor)

    def _take_queue_ticket(self) -> Path | None:
        """Join the write lock's waiting line: exclusively create the ticket
        one above the highest standing one. None when the line cannot be
        joined at all (an unwritable folder) - the lock still excludes,
        it just no longer orders this writer.

        Fairness: a ticket is created above every ticket standing when its
        writer listed the folder, so a writer can be overtaken only by a
        writer that listed before its own ticket existed - at most one per
        other contender - and every writer then waits for at most one
        critical section per writer ahead of it."""
        try:
            self.lock_queue.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        for _attempt in range(64):
            standing = self._queue_tickets()
            number = (standing[-1][0] + 1) if standing else 1
            path = self.lock_queue / f"{number:012d}.ticket"
            try:
                descriptor = os.open(
                    _syscall_path(path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            except (FileExistsError, PermissionError):
                # PermissionError: on Windows, a name whose delete is still
                # pending behind a reader's handle - taken, for now.
                continue
            except OSError:
                return None
            try:
                os.write(descriptor, f"{os.getpid()}\n{uuid.uuid4().hex}\n".encode())
            except OSError:  # godmode: swallow-ok: a pid-less ticket ages out like a pid-less claim
                pass
            finally:
                os.close(descriptor)
            return path
        return None

    def _queue_tickets(self) -> list[tuple[int, Path]]:
        """Standing tickets, lowest first."""
        try:
            names = os.listdir(self.lock_queue)
        except OSError:
            return []
        tickets = []
        for name in names:
            head, _, suffix = name.partition(".")
            if suffix == "ticket" and head.isdigit():
                tickets.append((int(head), self.lock_queue / name))
        tickets.sort()
        return tickets

    def _wait_for_queue_turn(self, ticket: Path | None, deadline: float) -> None:
        """Block until no live ticket stands below `ticket`, or raise busy
        at `deadline`. A ticket below is cleared only when its writer is
        provably gone (the same rule as a sequence claim), or - so a reused
        pid cannot wedge the line - once it has stood past the fallback's
        sweep window while nobody holds the lock. A wrong clear only
        reorders writers: exclusion never depended on the queue."""
        if ticket is None:
            return
        mine = int(ticket.name[:12])
        watched: Path | None = None
        since = 0.0
        while True:
            ahead = [(n, p) for n, p in self._queue_tickets() if n < mine]
            if not ahead:
                return
            lowest = ahead[0][1]
            now = time.monotonic()
            if lowest != watched:
                watched, since = lowest, now
            # Only a ticket that has stood at the front for a while is read:
            # on Windows an open read blocks its owner's release unlink, so
            # every waiter reading the front ticket on every poll would
            # stall the very hand-off it is waiting for.
            elif now - since >= 0.5:
                since = now
                if self._queue_ticket_abandoned(lowest):
                    _unlink_shared(lowest)
                    continue
            if now >= deadline:
                path = self.lock_owner_path if _has_kernel_locking() else self.excl_lock_path
                raise ArchiveError(_busy_message(path))
            # The writer next in line polls fast so the hand-off is quick;
            # those further back poll in proportion to their distance, so a
            # long line does not slow the holder's own disk work.
            time.sleep(min(0.25, 0.003 + 0.02 * (len(ahead) - 1)))

    def _queue_ticket_abandoned(self, path: Path) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
        pid = _payload_pid(text)
        if pid is not None and not _pid_alive(pid):
            return True
        if pid is None and age > 10:
            return True
        return age > _EXCLUSIVE_CREATE_SWEEP_SECONDS and not self.lock_is_held()

    def lock_is_held(self) -> bool:
        """Whether some process holds the write lock right now.

        The kernel-held lock's sidecar (`self.lock_path`) persists after
        release (see `write_lock` above), so its mere existence no longer
        means "held", and unlinking it on release would race a concurrent
        opener - on POSIX, `fcntl.flock` locks the INODE, not the path, so
        deleting the path out from under a holder would let a second
        opener silently acquire a lock on a different inode of the same
        name. Mirrors `write_lock`'s per-call errno classification, never
        latched: contention means someone else holds it; the "unsupported
        here" family means the exclusive-create fallback is the regime
        actually in effect for THIS call, so the answer comes from its own
        sidecar (`self.excl_lock_path`) instead - unlinked on every
        release, so "exists, and not yet old enough for the fallback's own
        age sweep to have reclaimed it" is the "held" signal that regime
        has always used. Any OTHER errno (EIO, ENOMEM, ...) - the same
        thing `write_lock` would raise `ArchiveError` on - is answered as
        "not held" rather than guessed, since this method has no
        exception contract to raise it through; it is not swallowed
        silently, only documented here, because there is no cheap way for
        a bare `bool` to also carry an error the caller (`godmode_lens.py`)
        has no way to act on differently anyway.
        """
        if _has_kernel_locking() and self.lock_path.exists():
            try:
                descriptor = os.open(self.lock_path, os.O_RDWR)
            except OSError:
                descriptor = None
            if descriptor is not None:
                try:
                    _kernel_lock(descriptor)
                except OSError as exc:
                    if exc.errno in _LOCK_CONTENTION_ERRNOS:
                        return True
                    if exc.errno not in _LOCK_UNSUPPORTED_ERRNOS:
                        return False
                    # else: the "unsupported here" family - fall through
                    # to the exclusive-create sidecar's own answer below.
                else:
                    try:
                        _kernel_unlock(descriptor)
                    except OSError:  # godmode: swallow-ok: close releases it anyway
                        pass
                    return False
                finally:
                    os.close(descriptor)

        if not self.excl_lock_path.exists():
            return False
        return not self._exclusive_lock_abandoned()

    def _write_lock_exclusive_create(self, timeout_seconds: float) -> Iterator[None]:
        """Fallback lock, on its own sidecar (`self.excl_lock_path`).

        An exclusive-create sidecar: mutual exclusion comes from the file
        not existing yet, so a crashed holder leaves it behind and only
        the age sweep below (`_EXCLUSIVE_CREATE_SWEEP_SECONDS`) recovers
        it. Used for a runtime with neither `fcntl` nor `msvcrt`, and for
        one call where locking was importable but hit an errno in
        `_LOCK_UNSUPPORTED_ERRNOS` - never on `self.lock_path`, which the
        kernel-lock path above may have already created via O_CREAT
        whether or not locking actually worked there.
        """
        deadline = time.monotonic() + timeout_seconds
        descriptor: int | None = None
        token = b""
        while descriptor is None:
            try:
                descriptor = os.open(
                    self.excl_lock_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                # No fsync: mutual exclusion comes from O_EXCL creation; the
                # content names the holder (pid, a unique time, version) so a
                # takeover can prove the holder is dead, and so release can
                # prove the sidecar is still its own.
                token = _lock_owner_payload(os.getpid(), time.time()).encode()
                os.write(descriptor, token)
            except FileExistsError:
                if self._take_over_abandoned_exclusive_lock():
                    continue
                if time.monotonic() >= deadline:
                    raise ArchiveError(_busy_message(self.excl_lock_path))
                waited = timeout_seconds - (deadline - time.monotonic())
                time.sleep(min(0.25, 0.05 + waited * 0.02) + (os.getpid() % 7) * 0.003)
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            # Release only a sidecar that is still this holder's own: one a
            # takeover replaced belongs to the new holder, and unlinking it
            # would let a third writer in beside them.
            try:
                still_ours = self.excl_lock_path.read_bytes() == token
            except OSError:
                still_ours = False
            if still_ours:
                self.excl_lock_path.unlink(missing_ok=True)

    def _take_over_abandoned_exclusive_lock(self) -> bool:
        """Remove the exclusive-create sidecar when its holder is gone, as
        one writer only.

        Judging and removing are two steps, so two waiters can both judge
        the same abandoned sidecar: the first removes it and creates its
        own, and a second that then removed "the" sidecar would remove the
        first one's fresh lock and create another beside it. The removal is
        therefore made under a short claim of its own (an exclusive-create
        `.takeover` file), and only once the sidecar still holds exactly
        the bytes that were judged abandoned; a sidecar that changed since
        belongs to a new holder and is left alone. Returns whether this
        writer removed it."""
        try:
            judged = self.excl_lock_path.read_bytes()
        except OSError:
            return False
        if not self._exclusive_lock_abandoned():
            return False
        claim_path = self.excl_lock_path.with_name(self.excl_lock_path.name + ".takeover")
        try:
            claim = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | getattr(os, "O_BINARY", 0), 0o600)
        except FileExistsError:
            # Another waiter is taking over right now. A claim is held only
            # for a read and an unlink, so one left by a writer that died
            # mid-claim is cleared once it is clearly older than that.
            try:
                if time.time() - claim_path.stat().st_mtime > _TAKEOVER_CLAIM_STALE_SECONDS:
                    claim_path.unlink(missing_ok=True)
            except OSError:  # godmode: swallow-ok: the next wait round looks again
                pass
            return False
        except OSError:
            return False
        try:
            try:
                current = self.excl_lock_path.read_bytes()
            except OSError:
                return False
            if current != judged or not self._exclusive_lock_abandoned():
                return False
            try:
                self.excl_lock_path.unlink(missing_ok=True)
            except OSError:
                # Windows refuses to remove a file a live process still has
                # open; the holder is not gone after all, so keep waiting.
                return False
            return True
        finally:
            os.close(claim)
            claim_path.unlink(missing_ok=True)

    def _exclusive_lock_abandoned(self) -> bool:
        """Whether the exclusive-create sidecar's holder is provably gone.

        Age alone is never enough: a holder that is merely slow (a large
        archive, a loaded machine) past the sweep window was taken over
        before, and two writers then overlapped. A sidecar naming a pid is
        abandoned only when that process is dead; one with no readable pid
        (a crash between create and write) only once it is older than the
        sweep window. A pid is only read on the host that wrote it: a
        sidecar from another host (a shared filesystem, another container)
        is never judged by a local pid lookup. Past the ceiling
        (`_EXCLUSIVE_CREATE_CEILING_SECONDS`) any sidecar is abandoned, so
        a live but hung holder cannot wedge the archive for good."""
        try:
            text = self.excl_lock_path.read_text(encoding="utf-8", errors="replace")
            age = time.time() - self.excl_lock_path.stat().st_mtime
        except OSError:
            return False
        if age > _EXCLUSIVE_CREATE_CEILING_SECONDS:
            return True
        pid = _payload_pid(text)
        if pid is not None:
            host = _lock_owner_host(text)
            if host is not None and host != _lock_host():
                return False
            return not _pid_alive(pid)
        return age > _EXCLUSIVE_CREATE_SWEEP_SECONDS

    def event_paths(self) -> list[Path]:
        if not self.events.exists():
            return []
        try:
            with os.scandir(self.events) as entries:
                names = [entry.name for entry in entries if _is_record_name(entry.name)]
        except OSError:
            return []
        return [self.events / name for name in sorted(names)]

    def _events_identity(self) -> str | None:
        """Cheap identity of the WHOLE events directory: every file's stat, hashed.

        NOT just the newest file - a tamper-evidence test caught that design
        directly: mutating an OLDER record's bytes in place (a plain
        write_text on an existing file, no new file added) left the count
        and the newest file's own stat unchanged, so that cache would have
        returned pre-tamper content and made verify() pass on tampered disk
        state. Chronicle's whole purpose is tamper evidence; a cache that
        can silently mask it is worse than no cache.

        Every file's (name, mtime_ns, size) folds into one hash. Still zero
        content reads - stat only - so it stays far cheaper than the parse
        it protects against, while catching a write to ANY record file.
        """
        # One scandir, not a stat per file: the directory listing already
        # carries mtime and size on Windows and most Unix filesystems, so
        # DirEntry.stat() costs no extra syscall. Measured 2026-09-04 on a
        # 9,178-record archive: a hook call spent 6 of its 18 seconds in
        # per-file stats here, seven identity checks per call. Same
        # (name, mtime_ns, size) fold; the tamper-evidence contract holds.
        try:
            with os.scandir(self.events) as entries:
                stats = []
                for entry in entries:
                    if not _is_record_name(entry.name):
                        continue
                    try:
                        stat = entry.stat()
                    except OSError:
                        return None  # a file vanished mid-scan; force a fresh read
                    stats.append((entry.name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            return None
        if not stats:
            return None
        stats.sort()
        parts = [f"{name}:{mtime}:{size}" for name, mtime, size in stats]
        identity = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        self._last_listing = (identity, {name: (mtime, size) for name, mtime, size in stats})
        return identity

    def _listing_for(self, identity: str | None) -> dict[str, tuple[int, int]] | None:
        """The per-file (mtime_ns, size) behind `identity`, when the last
        directory scan produced exactly that identity; None otherwise.

        On a 20,000-record archive a hook's first
        read stat-ed every record file one by one for the read index's
        prefix identity (4.4 s of a 7.5 s read) and listed the directory a
        second time for the record paths, after `_events_identity` had
        already listed it once with the same (name, mtime, size) for every
        file. Equal identity hashes mean an equal listing, so the tamper
        evidence is the same: an in-place rewrite of any record changes its
        listed mtime or size, the identity, and the prefix identity."""
        listing = self._last_listing
        if identity is not None and listing is not None and listing[0] == identity:
            return listing[1]
        return None

    # Field walk 2026-09-05: one SessionStart hook called read_events 25
    # times on a 9.3k-record archive and each call re-scanned the whole
    # directory - 1.4 s of stat calls for an archive nothing had touched.
    # The tamper-evidence contract (an in-place rewrite of an older record
    # must fail the NEXT read) rules out a time-based beat, so the relief is
    # opt-in: a short-lived process pins the identity it scanned once, its
    # own appends refresh the pin, and every append still lists the
    # directory fresh under the write lock for the chain tail.
    def pin_identity(self) -> None:
        self._pinned_identity = (True, self._events_identity())

    def unpin_identity(self) -> None:
        self._pinned_identity = None

    def _current_identity(self) -> str | None:
        pinned = self._pinned_identity
        if pinned is not None:
            return pinned[1]
        return self._events_identity()

    def _drop_events_cache(self, *, rewrite: bool = False) -> None:
        self._events_cache_key = None
        self._events_verified_key = None
        if rewrite:
            # An expunge or a re-seal rewrote files in place: an index
            # written before it would hand the next read the expunged
            # bytes. An append never reaches here with rewrite=True - the
            # indexed prefix is untouched by a new file after it.
            try:
                (self.root / self._INDEX_NAME).unlink()
            except OSError:  # godmode: swallow-ok: no index, or one the rewritten stats will reject anyway
                pass
            # Expunge/reanchor re-seal records in place,
            # which changes the `record_hash`/`previous_hash` a later
            # checkpoint's registry entry pinned - that entry no longer
            # describes what is on disk, so it must not go on granting
            # acceleration. Clearing it here (both callers of
            # rewrite=True) is what makes expunge safe on an archive that
            # holds a checkpoint: the next verify() falls through to a
            # full walk (the checkpoint's own registry-gated check is
            # simply skipped, never fails) and re-registers whatever it
            # finds intact.
            try:
                self.checkpoint_registry.unlink()
            except OSError:  # godmode: swallow-ok: no registry, or one the rewrite already invalidated
                pass
            # Expunge/reanchor can mutate an ALREADY-scanned record in
            # place (e.g. a lesson itself gets expunged) with no new record
            # added to signal it - the incremental sync below only ever
            # looks at the tail, so it would never notice. Reset to force
            # one full, one-time rescan on the next append.
            self._enforce_index_upto = 0
            self._enforce_lessons_by_subject = {}
            # The on-disk enforce sidecar
            # would otherwise keep describing pre-rewrite content under a
            # (count, head_hash) pair a fast in-place rewrite can leave
            # numerically unchanged (an expunge re-seals a record without
            # changing the file count) - unlink it here so the next sync
            # falls through to the full rescan the two resets above force,
            # and rewrites it once that rescan completes.
            try:
                (self.root / self._ENFORCE_INDEX_NAME).unlink()
            except OSError:  # godmode: swallow-ok: no sidecar, or one the rewrite already invalidated
                pass
        if self._pinned_identity is not None:
            # A pin that went None would make every later read a full parse
            # AND a full verify (measured: 33 s per SessionStart); re-scan
            # once so the next read fills the cache and verifies once.
            self._pinned_identity = (True, self._events_identity())

    def read_events(self, *, verify: bool = True) -> list[dict[str, Any]]:
        identity = self._current_identity()
        if identity is not None and identity == self._events_cache_key \
                and self._events_cache is not None:
            records = self._events_cache
        else:
            # A listing the identity scan already made gives the record
            # names and their stat figures without a second directory
            # walk, and without a Path object per record until one is read.
            listing = self._listing_for(identity)
            if listing is not None:
                names = sorted(listing)
                paths: list[Path] = _ListedPaths(self.events, names)
            else:
                paths = self.event_paths()
            trusted = 0
            indexed = self._read_index(paths, listing)
            if indexed is not None:
                # The on-disk index holds the first N records, parsed and
                # chain-walked under those N files' exact stat identity
                # (name, mtime, size). Only the files after N are parsed
                # and only their links are re-hashed. Before this,
                # every CLI call re-read and
                # re-hashed the whole archive (2.4-4 s per call).
                trusted = len(indexed)
                records = indexed + [self._read_json(path) for path in paths[trusted:]]
            else:
                records = [self._read_json(path) for path in paths]
            self._events_cache_key, self._events_cache = identity, records
            if verify and (identity is None or identity != self._events_verified_key):
                # Verify() now REPORTS a broken record instead of
                # raising; read_events() is the caller that relied on the
                # raise to make a corrupt archive unreadable rather than
                # silently returning tampered records, so it raises here
                # itself, carrying the same named-break message forward.
                outcome = self.verify(records, trusted_prefix=trusted)
                if not outcome["ok"]:
                    raise ArchiveError(outcome["message"])
                self._events_verified_key = identity
                if len(records) - trusted > self._INDEX_TAIL_LIMIT:
                    self._write_index(paths, records, listing)
            return records
        if verify:
            # Verified once per identity: the chain walk re-hashes every
            # record, and a hook call reads the archive seven times over
            # (measured 2026-09-04: 7 of 18 seconds). Any change on disk
            # changes the identity above and forces a fresh read AND a
            # fresh walk, so tamper evidence loses nothing.
            if identity is None or identity != self._events_verified_key:
                outcome = self.verify(records)
                if not outcome["ok"]:
                    raise ArchiveError(outcome["message"])
                self._events_verified_key = identity
        return records

    # --- on-disk read index -------------------------------------------------
    # Written after a verified read, keyed by the stat identity of the first
    # N record files; a read parses and verifies only the files after N and
    # rewrites the index once the tail outgrows _INDEX_TAIL_LIMIT. Ignored
    # under GODMODE_VERIFY_READS=1. Appends, expunge and reanchor still walk
    # the chain they touch, so tamper evidence keeps its write-side check,
    # and an in-place rewrite of any indexed file changes that file's stat
    # and drops the whole prefix.
    _INDEX_NAME = "godmode-events.index.json"
    _INDEX_TAIL_LIMIT = 200

    @staticmethod
    def _prefix_identity(paths: list[Path],
                         listing: dict[str, tuple[int, int]] | None = None) -> str | None:
        """Hash of each file's (name, mtime_ns, size). `listing`, when given,
        is a directory scan's own figures for those names (see
        `_listing_for`); a name it lacks is stat-ed directly."""
        if listing is not None and isinstance(paths, _ListedPaths):
            names = paths.names
            if all(name in listing for name in names):
                return hashlib.sha256("|".join(
                    f"{name}:{listing[name][0]}:{listing[name][1]}" for name in names
                ).encode("utf-8")).hexdigest()
        parts = []
        for path in paths:
            known = listing.get(path.name) if listing is not None else None
            if known is not None:
                parts.append(f"{path.name}:{known[0]}:{known[1]}")
                continue
            try:
                stat = path.stat()
            except OSError:
                long_path = _syscall_path(path)
                if long_path == str(path):
                    return None
                try:
                    stat = os.stat(long_path)
                except OSError:
                    return None
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _read_index(self, paths: list[Path],
                    listing: dict[str, tuple[int, int]] | None = None) -> list[dict[str, Any]] | None:
        if os.environ.get("GODMODE_VERIFY_READS"):
            return None
        path = self.root / self._INDEX_NAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        records = payload.get("records")
        count = payload.get("count")
        if not isinstance(records, list) or count != len(records) or count > len(paths) or count == 0:
            return None
        if payload.get("identity") != self._prefix_identity(paths[:count], listing):
            return None
        return records

    def _write_index(self, paths: list[Path], records: list[dict[str, Any]],
                     listing: dict[str, tuple[int, int]] | None = None) -> None:
        count = min(len(paths), len(records))
        identity = self._prefix_identity(paths[:count], listing)
        if identity is None or count == 0:
            return
        path = self.root / self._INDEX_NAME
        try:
            handle, temporary = tempfile.mkstemp(prefix=".index", suffix=".tmp", dir=str(self.root))
            # `dumps` then one write, not `json.dump`: `dump` streams through
            # the pure-Python encoder in small chunks, measured at several
            # seconds for a 20,000-record index (2026-09-23).
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"identity": identity, "count": count, "records": records[:count]},
                                    separators=(",", ":")))
            os.replace(temporary, path)
        except OSError:
            return

    # --- on-disk enforce-lesson index --------
    # Beside the read index above: a fresh `Chronicle` (every hook
    # invocation, every write-only CLI call is one) used to pay a full
    # `read_events()` walk on its first non-lesson append hunting for
    # enforce-carrying lessons that, on almost every real archive, do not
    # exist - measured 3,082 ms / 4,003 record reads on a 4,000-record
    # archive. This sidecar caches `_enforce_lessons_by_subject` itself,
    # keyed on the exact (count, head_hash) pair `_read_head()` already
    # maintains for the head-cache fast path, so a fresh process trusts the
    # last writer's own scan instead of repeating it - see
    # `_sync_enforce_index`, which reads this, and `_write_record`, which
    # keeps it current on every caught-up append.
    #
    # Threat model: forgeable by any writer with access to the archive
    # directory, exactly like `godmode-events.index.json` and the
    # checkpoint registry (THREAT-MODEL.md's ledger-tampering row) -
    # accepted under the same out-of-scope boundary (a hostile local user
    # with filesystem access; see THREAT-MODEL.md's "Out of scope"). Its
    # ORDINARY failure mode, absent deliberate tampering, is
    # under-enforcement only: a sidecar left behind by a crash, a partial
    # write, or an out-of-band edit that did not also refresh it simply
    # fails the (count, head_hash) check below and forces one full scan,
    # which finds every real lesson regardless - this file is a cache of
    # that scan's own output, never a distinct source of truth a write
    # trusts over the chain itself. Deliberate forgery of this file sits
    # inside the same filesystem-write-access boundary the hash chain
    # itself already declines to defend against.
    _ENFORCE_INDEX_NAME = "godmode-enforce.index.json"

    def _read_enforce_index(
        self, count: int, head_hash: str | None
    ) -> dict[str, dict[str, Any]] | None:
        """The cached `_enforce_lessons_by_subject`, or `None` when absent,
        unreadable, or stale (its own `count`/`head_hash` disagree with the
        archive's current head - the ONLY invalidation rule this needs,
        since both change on every append)."""
        path = self.root / self._ENFORCE_INDEX_NAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("count") != count or payload.get("head_hash") != head_hash:
            return None
        lessons = payload.get("lessons")
        if not isinstance(lessons, dict):
            return None
        result: dict[str, dict[str, Any]] = {}
        for subject, entry in lessons.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("sequence"), int):
                return None
            enforce = entry.get("enforce")
            result[str(subject)] = {
                "sequence": entry["sequence"],
                # Normalised the same way every writer
                # of this dict does (`_sync_enforce_index`'s tier-3 fold,
                # `.strip().lower()`) - a raw read here was the one place
                # left where a hand-edited sidecar's `"Superseded"` would
                # compare unequal to `_ENFORCE_INACTIVE_STATUSES`'s
                # lower-case members and stay armed. Only reachable through
                # a hand-edited sidecar (this class's own writer already
                # normalises before persisting), same as nit 7's original.
                "status": str(entry.get("status", "active")).strip().lower(),
                "guard": str(entry.get("guard", "")),
                "enforce": enforce if isinstance(enforce, dict) else None,
            }
        return result

    def _write_enforce_index(self, count: int, head_hash: str | None) -> None:
        """Best-effort: a failed write costs the next
        fresh process one fallback scan, nothing else - never raised,
        never allowed to fail the append whose data it is merely caching."""
        path = self.root / self._ENFORCE_INDEX_NAME
        try:
            handle, temporary = tempfile.mkstemp(
                prefix=".enforce", suffix=".tmp", dir=str(self.root))
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "count": count,
                        "head_hash": head_hash,
                        "lessons": self._enforce_lessons_by_subject,
                    },
                    fh, separators=(",", ":"), sort_keys=True,
                )
            os.replace(temporary, path)
        except OSError:  # godmode: swallow-ok: best-effort sidecar, see docstring above
            pass

    _CHECKPOINT_REGISTRY_FORMAT = 1
    _CHECKPOINT_REGISTRY_LIMIT = 16

    def _read_checkpoint_registry(self) -> dict[int, dict[str, Any]]:
        """The verified-checkpoint registry, keyed by `sequence`.

        Each entry is `{record_hash, previous_hash, record_count}` as they
        stood the moment a FULL walk (see `verify()`) last proved the chain
        intact through that checkpoint. Missing, unreadable, or malformed
        reads as empty - the registry is an accelerator, never an
        authority; losing it only costs the acceleration, never causes a
        false pass. Only the newest `_CHECKPOINT_REGISTRY_LIMIT` entries are
        ever kept (see `_write_checkpoint_registry`), so at most that many
        checkpoints can ever accelerate a read.
        """
        try:
            payload = json.loads(self.checkpoint_registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # ValueError also catches UnicodeDecodeError (a subclass) from a
            # non-UTF-8 file, and json.JSONDecodeError (also a subclass) from
            # a malformed one - same precedent as `_read_index` above: a
            # registry this function cannot parse reads as "no registry",
            # never a raise, and the next full walk rewrites it clean.
            return {}
        if not isinstance(payload, dict) or payload.get("format") != self._CHECKPOINT_REGISTRY_FORMAT:
            return {}
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return {}
        registered: dict[int, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sequence = entry.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                continue
            registered[sequence] = {
                "record_hash": entry.get("record_hash"),
                "previous_hash": entry.get("previous_hash"),
                "record_count": entry.get("record_count"),
            }
        return registered

    def _write_checkpoint_registry(self, registered: dict[int, dict[str, Any]]) -> None:
        entries = [
            {"sequence": sequence, **fields}
            for sequence, fields in sorted(registered.items())
        ][-self._CHECKPOINT_REGISTRY_LIMIT:]  # unbounded growth otherwise - only the newest N checkpoints ever accelerate a read
        try:
            _atomic_json(self.checkpoint_registry,
                        {"format": self._CHECKPOINT_REGISTRY_FORMAT, "entries": entries})
        except (OSError, ArchiveError):  # godmode: swallow-ok: best-effort write: this is the read path, and a write that fails here costs only the acceleration on the NEXT read, never correctness on this one, same as the chain anchor and the read index
            pass

    _COLD_REGISTRY_FORMAT = 1

    def _read_cold_registry(self) -> dict[str, Any] | None:
        """The cold tier's own ledger: which sequences `rotate_to_cold()`
        has moved out of `self.events`, the record_hash each one sealed
        with (`hash_by_sequence`, keyed by the sequence as a decimal
        string - JSON object keys are always strings), and which segment
        files hold them. `None` when absent or unreadable - a fresh
        archive, or one that has never run `godmode forget`, has no cold
        tier and every reader below treats that exactly like today's
        behaviour (see `verify()`'s gap-bridging comment and
        `_chain_tail()`).
        """
        try:
            payload = json.loads(self.cold_registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("format") != self._COLD_REGISTRY_FORMAT:
            return None
        rotated = payload.get("rotated")
        hash_by_sequence = payload.get("hash_by_sequence")
        segments = payload.get("segments")
        if not isinstance(rotated, list) or any(
            not isinstance(s, int) or isinstance(s, bool) or s <= 0 for s in rotated
        ):
            return None
        if not isinstance(hash_by_sequence, dict):
            return None
        if not isinstance(segments, list):
            return None
        try:
            parsed_hashes = {int(k): v for k, v in hash_by_sequence.items()
                             if isinstance(v, str) and v}
        except (TypeError, ValueError):
            return None
        # `rotated` and `hash_by_sequence` used to be
        # validated independently and never cross-checked, so a registry
        # could claim a sequence was rotated while holding no hash for it -
        # and a non-string value was simply dropped, producing exactly that
        # shape from a merely malformed file. Every reader downstream
        # (`verify()`'s gap bridge, `_chain_tail`'s cold-tail hash) then had
        # to cope with a `None` where a hash belongs. Fail closed instead:
        # an incomplete registry is an unreadable one, which every caller
        # already handles as "no cold tier, so a gap is a break".
        if any(sequence not in parsed_hashes for sequence in rotated):
            return None
        return {
            "rotated": sorted(rotated),
            "hash_by_sequence": parsed_hashes,
            "segments": segments,
        }

    def _write_cold_registry(self, rotated: list[int], hash_by_sequence: dict[int, str],
                             segments: list[dict[str, Any]]) -> None:
        _atomic_json(self.cold_registry, {
            "format": self._COLD_REGISTRY_FORMAT,
            "rotated": sorted(rotated),
            "hash_by_sequence": {str(k): v for k, v in hash_by_sequence.items()},
            "segments": segments,
        })

    def cold_segment_paths(self) -> list[Path]:
        """Every rotated segment file this archive's registry knows about,
        in the order they were written - `verify_cold()`'s own reading
        order, and the one place other callers (`godmode forget`'s report,
        a future export) learn where the cold bytes actually live rather
        than re-deriving the naming convention themselves."""
        registry = self._read_cold_registry()
        if registry is None:
            return []
        return [self.root / entry["file"] for entry in registry["segments"]
                if isinstance(entry, dict) and isinstance(entry.get("file"), str)]

    def _extend_checkpoint_registry(self, records: list[dict[str, Any]]) -> None:
        """Called only after `verify()` just walked EVERY record from
        position 0 and found the chain intact - registers every C-8-shaped
        checkpoint (`chain_head`/`record_count` present) it saw, so a later
        `_checkpoint_boundary` call may trust it without re-walking.
        Pre-C-8 checkpoints (no such fields) are never registered - there
        is nothing of theirs to pin.

        A checkpoint is registered only when it is still SELF-consistent:
        its own `data["chain_head"]` must equal its own `previous_hash`
        field, and its own `data["record_count"]` must equal its own GLOBAL
        position, `sequence - 1` - true by construction for anything
        `append()` ever wrote (it stamps `record_count` from `_chain_tail`'s
        tail sequence, which is this record's sequence minus one), but no
        longer true for a checkpoint an `expunge()` re-seal touched (the re-seal recomputes `previous_hash`/`record_hash` from
        the NEW chain shape, but cannot also reach back and change what is
        frozen inside the already-hashed `data` it is not re-sealing the
        CONTENT of). Registering it anyway would freeze a comparison in
        `_checkpoint_boundary` that this exact checkpoint can never again
        pass, permanently un-registerable and permanently un-accelerating
        - not a broken archive (the full walk that got here already proved
        the chain intact; a later one always can again), just a checkpoint
        that no longer qualifies as a boundary.
        """
        registered = self._read_checkpoint_registry()
        changed = False
        for record in records:
            if record.get("kind") != "checkpoint":
                continue
            data = record.get("data") or {}
            if "chain_head" not in data or "record_count" not in data:
                continue
            if data.get("chain_head") != record.get("previous_hash"):
                continue
            sequence = record.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                continue
            # The GLOBAL position
            # (`sequence - 1`), never this list's index. Once a rotation has
            # removed older files, a hot-list index is smaller than the
            # record's true position, and every checkpoint - old and new -
            # failed this test, so the registry could never be rebuilt and
            # every verify() walked from position 0 for the life of the
            # archive. `sequence - 1` is the same number an un-rotated
            # archive's index always was, so nothing already registered
            # changes meaning.
            if data.get("record_count") != sequence - 1:
                continue
            entry = {
                "record_hash": record.get("record_hash"),
                "previous_hash": record.get("previous_hash"),
                "record_count": data.get("record_count"),
            }
            if registered.get(sequence) != entry:
                registered[sequence] = entry
                changed = True
        if changed:
            self._write_checkpoint_registry(registered)

    def _checkpoint_boundary(self, records: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The newest `checkpoint` that is BOTH C-8-shaped
        AND already present in the verified-checkpoint registry
        (`_read_checkpoint_registry`) - `None` when nothing in `records`
        qualifies, so callers keep whatever `trusted_prefix` they already
        had (a full walk follows, and now-appears-good checkpoints get
        registered by it for next time - see `_extend_checkpoint_registry`).

        Registration - not mere internal self-consistency - is what makes a
        checkpoint trustworthy: every field this function compares is one
        the archive's own writer controls, so before the registry existed,
        an attacker could forge one appended checkpoint whose `chain_head`
        they simply read off the last record's stored hash, and the whole
        prefix before it went untrusted-but-unchecked. A checkpoint that
        was never seen intact by a full walk is not in the registry no
        matter how internally consistent it looks, and grants nothing here
        - the search moves on to an older checkpoint, or falls through to
        `None` (full walk) if none qualifies.

        `GODMODE_VERIFY_READS=1` disables this entirely (matching
        `_read_index`'s own handling of the same variable) - every read
        becomes a full walk again.

        For a checkpoint that IS in the registry, its own stored fields must
        equal what the registry captured at registration time: `record_hash`,
        `previous_hash`, and `data["chain_head"]` (which equals
        `previous_hash` for an honestly-written checkpoint - see
        `Chronicle.append()`), plus `data["record_count"]` against the
        registered `record_count` - AND the checkpoint's own position in
        THIS read's `records` list must still equal that same registered
        `record_count`, so a record inserted or removed ahead of it (shifting
        every later position) is a mismatch even when every stored field
        still agrees with itself. This catches any tampering of the
        CHECKPOINT RECORD ITSELF, or of what precedes it in this read's list,
        immediately, on every read, without a walk. It does NOT re-examine
        the CONTENT of the record before the checkpoint - tampering there,
        without touching the checkpoint's own bytes or shifting its position,
        is caught only at the next full walk (see
        `changelog.d/verified-checkpoints.added.md` and THREAT-MODEL.md for
        the plain statement of that scope).

        A checkpoint that PASSES returns `{"ok": True, "trusted_prefix":
        position + 1}`. One that is registered but now DISAGREES with its
        registered fields grants nothing here either: it returns `None`,
        the same as an unregistered or not-yet-seen checkpoint, so the
        caller falls through to a full walk. The registry is an
        accelerator, never an authority (see `_read_checkpoint_registry`);
        a disagreement here is not itself proof of tampering - a forged
        `previous_hash`/`chain_head`, a rewritten `record_count`, or a
        shifted position still breaks the content hash, the chain link, or
        sequence contiguity that the full walk below checks record by
        record, so real tampering is still caught and named there, while a
        merely poisoned or stale registry entry self-heals: the full walk
        re-registers the true entry for next time.
        """
        if os.environ.get("GODMODE_VERIFY_READS"):
            return None
        registered = self._read_checkpoint_registry()
        if not registered:
            return None
        # `record_count` is a GLOBAL
        # position (`sequence - 1`), and `records` here is the hot tier,
        # which after a rotation holds fewer records than the chain does.
        # The rotated sequences below a candidate are exactly the difference
        # between its index here and its global position, so the shift check
        # below stays the same check it always was - a record inserted or
        # removed ahead of the checkpoint still fails it - while a rotation
        # that legitimately removed older files no longer does. (The one
        # caller that hands in a cold+hot COMBINED list, `verify_cold()`,
        # passes `use_checkpoint=False` and never reaches here.)
        cold_registry = self._read_cold_registry()
        cold_rotated = sorted(cold_registry["rotated"]) if cold_registry else []
        for index in range(len(records) - 1, -1, -1):
            record = records[index]
            if record.get("kind") != "checkpoint":
                continue
            data = record.get("data") or {}
            if "chain_head" not in data or "record_count" not in data:
                # Pre-C-8 checkpoint: never registered, nothing to check -
                # keep looking further back for one that might be.
                continue
            sequence = record.get("sequence")
            entry = registered.get(sequence) if isinstance(sequence, int) else None
            if entry is None:
                # Not (yet) proven by a full walk - a brand-new checkpoint,
                # or a forged/appended one. Either way it grants nothing;
                # look further back rather than trusting it or failing on it.
                continue
            rotated_below = sum(1 for s in cold_rotated if s < sequence)
            if (record.get("record_hash") != entry.get("record_hash")
                    or record.get("previous_hash") != entry.get("previous_hash")
                    or data.get("chain_head") != entry.get("previous_hash")
                    or data.get("record_count") != entry.get("record_count")
                    or index + rotated_below != entry.get("record_count")):
                # Registered but now disagrees: the registry is an
                # accelerator, never an authority. Grant nothing and fall
                # through to the full walk below, which catches any real
                # tampering on its own (content hash / chain link /
                # sequence) and re-registers a merely poisoned or stale
                # entry - see the docstring above.
                return None
            return {"ok": True, "trusted_prefix": index + 1}
        return None

    def verify(self, records: list[dict[str, Any]] | None = None, *,
               check_anchor: bool = True, trusted_prefix: int = 0,
               use_checkpoint: bool = True, bridge_gaps: bool = True,
               path_at: Callable[[int], Path | None] | None = None) -> dict[str, Any]:
        # `bridge_gaps=False` (only `verify_cold()`
        # passes it) turns the cold registry off entirely for this call, so a
        # sequence missing from `records` is a BROKEN CHAIN rather than a gap
        # the registry explains. The ordinary read path keeps the bridge - it
        # is reading the hot tier alone, where a rotated sequence is absent by
        # design - but the thorough cross-tier check hands in cold and hot
        # together, and there nothing legitimate is missing, so nothing may be
        # explained away.
        # `path_at`: how a broken record's position maps to
        # a file, for the ONE caller (`verify_cold()`) whose `records` are
        # not `self.event_paths()`'s own list - a cold-plus-hot combined
        # walk, where `self.event_paths()` alone would name the wrong file
        # for a break inside the cold portion. Every other caller leaves
        # this `None` and gets exactly today's `event_paths()` lookup.
        # A broken record (schema, project identity, sequence, chain
        # link, or content hash) is reported here, not raised - the caller
        # gets the exact record that broke (sequence, file, line) instead
        # of a bare "tamper detected" that sends the reader to grep. Tail
        # truncation stays a raise below: that failure means records are
        # GONE, which no return value can safely let a caller ignore.
        records = self.read_events(verify=False) if records is None else records
        # The two prefix optimisations compose by taking whichever
        # proves MORE. `trusted_prefix` as passed in comes from the
        # file-stat index (godmode-events.index.json) - valid only while
        # those exact files' stat identity (name, mtime, size) hasn't
        # moved, and lost the moment they're copied or restored elsewhere.
        # `_checkpoint_boundary` proves a prefix by matching a checkpoint
        # record's own stored fields against its entry in
        # `godmode-checkpoint-registry.json` - a sidecar a full walk wrote
        # the last time it proved the chain intact through that checkpoint -
        # not by re-hashing anything here. Neither invalidates the other;
        # whichever bound is larger wins, and the walk below still only
        # re-checks what neither one already covers.
        #
        # `use_checkpoint=False` (only `cmd_doctor` passes this) skips the
        # lookup entirely, forcing this call to walk from position 0 even
        # when a registered checkpoint would otherwise accelerate it - the
        # one deliberately-triggered full walk this codebase schedules (see
        # `cmd_doctor` in godmode_console.py) so pre-boundary tampering
        # still surfaces, and so newer checkpoints get INTO the registry in
        # the first place.
        boundary = self._checkpoint_boundary(records) if use_checkpoint else None
        if boundary is not None:
            if not boundary["ok"]:
                return boundary
            trusted_prefix = max(trusted_prefix, boundary["trusted_prefix"])
        # A FULL walk is one where nothing at all was skipped - neither the
        # file-stat index nor a registered checkpoint accelerated it. Only
        # a walk this thorough is allowed to feed the registry (ruling:
        # "verify() writes/extends the registry only after a FULL walk
        # proved the chain intact through that checkpoint") - registering
        # off a partially-accelerated walk would let one bad registration
        # compound into trusting something no full walk ever actually saw.
        full_walk = trusted_prefix == 0
        previous: str | None = None
        expected_sequence = 1
        # The cold registry, read once per
        # verify() call - see `_read_cold_registry`'s docstring for why
        # this is safe to trust for BRIDGING a gap (never for re-proving
        # the cold bytes themselves; that is `verify_cold()`'s job).
        # Absent on every archive that never rotated to cold storage, so this is a
        # no-op there and every existing caller's behaviour is unchanged.
        cold_registry = self._read_cold_registry() if bridge_gaps else None
        cold_rotated: frozenset[int] = (
            frozenset(cold_registry["rotated"]) if cold_registry else frozenset()
        )
        cold_hash_by_sequence: dict[int, str] = (
            cold_registry["hash_by_sequence"] if cold_registry else {}
        )
        # A registry file that exists but did not survive
        # `_read_cold_registry`'s checks leaves every rotation gap
        # unexplained - correct (fail-closed), but the resulting break read
        # as a bare "record sequence is not contiguous" with no named cause
        # and no remedy. Say which file is the reason.
        registry_unreadable = bool(
            bridge_gaps and cold_registry is None and self.cold_registry.exists())
        for position, record in enumerate(records):
            if position < trusted_prefix:
                # Walked and hashed when the index was written; the files
                # carry the same stat identity now. The link into the tail
                # still starts from this record's sealed hash. Keyed off the
                # record's OWN sequence (not a blind +1) so a trusted prefix
                # that happens to start above 1 - the hot tier right after a
                # cold rotation - still hands the loop the right starting
                # point below.
                #
                # Unchanged stat identity
                # proves these bytes still match what the index recorded -
                # it says nothing about which PROJECT wrote them. Skipping
                # the identity check here let a record whose project_key
                # is not one of this archive's accepted_keys() ride the
                # trusted prefix straight past the exact check the tail
                # enforces below, so a verdict depended on how much of the
                # archive the index happened to cover. Cheap enough (a set
                # lookup, no hashing) to run unconditionally without
                # undoing what the index actually accelerates: the hash
                # work, not this.
                if record.get("project_key") not in self.accepted_keys():
                    if path_at is not None:
                        path = path_at(position)
                    else:
                        paths = self.event_paths()
                        path = paths[position] if position < len(paths) else None
                    return self._broken(
                        position, len(records), previous, record.get("sequence"),
                        path, '"project_key"', "record project identity mismatch")
                previous = record["record_hash"]
                expected_sequence = _sequence_of(record) + 1
                continue
            sequence = record.get("sequence")
            broken: tuple[str, str] | None = None
            if record.get("schema_version") != SCHEMA_VERSION:
                broken = ('"schema_version"', "record schema mismatch")
            elif record.get("project_key") not in self.accepted_keys():
                broken = ('"project_key"', "record project identity mismatch")
            elif sequence != expected_sequence:
                # A gap here is legitimate ONLY when every sequence
                # number it skips was moved to a cold segment by
                # `rotate_to_cold`, AND this record's own `previous_hash` -
                # sealed at append time, long before any rotation existed -
                # already equals the registry's recorded hash for the cold
                # record immediately before it. The registry does not MAKE
                # that link true; it only reports one the record's own
                # stored bytes already claim, so a forged registry entry
                # with no matching `previous_hash` still fails here exactly
                # like an unexplained gap always has. A gap the registry
                # does not explain is reported precisely as before cold-registry bridging existed.
                # The bridging hash must BE a hash. A
                # bare `.get(...) == record.get("previous_hash")` passed on
                # `None == None` - a registry entry the `rotated` list claims
                # and `hash_by_sequence` does not hold, against a record whose
                # own `previous_hash` is null - and blessed a record linked to
                # nothing. The sentence THREAT-MODEL.md makes about this
                # bridge ("the registry only confirms a link the record's own
                # stored bytes already claim") is only true with this guard.
                bridging_hash = cold_hash_by_sequence.get(
                    sequence - 1 if isinstance(sequence, int) else -1)
                gap_explained = (
                    isinstance(sequence, int) and not isinstance(sequence, bool)
                    and sequence > expected_sequence
                    and all(s in cold_rotated for s in range(expected_sequence, sequence))
                    and isinstance(bridging_hash, str) and bool(bridging_hash)
                    and bridging_hash == record.get("previous_hash")
                )
                if gap_explained:
                    previous = record.get("previous_hash")
                    expected_sequence = sequence
                else:
                    reason = (
                        f"record sequence is not contiguous (expected {expected_sequence})")
                    if registry_unreadable:
                        reason += (
                            f"; the cold registry ({self.cold_registry.name}) is present "
                            "but unreadable or incomplete, so no rotation can be "
                            "explained - restore it, or run `godmode doctor` for the "
                            "cross-tier walk")
                    broken = ('"sequence"', reason)
            if broken is None and record.get("previous_hash") != previous:
                broken = ('"previous_hash"', "record chain link is invalid")
            elif broken is None and record.get("record_hash") != _record_hash(record):
                broken = ('"record_hash"', "record content hash is invalid")
            if broken is not None:
                # The directory listing is only walked once a break is
                # actually found - every intact verify (the common case, run
                # on every read) pays nothing extra for it.
                needle, reason = broken
                if path_at is not None:
                    path = path_at(position)
                else:
                    paths = self.event_paths()
                    path = paths[position] if position < len(paths) else None
                return self._broken(position, len(records), previous, sequence,
                                     path, needle, reason)
            previous = record["record_hash"]
            expected_sequence += 1
        if full_walk:
            # Every record just verified from scratch - any C-8-shaped
            # checkpoint seen along the way is now provably intact, so it
            # goes in the registry for the next call to trust without
            # re-walking. Best-effort: a write failure here costs only the
            # NEXT read's acceleration, not this read's correctness.
            self._extend_checkpoint_registry(records)
        result = {
            "valid": True,
            # `records`/`record_count` are the records THIS walk saw - the hot
            # tier, on the ordinary read path. A rotation
            # makes that number shrink, which reads as an archive losing
            # history when it has only moved storage, so the number that never
            # shrinks (the highest sequence ever sealed, cold included) is
            # reported beside them rather than silently substituted - the two
            # existing keys have position semantics the broken branch below
            # and `verify_cold()`'s combined walk both depend on.
            "records": len(records),
            "sealed_records": max(expected_sequence - 1, 0),
            "head_hash": previous,
            "ok": True,
            "record_count": len(records),
            "first_broken_sequence": None,
            "first_broken_path": None,
            "first_broken_line": None,
            "message": "chain intact",
        }
        # B4-1: the chain walk above proves the records present link up; it
        # cannot prove none were removed from the END. Only the anchor can:
        # the chain must still PASS THROUGH the anchored head. Shorter than
        # anchored, or a different hash at the anchored length, is a
        # truncation. Longer is the legal crash-window lag. `check_anchor`
        # exists solely for `reanchor()`, which must verify the surviving
        # structure while the anchor itself is what's stale.
        if check_anchor:
            anchor_state = self._read_chain_anchor()
            if anchor_state is None:
                result["anchor"] = "anchor-absent"
            else:
                gap = self._anchor_gap(anchor_state, records)
                if gap is not None:
                    # Lesson 4128, and its third live occurrence (2026-08-28,
                    # two projects in one day): a concurrent writer appends
                    # the record file and then the anchor, so a reader
                    # holding a pre-append listing can see anchor N+1
                    # against N files - a false truncation that self-heals.
                    # One re-read after a short beat, against FRESH disk
                    # state, separates that race from a real truncation;
                    # only the persistent mismatch raises. The remedy the
                    # alarm names (db --reanchor) is destructive on a false
                    # positive, which is why the beat is worth its 150ms.
                    time.sleep(0.15)
                    fresh_anchor = self._read_chain_anchor()
                    if fresh_anchor is None:
                        gap = None
                    else:
                        fresh = [self._read_json(path) for path in self.event_paths()]
                        gap = self._anchor_gap(fresh_anchor, fresh)
                if gap is not None:
                    self._raise_truncated(*gap)
                result["anchor"] = "anchored"
        return result

    @staticmethod
    def _broken(position: int, total: int, previous: str | None, sequence: Any,
                path: Path | None, needle: str, reason: str) -> dict[str, Any]:
        """The dict `verify()` returns for the first record that breaks the
        chain: which sequence, which file, and which line in it - a tamper
        report that names the record instead of sending the reader to grep.

        `records` mirrors the intact branch's meaning (the total records
        present on disk, `total`); `record_count` is this branch's own
        number, how many of those verified good before the break (`position`).
        """
        line = Chronicle._line_of(path, needle) if path is not None else None
        location = f"{path.name}:{line}" if path is not None else "an unreadable location"
        # A schema-broken (or otherwise non-numeric) record may carry no
        # usable sequence at all - fall back to 0 rather than leaving None
        # sitting in ok=False's payload and the message reading "sequence None".
        named_sequence = int(sequence) if isinstance(sequence, int) and not isinstance(sequence, bool) else 0
        message = f"chain broken at sequence {named_sequence} ({location}): {reason}"
        return {
            "valid": False,
            "records": total,
            "head_hash": previous,
            "ok": False,
            "record_count": position,
            "first_broken_sequence": named_sequence,
            "first_broken_path": path.name if path is not None else None,
            "first_broken_line": line,
            "message": message,
        }

    @staticmethod
    def _line_of(path: Path, needle: str) -> int:
        """The 1-based line in `path` where `needle` first appears as a
        TOP-LEVEL key (json.dump(indent=2)'s first nesting level: exactly
        two leading spaces before the quoted key) - a nested payload key
        that happens to share the same name must never win. 1 when not
        found, so a caller always gets a usable line rather than None."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return 1
        anchored = "  " + needle
        for number, line in enumerate(text.splitlines(), 1):
            if line.startswith(anchored):
                return number
        return 1

    def _read_chain_anchor(self) -> dict[str, Any] | None:
        """The anchored {length, head_hash}, or None when absent/unreadable.

        Unlike the head hint, absence here is REPORTED (`verify()` returns
        `anchor: "anchor-absent"`) rather than silently rebuilt - a fresh or
        pre-anchor archive legitimately has none, and the first append
        writes one; but nothing ever trusts an absent anchor as proof the
        tail is intact."""
        try:
            value = json.loads(self.chain_anchor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        length = value.get("length")
        head_hash = value.get("head_hash")
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            return None
        if length == 0 and head_hash is None:
            return {"length": 0, "head_hash": None}
        if not isinstance(head_hash, str):
            return None
        return {"length": length, "head_hash": head_hash}

    def _write_chain_anchor(self, length: int, head_hash: str | None) -> None:
        """Atomic + fsynced (`_atomic_json`), AFTER the record file lands:
        a crash between the two leaves an anchor that under-counts by one,
        which reads as the legal lag the next append repairs - never as a
        truncation."""
        try:
            _atomic_json(self.chain_anchor, {"length": length, "head_hash": head_hash})
        except OSError:
            # An anchor that cannot be written must not fail the append its
            # record already sealed. It must also not leave the PREVIOUS
            # anchor standing: that one now under-counts the files, and an
            # under-counting anchor is exactly the shape `verify` reads as
            # the legal crash-window lag - so a persistent write failure
            # would look like a healthy archive forever. Removing it makes
            # the next read say `anchor-absent`, which is the honest answer,
            # and the next successful append re-establishes it.
            self.chain_anchor.unlink(missing_ok=True)

    def _anchor_gap(self, anchor_state: dict[str, Any],
                    records: list[dict[str, Any]]) -> tuple[int, int] | None:
        """(anchored, remaining) when the chain does not pass through the
        anchored head; None when it does.

        Matched by the anchored record's own
        `sequence` field, not by list POSITION - `records` here is
        `self.event_paths()`'s hot-only list, and once `rotate_to_cold` has
        removed older files, position `length - 1` no longer names the
        `length`-th record the way it always did before rotation existed (position
        and sequence agree only while nothing has ever been rotated). The
        anchor itself is untouched by rotation (`_write_chain_anchor` is
        never called by `rotate_to_cold`) - it still names the true total
        record count, and the record that count belongs to is always
        findable by matching `sequence`, in hot records unless every record
        ever written has been rotated away (checked via the cold registry's
        own bridging hash in that one edge case).
        """
        length = int(anchor_state["length"])
        if length == 0:
            return None
        highest_sequence = _sequence_of(records[-1]) if records else 0
        if length > highest_sequence:
            registry = self._read_cold_registry()
            cold_hash = registry["hash_by_sequence"].get(length) if registry else None
            if cold_hash is not None and cold_hash == anchor_state["head_hash"]:
                return None
            return length, len(records)
        for record in reversed(records):
            if _sequence_of(record) == length:
                if record.get("record_hash") != anchor_state["head_hash"]:
                    return length, len(records)
                return None
        # No HOT record carries that sequence, which on a
        # rotated archive means the anchored record is cold. The branch
        # above already knows how to answer from the registry's own recorded
        # hash; answer from it here too rather than skip the anchored-head
        # check silently. A registry that names no hash for it leaves the
        # check unanswerable from this call's inputs, which is exactly where
        # it stood before - unchanged, and still cross-checked by the gap
        # bridge on the next hot record.
        registry = self._read_cold_registry()
        cold_hash = registry["hash_by_sequence"].get(length) if registry else None
        if cold_hash is not None:
            return None if cold_hash == anchor_state["head_hash"] else (length, len(records))
        return None

    @staticmethod
    def _raise_truncated(anchored: int, remaining: int) -> None:
        raise ArchiveError(
            f"tail-truncated: the chain anchor records {anchored} sealed "
            f"records but {remaining} remain, or the chain no longer passes "
            "through the anchored head - the newest records were removed or "
            "replaced. Recover them, or run `godmode db --reanchor` as an "
            "explicit operator decision (the reanchor itself is chronicled)."
        )

    def _read_head(self) -> dict[str, Any] | None:
        """Best-effort read of the head cache; anything doubtful reads as absent.

        The head cache is an optimisation, never an authority: a corrupt or
        implausible head must degrade to the full-chain scan rather than fail an
        append or, worse, be trusted.
        """
        try:
            value = json.loads(self.head.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        sequence = value.get("sequence")
        record_hash = value.get("record_hash")
        if not isinstance(sequence, int) or sequence < 0:
            return None
        if sequence == 0 and record_hash is None:
            return {"sequence": 0, "record_hash": None}
        if not isinstance(record_hash, str):
            return None
        return {"sequence": sequence, "record_hash": record_hash}

    def _write_head(self, sequence: int, record_hash: str | None) -> None:
        # A plain overwrite, not _atomic_json: the head is a disposable hint,
        # every reader and writer of it holds the write lock, and a torn write
        # merely fails _read_head's parse and triggers the full-scan rebuild.
        # The temp-file/replace/fsync dance would cost several syscalls per
        # append to protect a file whose loss costs nothing.
        try:
            self.head.write_text(
                json.dumps(
                    {"sequence": sequence, "record_hash": record_hash},
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            self.head.unlink(missing_ok=True)

    def _tail_entry(self) -> tuple[int, Path | None]:
        """Count record files and find the newest without glob's pattern machinery.

        Profiling showed glob dominating the append fast path. Record names start
        with a zero-padded 12-digit sequence, so the lexicographic maximum IS the
        newest record -- the same ordering event_paths() relies on -- and one
        name listing gives both the count and the tail. The count matters: a head
        that undercounts the files (a crash between the record and head writes,
        or a record file deleted out of the MIDDLE of the chain) must be refused,
        or the next append would fork the chain.

        This returns the FILE COUNT, exactly as it
        did before the cold tier existed. Returning the tail's sequence number
        here instead made `_chain_tail`'s guard below compare a sequence against
        a sequence, which cannot see files missing from the middle - a plain
        filesystem deletion then rode the append fast path straight past a chain
        the archive's own `verify()` already knew was broken. The tail's sequence
        number is a separate question with a separate accessor
        (`_tail_sequence_of`), and `_chain_tail` reconciles the two against the
        cold registry rather than conflating them.
        """
        count = 0
        last_name: str | None = None
        try:
            names = os.listdir(self.events)
        except OSError:
            return 0, None
        for name in names:
            if not _is_record_name(name):
                continue
            count += 1
            if last_name is None or name > last_name:
                last_name = name
        return count, (self.events / last_name) if last_name else None

    @staticmethod
    def _tail_sequence_of(path: Path | None) -> int:
        """The sequence number a record file's own name carries - the same
        zero-padded 12-digit prefix `event_paths()` orders by - or 0 when there
        is no file. Deliberately separate from `_tail_entry`'s file COUNT
        Once `rotate_to_cold` can remove an older file, the
        count and the tail sequence are different numbers, and each guard needs
        the one it actually means."""
        if path is None:
            return 0
        try:
            return int(path.name[:12])
        except ValueError:
            return 0

    def _files_account_for(self, count: int, tail_sequence: int) -> bool:
        """Whether the record files on disk, plus the sequences the cold
        registry says `rotate_to_cold` moved out from under them, account for
        EVERY sequence from 1 to `tail_sequence` - the reconciliation
        `_tail_entry`'s file count exists to feed (review A, B2).

        With no cold tier this is `count == tail_sequence`, the pre-Task-7
        check byte for byte. A rotation explains exactly the files it removed
        and nothing else, so a file deleted out of the middle leaves the sum
        short, the append fast path is refused, and the full verified scan
        names the break instead of extending a forked chain.
        """
        if count == tail_sequence:
            return True
        if count > tail_sequence:
            # More files than sequence numbers: nothing legitimate produces
            # this, and no registry entry can explain it away.
            return False
        registry = self._read_cold_registry()
        if registry is None:
            return False
        rotated_below = sum(1 for s in registry["rotated"] if s <= tail_sequence)
        return count + rotated_below == tail_sequence

    def _chain_tail(self, *, fresh: bool = False) -> tuple[int, str | None]:
        """Locate the chain tail without re-reading history. Caller holds the lock.

        Re-verifying the whole chain on every append made writes O(history), so a
        long-lived archive punished the very habit -- frequent recording -- the
        product exists to encourage. The head cache is validated against the last
        record file only (count, sequence, stored hash, and that record's own
        hash); any mismatch falls back to the full verified scan and rebuilds the
        cache. Tamper detection is not weakened: verify()/doctor still walk the
        entire chain.

        Every answer comes from disk as it stands under the lock, never from
        this process's own memory. `fresh=True` skips the head hint entirely
        (a retry after a sequence claim was refused).
        """
        count, last_path = self._tail_entry()
        tail_sequence = self._tail_sequence_of(last_path)
        head = None if fresh else self._read_head()
        # BOTH halves, or the fast path is refused. The head must
        # name the tail's own sequence, AND the files present must account for
        # every sequence below it (directly, or through the cold registry's own
        # record of what was rotated away).
        if (head is not None and head["sequence"] == tail_sequence
                and self._files_account_for(count, tail_sequence)):
            if last_path is None:
                return 0, None
            try:
                last = self._read_json(last_path)
            except ArchiveError:
                last = None
            if (
                last is not None
                and last.get("sequence") == head["sequence"]
                and last.get("record_hash") == head["record_hash"]
                and _record_hash(last) == head["record_hash"]
            ):
                # B4-1: the hint validates count + last record, both of
                # which a tail-deleter who refreshes the hint controls -
                # the anchor does not pass through their hands. Checked
                # here too, or every append would ride the fast path
                # straight past it. (`anchored < count` prefix divergence
                # is left to the slow path's full verify - this guard's
                # job is the fast path's own blind spot: a shortened tail
                # behind a plausible hint.)
                anchor_state = self._read_chain_anchor()
                if anchor_state is not None:
                    # Compared against the tail SEQUENCE, not the file count:
                    # the anchor records how many records were ever sealed,
                    # which a rotation does not change (it moves storage, never
                    # history). `_files_account_for` above is what holds the
                    # file count itself to account.
                    if anchor_state["length"] > tail_sequence:
                        self._raise_truncated(anchor_state["length"], tail_sequence)
                    if (anchor_state["length"] == tail_sequence and tail_sequence
                            and last.get("record_hash") != anchor_state["head_hash"]):
                        self._raise_truncated(anchor_state["length"], tail_sequence)
                return head["sequence"], head["record_hash"]
        # A pinned identity (a hook process) is the directory as it stood
        # when the pin was taken; other processes may have sealed records
        # since. Reading the tail through it handed a hook its own stale
        # list the moment the head hint failed to validate (a writer killed
        # between its record and its hint, say): the next record reused a
        # sequence already on disk, with the same previous_hash - a fork.
        # Re-scan first, so the read below reflects the directory now.
        if self._pinned_identity is not None:
            self._pinned_identity = (True, self._events_identity())
        records = self.read_events(verify=True)
        # The true tail is the highest sequence ever sealed, which is
        # not always the last HOT record - `self.events` holds only what no
        # rotation has moved. The cold registry is
        # consulted whenever it names a HIGHER sequence, not only when the hot
        # tier is empty. `rotate_to_cold` refuses to move the tail and
        # `eligible_for_expiry` never selects it, so an ordinary pass should
        # never produce that shape - but reading the tail off the last hot
        # record while a higher one sits cold would hand the next append a
        # sequence number already sealed, and a forked chain is not a failure
        # mode to leave resting on one guard.
        registry = self._read_cold_registry()
        cold_tail = max(registry["rotated"]) if registry and registry["rotated"] else 0
        hot_tail = _sequence_of(records[-1]) if records else 0
        if cold_tail > hot_tail:
            tail_sequence = cold_tail
            tail_hash = registry["hash_by_sequence"].get(cold_tail)
        elif records:
            tail_sequence = hot_tail
            tail_hash = records[-1]["record_hash"]
        else:
            tail_sequence, tail_hash = 0, None
        self._write_head(tail_sequence, tail_hash)
        return tail_sequence, tail_hash

    def _sequence_sealed(self, sequence: int) -> bool:
        """Whether a record file for `sequence` is on disk (hot tier) or the
        cold registry says one was sealed and rotated."""
        prefix = f"{sequence:012d}-"
        try:
            names = os.listdir(self.events)
        except OSError:
            names = []
        if any(name.startswith(prefix) and _is_record_name(name) for name in names):
            return True
        registry = self._read_cold_registry()
        return bool(registry and sequence in registry["rotated"])

    def _claim_abandoned(self, path: Path, sequence: int) -> bool:
        """A claim left by a writer that died before sealing: no record
        carries its sequence and its holder is not running. A claim whose
        record exists is never abandoned - that sequence is taken."""
        if self._sequence_sealed(sequence):
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
        pid = _payload_pid(text)
        if pid is not None:
            return not _pid_alive(pid)
        # Created but never written: the holder died in between, or is
        # writing right now. Only age tells those apart.
        return age > 10

    def _claim_sequence(self, sequence: int) -> Path:
        """Take `sequence` exclusively before its record is written.

        O_EXCL on `<sequence>.claim`: of any two writers that derived the
        same sequence, exactly one creates it. The loser raises
        `_SequenceTaken`. A claim ABOVE this one means a writer already
        sealed past this sequence (claims below the newest are pruned only
        after a later record lands), so this writer's view of the tail is
        stale and it is refused too. Abandoned claims (holder dead, nothing
        sealed) are cleared rather than wedging the archive."""
        claims = self.sequence_claims
        try:
            claims.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ArchiveError(f"cannot create {claims} ({exc.strerror or exc})") from exc
        path = claims / f"{sequence:012d}.claim"
        for attempt in (1, 2):
            try:
                descriptor = os.open(
                    _syscall_path(path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            except FileExistsError:
                if attempt == 1 and self._claim_abandoned(path, sequence):
                    path.unlink(missing_ok=True)
                    continue
                raise _SequenceTaken(
                    f"sequence {sequence} is already claimed by another writer")
            try:
                os.write(descriptor, f"{os.getpid()}\n{uuid.uuid4().hex}\n".encode())
            finally:
                os.close(descriptor)
            break
        try:
            others = os.listdir(claims)
        except OSError:
            others = []
        for name in others:
            head, _, suffix = name.partition(".")
            if suffix != "claim" or not head.isdigit() or int(head) <= sequence:
                continue
            higher = claims / name
            if self._claim_abandoned(higher, int(head)):
                higher.unlink(missing_ok=True)
                continue
            path.unlink(missing_ok=True)
            raise _SequenceTaken(
                f"sequence {int(head)} is already claimed, above {sequence}")
        return path

    def _clear_claims_above(self, tail: int) -> None:
        """Drop every claim above `tail` - only for an explicit operator
        decision that the chain ends at `tail` (reanchor, fork repair)."""
        try:
            names = os.listdir(self.sequence_claims)
        except OSError:
            return
        for name in names:
            head, _, suffix = name.partition(".")
            if suffix == "claim" and head.isdigit() and int(head) > tail:
                (self.sequence_claims / name).unlink(missing_ok=True)

    def _prune_claims(self, sealed: int) -> None:
        """Drop claims below the one just sealed (best-effort). Pruning only
        BELOW a sealed record keeps the refusal sound: any sequence whose
        claim is gone already has its record on disk and a higher claim
        standing, which a stale writer's claim check sees."""
        try:
            names = os.listdir(self.sequence_claims)
        except OSError:
            return
        for name in names:
            head, _, suffix = name.partition(".")
            if suffix == "claim" and head.isdigit() and int(head) < sealed:
                try:
                    (self.sequence_claims / name).unlink()
                except OSError:  # godmode: swallow-ok: a leftover claim below the tail is inert
                    pass

    def _write_record(
        self,
        kind: str,
        subject: str,
        data: dict[str, Any],
        evidence: list[str],
        *,
        sequence: int,
        previous_hash: str | None,
        writer: str | None = None,
    ) -> dict[str, Any]:
        """Seal and persist one record. Caller holds the lock and has scanned the payload.

        The record file lands before the head cache on purpose: a crash between
        the two leaves a head that undercounts, which _chain_tail detects and
        repairs from the files -- the files are the truth, the head is a hint.
        """
        identifier = uuid.uuid4().hex
        # Computed here (rather than required from every caller) so
        # the one direct caller outside append() (expunge()'s tombstone)
        # still gets a real derivation instead of an omitted field.
        if writer is None:
            writer = derive_writer()
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "project_key": self.anchor.project_key,
            "sequence": sequence,
            "record_id": identifier,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "anchor_fingerprint": anchor_fingerprint(self.anchor),
            # Every record attributes its author, so drift between models is
            # traceable on any kind, not only attestations.
            "agent": writer_fingerprint(),
            # Who wrote it and how much that writer is trusted. Old
            # records (sealed before this field existed) simply lack it -
            # `record_writer`/`record_trust` read that absence as `agent`,
            # and the hash below covers only whatever keys are actually
            # present, so nothing about an old record's stored hash changes.
            "writer": writer,
            "trust": TRUST_ORDER[writer],
            "kind": kind,
            "subject": subject,
            "data": data,
            "evidence": evidence,
            "previous_hash": previous_hash,
        }
        record["record_hash"] = _record_hash(record)
        destination = self.events / f"{sequence:012d}-{identifier}.godmode.json"
        claim = self._claim_sequence(sequence)
        try:
            _atomic_json(destination, record)
        except BaseException:
            # Nothing sealed: give the sequence back, or the next writer
            # would have to wait for this process to exit to take it.
            claim.unlink(missing_ok=True)
            raise
        self._prune_claims(sequence)
        # B4-1 ordering: record first, anchor second, hint last. A crash
        # after the record leaves the anchor lagging by one (legal, repaired
        # by the next append); an anchor ahead of the files can only mean
        # truncation.
        self._write_chain_anchor(sequence, record["record_hash"])
        self._write_head(sequence, record["record_hash"])
        # Field walk 2026-09-05: the hook's own append used to invalidate
        # the parsed cache, so its next read re-parsed every record file
        # (two full reads per hook on a 9.3k-record archive). The record
        # just sealed continues the verified chain the cache holds, so the
        # cache extends by one - into a NEW list, so a caller holding the
        # old one never sees it mutate - and the identity re-scans once.
        cache = self._events_cache
        # Compared against the cached tail's own
        # SEQUENCE, not the list's length. After any rotation the hot list is
        # shorter than the tail sequence forever, so `len(cache) == sequence
        # - 1` was false on every append for the life of the archive and the
        # parsed cache was dropped every time - the one read this codebase
        # works hardest to avoid, re-paid on every write.
        cached_tail = (_sequence_of(cache[-1]) if cache else 0) if cache is not None else None
        if (cache is not None and cached_tail == sequence - 1
                and self._events_cache_key is not None):
            self._events_cache = cache + [record]
            identity = self._events_identity()
            self._events_cache_key = identity
            self._events_verified_key = identity
            if self._pinned_identity is not None:
                self._pinned_identity = (True, identity)
        else:
            self._drop_events_cache()
        # The enforce-lesson index advances the same way, one record at
        # a time, straight from the record just sealed - never a re-read.
        # `_enforce_index_upto` starting at 0 collides with nothing here
        # (unlike `_events_cache_key`, 0 is never ambiguous with "not
        # caught up yet"), so this fires on every append once the index is
        # caught up, lesson or not - a lesson append never routes through
        # `_sync_enforce_index` at all (self-lockout's early return), so
        # without this it would never learn about its own kind's writes.
        def _fold_into(entries: dict[str, dict[str, Any]]) -> None:
            if kind == "lesson":
                enforce = data.get("enforce")
                entries[subject] = {
                    "sequence": sequence,
                    "status": str(data.get("status", "active")).strip().lower(),
                    "guard": str(data.get("generalized_guard") or ""),
                    "enforce": enforce if isinstance(enforce, dict) else None,
                }

        if self._enforce_index_upto == sequence - 1:
            _fold_into(self._enforce_lessons_by_subject)
            self._enforce_index_upto = sequence
            # Refresh the on-disk sidecar
            # every time the in-process index stays caught up - cheap (one
            # small JSON write, no record read), and it is what lets the
            # NEXT fresh process (this append's own count/head_hash, which
            # this record just became) skip the scan entirely instead of
            # re-earning it once per process forever.
            self._write_enforce_index(sequence, record["record_hash"])
        else:
            # NOT caught up in-process - the
            # common case is a `writer == "hook"` append, which never calls
            # `_sync_enforce_index` at all (`_enforced_refusal`'s own early
            # return for `writer == "hook"`), so a fresh process whose FIRST
            # write is a hook append reaches here with `_enforce_index_upto`
            # still 0 no matter how fresh the on-disk sidecar actually is.
            # Left alone, that append advances `count`/`head_hash` and
            # leaves the sidecar describing the PREVIOUS head - the next
            # fresh non-hook writer would then see a stale key and re-pay
            # the full `read_events()` walk (measured: 4,003 record reads
            # at N=4,000). This append's own pre-image is already in hand
            # as `(sequence - 1, previous_hash)` - the sidecar this append
            # is about to make stale, if it is still fresh for the head
            # this append started from - so adopting it costs one small
            # JSON read, zero record reads, under the SAME key check
            # `_read_enforce_index` always applies (no new trust: a mismatch
            # returns `None` and this simply does nothing, same as before).
            adopted = self._read_enforce_index(sequence - 1, previous_hash)
            if adopted is not None:
                self._enforce_lessons_by_subject = adopted
                _fold_into(self._enforce_lessons_by_subject)
                self._enforce_index_upto = sequence
                self._write_enforce_index(sequence, record["record_hash"])
        return record

    # Kinds a different actor may always append against someone
    # else's subject - collaborative-by-design, never a closure. Every
    # other kind's `--status closed` is single-writer.
    _SINGLE_WRITER_EXEMPT_KINDS = frozenset({"request", "claim"})

    def _subject_creator(self, kind: str, subject: str) -> dict[str, Any] | None:
        """Whichever record first used this (kind, subject) pair - the
        subject's owner. `None` when nothing has claimed it yet (this append
        would be the first, i.e. the creation itself)."""
        for record in self.read_events(verify=False):
            if record.get("kind") == kind and record.get("subject") == subject:
                return record
        return None

    def _subject_creator_agent_id(self, kind: str, subject: str) -> str | None:
        """The `agent_id` of the subject's owner - see `_subject_creator`."""
        creator = self._subject_creator(kind, subject)
        return None if creator is None else (creator.get("agent") or {}).get("agent_id")

    def _chronicled_session_role(self) -> str | None:
        """`checker`, but only when it is OPERATOR-GRANTED and belongs to
        THIS caller.

        An earlier version read a bare `GODMODE_SESSION_ROLE=checker` claim back
        against the archive's LATEST `session` record - attributable to
        *some* `session open --role checker` call, but not necessarily one
        THIS process made, and that call itself was ungated: any process
        could run it and mint `checker` for itself. Both holes are closed
        here, together:

          1. Identity: the env var is `GODMODE_SESSION` - the session id
             (`S-{record_hash[:12]}`) that `godmode_console.cmd_session_open`
             stamps on ITS OWN process after a session actually opens -
             never a role claim. A process that never ran `session open`
             itself has no such id and inherits nothing, even when some
             OTHER, unrelated checker session exists in the same archive.
          2. Grant: the named record is honoured as `checker` only when it
             was itself written with operator trust - `role_granted_by:
             "operator"` in its `data` AND `writer == "operator"` on the
             record (`open_session(..., operator_verified=True)`), which
             `cmd_session_open` only reaches after verifying `--as-operator`
             through the same password/interactive path every other
             operator write uses. A `session open --role checker` run
             without that verification writes a record with neither, so
             this never matches it.

        Stopping there would close the "latest record" bug but leave
        a narrower one open: naming a DIFFERENT, genuinely operator-granted
        session id would still mint `checker` for whichever process asked,
        because nothing tied the record to the caller - the id is not a
        secret (`godmode history --kind session --json` prints it, and the
        grant never expires). So this is closed too:

          3. Ownership: the record's `data["agent"]["agent_id"]` -
             stamped by `open_session` via `agent_fingerprint()` /
             `writer_fingerprint()` onto the SAME process that ran
             `session open` - must equal this caller's own `agent_id()`.
             A process that merely learns another session's id (by reading
             history, or being handed it) no longer inherits that session's
             grant.

        Like the single-writer guard (`_subject_creator_agent_id` /
        `agent_id()` above), this ownership check is inert wherever
        per-agent ids are undeclared: with no `GODMODE_AGENT_ID` set, every
        process in the project shares one default id, so "belongs to this
        caller" is trivially true for all of them. It bites exactly where
        the single-writer guard already bites - once the host declares
        distinct ids per agent.

        `GODMODE_SESSION_ROLE` is gone entirely: it was a second, redundant
        claim about the same fact this now reads directly off the one
        record that matters.
        """
        session_id = os.environ.get("GODMODE_SESSION", "").strip()
        if not session_id:
            return None
        for record in reversed(self.read_events(verify=False)):
            if record.get("kind") != "session":
                continue
            if f"S-{record['record_hash'][:12]}" != session_id:
                continue
            data = record.get("data") or {}
            if str(data.get("role", "")).strip().lower() != "checker":
                return None
            if str(data.get("role_granted_by", "")).strip().lower() != "operator":
                return None
            if record_writer(record) != "operator":
                return None
            granted_to = str((data.get("agent") or {}).get("agent_id", ""))
            if granted_to != agent_id():
                return None
            return "checker"
        return None

    def chronicled_session_role(self) -> str | None:
        """Public wrapper for `_chronicled_session_role` - the
        SAME derivation `append` uses to decide whether THIS process, right
        now, holds an operator-granted `checker` session belonging to its
        own `agent_id()`. Callers outside this module that need to assert
        "the caller currently holds real checker trust" (such as
        `godmode_bonds.ratify`) reuse this, never a second copy of
        the same rule."""
        return self._chronicled_session_role()

    def resolve_writer(self, *, role: str | None = None, as_operator: bool = False,
                        operator_verified: bool | None = None) -> str:
        """The `writer` value THIS process's next `append()` call would
        stamp, without actually writing anything.

        `_validate_supersedes` (console.py) needs
        to know the writer's trust rank BEFORE the write happens, to refuse
        a low-trust supersession of a high-trust record rather than
        discover the hole after `combine` has already run. Factored out of
        `append` itself (which now just calls this) rather than
        reimplemented at the call site, so the two can never resolve the
        same write as two different writers.
        """
        resolved_role = role if role is not None else self._chronicled_session_role()
        return derive_writer(
            role=resolved_role, as_operator=as_operator, operator_verified=operator_verified)

    # A lesson's own status values that take it
    # out of enforcement. Imported from `godmode_law`
    # rather than a separately-maintained copy - the two used to drift (a
    # `--status superseded` lesson stopped refusing writes here but kept
    # rendering as active law in the brief); one set now backs both.
    _ENFORCE_INACTIVE_STATUSES = _law.LESSON_DORMANT_STATUSES

    def _sync_enforce_index(self, count: int) -> None:
        """Advance the enforce-lesson index up to `count` (the archive's
        current record count, from the SAME `_tail_entry()`/`_chain_tail()`
        call the caller already made: this used to
        take its own `_tail_entry()` listing, a second `os.listdir()` per
        append the caller's own count already made redundant) - never
        rescanning what it already folded in.

        Three tiers, cheapest first:

        1. Already caught up (`count <= self._enforce_index_upto`): no work.
           `_write_record`'s own incremental bump keeps this true after
           every append THIS process makes, so a long-lived process (a
           session that appends many records) never falls through past
           here after its first sync.
        2. Behind, but the on-disk sidecar (`godmode-enforce.index.json`,
           see its own docstring above `_read_enforce_index`) is fresh for
           this exact `count`: load it - zero record reads, one small JSON
           parse. This is the fresh-process case (Blocking 1): every hook
           invocation and every write-only CLI call starts here, at
           `_enforce_index_upto == 0`, and a prior process's append already
           left the sidecar fresh for the head it just sealed.
        3. Behind, sidecar missing or stale: the one full `read_events()`
           walk this method ever pays, ONCE - after which it writes the
           sidecar so the NEXT fresh process lands on tier 2 instead of
           repeating this walk ("reads fall back to a
           scan ONCE and then write").

        A shrink (only possible after expunge/reanchor, which reset
        `_enforce_index_upto` to 0 and unlink the sidecar via
        `_drop_events_cache(rewrite=True)`) reads as "nothing folded in
        yet" here too and forces the same one-time rescan.

        Guards are read from `read_events(verify=False)` - unverified
        records. Harmless: `read_events()`'s OWN
        verified paths still run on every reading caller that asks for
        `verify=True`, catching real tampering there; a write that reads
        the archive to decide whether to refuse itself is not the
        chain-integrity check, and a tamperer with write access to inject a
        fake enforce lesson already has write access to fake anything else
        in the archive too (see THREAT-MODEL.md's "Out of scope").
        """
        if count <= self._enforce_index_upto:
            return
        if self._enforce_index_upto == 0 and count > 0:
            head = self._read_head()
            if head is not None and head["sequence"] == count:
                sidecar = self._read_enforce_index(count, head["record_hash"])
                if sidecar is not None:
                    self._enforce_lessons_by_subject = sidecar
                    self._enforce_index_upto = count
                    return
        records = self.read_events(verify=False)
        # A SEQUENCE, not the hot count. `count`
        # comes from `_chain_tail()` and `_write_record`'s own incremental
        # bump compares `_enforce_index_upto == sequence - 1`, so both ends
        # of this field have always been sequences; only this tier set it
        # from `len(records)`. On a rotated archive the two never agree
        # again, which switched I-1's acceleration off in both directions:
        # tier 1 stopped recognising a caught-up index (every append re-paid
        # the full walk) and tier 3 stopped refreshing the sidecar (every
        # fresh process re-paid it too).
        total = _sequence_of(records[-1]) if records else 0
        if total < self._enforce_index_upto:
            self._enforce_lessons_by_subject = {}
            self._enforce_index_upto = 0
        if total <= self._enforce_index_upto:
            return
        for record in records:
            if _sequence_of(record) <= self._enforce_index_upto:
                continue
            if record.get("kind") != "lesson":
                continue
            data = record.get("data") or {}
            enforce = data.get("enforce")
            subject = str(record.get("subject", ""))
            # Newest record per subject wins - the same dedup
            # `_guarded_lessons` (godmode_law.py) applies, so a superseding
            # or retiring write on the same subject overwrites the entry
            # the earlier enforcing lesson left here instead of stacking
            # beside it.
            self._enforce_lessons_by_subject[subject] = {
                "sequence": int(record.get("sequence", 0)),
                "status": str(data.get("status", "active")).strip().lower(),
                "guard": str(data.get("generalized_guard") or ""),
                "enforce": enforce if isinstance(enforce, dict) else None,
            }
        self._enforce_index_upto = total
        # Tier 3's write: persist what the expensive walk just found so the
        # next fresh process (even one that never gets past this same
        # refused write, since a refused write never reaches `_write_record`)
        # hits tier 2 instead of repeating this walk.
        head = self._read_head()
        if head is not None and head["sequence"] == total:
            self._write_enforce_index(total, head["record_hash"])

    def seed_enforce_index(self) -> None:
        """Freshen `godmode-enforce.index.json` outside any write lock.

        `_sync_enforce_index`'s tier-3
        fallback (a full `read_events()` walk, paid once per process when
        the sidecar is absent or stale) normally runs from inside
        `append()`'s `write_lock()` - fine for the sidecar's steady state
        (fast tier 2 thereafter), but re-review measured it at 12.93s on a
        real 18,964-record archive that had never had the sidecar at all,
        held inside a lock whose acquire deadline is 20s: the FIRST write
        after this feature lands on such an archive would stall every
        concurrent writer, hooks included, for that whole window.

        `godmode doctor` already pays a full unlocked `read_events()` walk
        of its own (its health check), so calling this from `cmd_doctor`
        folds the enforce lessons and persists the sidecar from that same
        unlocked context - before any write ever needs to. One operator
        action (`godmode doctor`, run once after upgrading) removes the
        window entirely; skipping it just means the first live write pays
        the walk instead, exactly as before this method existed.

        Idempotent and safe to call any time, any number of times:
        `_sync_enforce_index` itself no-ops once caught up (tier 1). The
        count passed in is `event_paths()` (a directory listing, not a
        parse of every file) rather than the head cache: the head cache is
        itself only an accelerator and can be missing or stale on exactly
        the kind of archive this exists for (one that predates a piece of
        this machinery), and trusting it here would make a stale count
        short-circuit tier 1's "already caught up" check into doing
        nothing at all.
        """
        # The tail SEQUENCE off the last filename, not the
        # file count - still one directory listing, no file parsed, but on a
        # rotated archive a count is smaller than the sequence this method's
        # own caller compares against, and passing one here would let tier 1
        # read "already caught up" while the index was behind.
        _count, last_path = self._tail_entry()
        self._sync_enforce_index(self._tail_sequence_of(last_path))

    def _enforced_refusal(
        self, kind: str, subject: str, data: dict[str, Any], writer: str, count: int
    ) -> dict[str, Any] | None:
        """The first ACTIVE enforce-carrying lesson whose predicate matches
        this write, or `None`. A `lesson` write is never checked against
        enforce rules at all (no self-lockout, per spec): the one act that
        must always stay possible is recording another lesson, including
        the corrective `--status superseded` one that lifts a bad guard.

        A `writer == "hook"` write is exempt too -
        `record_refusal`, the hook's own action/checkpoint writes, feed
        `authorize stage --from-last-refusal`, `observe --report`, and the
        session digest; an enforce lesson that happened to name one of
        those kinds would otherwise silently delete the gate's own audit
        trail with no signal. `godmode_law.ENFORCE_FORBIDDEN_KINDS` refuses
        authoring such a lesson in the first place; this is the second,
        independent layer for a hand-edited archive that already has one.

        `enforce_predicate_matches` raises
        `EnforceFieldTooLong` (never `ArchiveError`, so the generic
        malformed-predicate swallow below cannot catch it by accident) when
        a `matches` rule's field exceeds the scan cap - that refuses THIS
        write outright, fail-closed, rather than being treated as "this
        rule does not apply" and falling through to the next lesson.
        """
        if kind == "lesson" or writer == "hook":
            return None
        self._sync_enforce_index(count)
        for entry in self._enforce_lessons_by_subject.values():
            if entry["status"] in self._ENFORCE_INACTIVE_STATUSES:
                continue
            spec = entry["enforce"]
            if not spec or spec.get("kind") != kind:
                continue
            try:
                if _law.enforce_predicate_matches(str(spec.get("predicate", "")), data):
                    return entry
            except _law.EnforceFieldTooLong as exc:
                raise ArchiveError(
                    f"Refusing to write {kind} {subject!r}: {exc} (enforce "
                    f"lesson seq:{entry['sequence']})"
                ) from exc
            except ArchiveError:
                # A predicate that no longer parses cannot refuse anything -
                # the invariant at write time keeps this from happening for
                # anything remember() wrote, but a hand-edited archive is
                # never trusted to still be well-formed.
                continue
        return None

    def _refuse_incomplete_supersession(
        self, subject: str, data: dict[str, Any], count: int
    ) -> None:
        """A subject whose latest lesson carries
        an ACTIVE `enforce` guard stays armed until a later lesson on that
        same subject either re-affirms it (carries its own `--enforce`) or
        explicitly disarms it with any status that already takes it out of
        enforcement (`_ENFORCE_INACTIVE_STATUSES`, i.e.
        `godmode_law.LESSON_DORMANT_STATUSES` - `superseded`, `retired`, or
        `candidate`, not `superseded` alone) - an ordinary `remember --kind
        lesson` on the same subject with neither used to silently turn an
        executing guard back into advisory prose, with no signal anyone
        asked for that. Only checked for `kind == "lesson"` writes; nothing
        else can touch a lesson's own dedup slot."""
        self._sync_enforce_index(count)
        current = self._enforce_lessons_by_subject.get(subject)
        if current is None or not current.get("enforce"):
            return
        if current["status"] in self._ENFORCE_INACTIVE_STATUSES:
            return
        if data.get("enforce"):
            return
        if str(data.get("status", "active")).strip().lower() in self._ENFORCE_INACTIVE_STATUSES:
            return
        raise ArchiveError(
            f"Refusing lesson {subject!r}: its active enforce guard "
            f"(seq:{current['sequence']} - {current['guard']}) would be "
            "silently disarmed by this write - carry --enforce again to "
            "reaffirm the guard, or --status superseded, retired, or "
            "candidate to lift it on purpose"
        )

    def append(
        self,
        kind: str,
        subject: str,
        data: dict[str, Any],
        *,
        evidence: list[str] | None = None,
        dedupe: bool = False,
        role: str | None = None,
        as_operator: bool = False,
        operator_verified: bool | None = None,
    ) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ArchiveError(f"Unsupported Godmode record kind: {kind}")
        subject = subject.strip()
        if not subject or len(subject) > 200:
            raise ArchiveError(
                "Record subject must contain 1-200 characters - the subject "
                "is a label; put the detail in the record's value or data")
        validator = KIND_INVARIANTS.get(kind)
        if validator is not None:
            validator(data)
        evidence = evidence or []
        payload_for_scan = {"subject": subject, "data": data, "evidence": evidence}
        # A secret-shaped free-text field refuses the write outright,
        # naming exactly which field it found it in - never persisted, even
        # redacted, because the shape alone is enough to leak in a diff or a
        # shared archive copy.
        enforce_private_payload(payload_for_scan)
        writer = self.resolve_writer(
            role=role, as_operator=as_operator, operator_verified=operator_verified)
        self.initialize()
        with self.write_lock():
            if dedupe:
                # Re-recording an unchanged fact adds no information but grows the
                # chain forever; opt-in dedupe returns the existing record instead.
                # Only the most recent record of the same kind AND subject counts:
                # deduping across subjects would silently merge distinct facts,
                # and matching anything older would hide a real state change.
                for existing in reversed(self.read_events(verify=False)):
                    if existing.get("kind") != kind or existing.get("subject") != subject:
                        continue
                    if _canonical_json(existing.get("data")) == _canonical_json(data):
                        duplicate = dict(existing)
                        # Presentation-only marker: never persisted, so the
                        # stored record's hash is untouched.
                        duplicate["deduplicated"] = True
                        return duplicate
                    break
            closing_status = str(data.get("status", "")).strip().lower()
            if (kind not in self._SINGLE_WRITER_EXEMPT_KINDS
                    and (closing_status in CLOSING_STATUSES
                         or (kind == "lesson" and closing_status in LESSON_CLOSING_STATUSES)
                         or (kind == "review" and closing_status in REVIEW_CLOSING_STATUSES))
                    # Human override: a confirmed operator, or a
                    # declared checker, may always close a subject they did
                    # not create - the persistent-override property the
                    # guard exists alongside, not one it should defeat
                    # (without this, an operator sharing
                    # the writing agent's own `agent_id` was refused too,
                    # the moment a host declared per-agent ids).
                    and writer not in ("operator", "checker")):
                # Single writer: a subject's owner is whoever created
                # it. Closing is the one act another actor cannot do on its
                # behalf - hook-agnostic, since this compares `agent_id`
                # (the actual actor), never the `writer` role a hook process
                # happens to carry. `CLOSING_STATUSES` is
                # the full terminal set `status.remaining()` already treats
                # as closed - matching only the literal "closed" let a
                # foreign agent close the same subject with `--status done`
                # and the refusal never fired.
                creator_record = self._subject_creator(kind, subject)
                creator = (None if creator_record is None
                           else (creator_record.get("agent") or {}).get("agent_id"))
                this_actor = agent_id()
                if creator is not None and creator != this_actor:
                    raise ArchiveError(
                        f"Refusing to close {kind} {subject!r}: it was created "
                        f"by a different agent ({creator}); only its creator "
                        "can close it - append a request/claim against it "
                        "instead, or have the creator close it."
                    )
                # TRUST rank as well as identity, the
                # same rule `_validate_supersedes` already applies.
                # Identity alone is not enough: by
                # `godmode_constants`' own default, two undeclared agents on
                # one project SHARE an `agent_id`, so the check above is
                # vacuous in the default configuration - and a plain agent
                # could dismiss a contradiction an operator had adjudicated.
                # A lower-trust writer may not close what a higher-trust
                # writer opened; an equal or higher one still can.
                if creator_record is not None and TRUST_ORDER[writer] < record_trust(
                        creator_record):
                    raise ArchiveError(
                        f"Refusing to close {kind} {subject!r}: it was opened by a "
                        f"{record_writer(creator_record)} (seq:"
                        f"{_sequence_of(creator_record)}) and this write carries "
                        f"{writer} trust - a lower-trust writer may not close what a "
                        "higher-trust one opened. Re-run with `--as-operator`, or "
                        "append a request/claim against it instead."
                    )
            # Guards that execute, not advise.
            # `_chain_tail()` moves ahead of the enforce checks (fix round
            # 1, nit 9) so `_sync_enforce_index` can reuse its `count`
            # instead of listing the directory a second time - reading the
            # tail draws no sequence number by itself (only `_write_record`
            # below does, from `count + 1`), so a refused write still never
            # consumes one, exactly as before.
            base_data = data
            attempts = 5
            for attempt in range(1, attempts + 1):
                # A refused sequence claim means this view of the tail was
                # not the directory's: re-derive it from disk (no head
                # hint, no cached list) and try again.
                count, tail_hash = self._chain_tail(fresh=attempt > 1)
                if kind == "lesson":
                    self._refuse_incomplete_supersession(subject, base_data, count)
                matched = self._enforced_refusal(kind, subject, base_data, writer, count)
                if matched is not None:
                    raise ArchiveError(
                        f"Refusing to write {kind} {subject!r}: matches enforce "
                        f"lesson seq:{matched['sequence']} - {matched['guard']}"
                    )
                data = base_data
                if kind == "checkpoint":
                    # A checkpoint is itself a chain entry that later lets
                    # verify() bound its work to the tail after it. `chain_head`
                    # and `record_count` are the head hash and length as they
                    # stood immediately BEFORE this append - captured here,
                    # under the lock, from the same `_chain_tail()` call the
                    # write itself uses, so they can never disagree with the
                    # sequence/previous_hash this record is actually sealed
                    # with.
                    data = {**base_data, "chain_head": tail_hash, "record_count": count}
                try:
                    return self._write_record(
                        kind, subject, data, evidence,
                        sequence=count + 1, previous_hash=tail_hash,
                        writer=writer,
                    )
                except _SequenceTaken as exc:
                    if attempt == attempts:
                        raise ArchiveError(
                            f"Refusing to write {kind} {subject!r}: {exc}, and the "
                            "tail read from disk kept naming it. Another writer is "
                            "sealing at the same time outside the archive lock, or "
                            f"a claim in {self.sequence_claims} belongs to a process "
                            "that is still running. Retry; `godmode doctor` checks "
                            "the chain."
                        ) from exc
                    self._drop_events_cache()
                    time.sleep(0.02 * attempt)
            raise AssertionError("unreachable")

    def reanchor(self) -> dict[str, Any]:
        """B4-1's explicit recovery: accept the chain that remains as the
        chain, and say so on the record.

        The surviving records must still verify structurally (`check_anchor=
        False` - the anchor is exactly what is stale here); then the anchor
        is rewritten to match them, and the act itself is chronicled as an
        `action` record (counts only) - an operator decision that history
        got shorter, never a silent repair.
        """
        with self.write_lock():
            self._drop_events_cache(rewrite=True)
            records = [self._read_json(path) for path in self.event_paths()]
            # Verify() reports rather than raises now; reanchor() still
            # refuses to anchor a chain that does not verify structurally -
            # accepting a shorter chain is fine, accepting a BROKEN one is not.
            outcome = self.verify(records, check_anchor=False)
            if not outcome["ok"]:
                raise ArchiveError(outcome["message"])
            previous = self._read_chain_anchor()
            # A SEQUENCE, never the hot count.
            # Everywhere else in this file the anchor's `length` is the
            # highest sequence ever sealed - `_write_record` writes
            # `_write_chain_anchor(sequence, ...)`, and `_chain_tail`'s own
            # comment states the invariant ("the anchor records how many
            # records were ever sealed, which a rotation does not change").
            # `records` here is `event_paths()`'s HOT-only list, so on a
            # rotated archive `len(records)` is smaller than the tail's own
            # sequence, and writing it anchored the chain to a length no
            # record has. It self-healed only because the trailing append
            # below rewrites the anchor; remove that one prop - an enforce
            # lesson refusing this `action`, a disk error, a kill between
            # the two - and every later read raised `tail-truncated` with a
            # self-contradicting message ("records 6 ... but 6 remain": two
            # different units) whose named remedy wrote the same wrong
            # anchor again.
            anchored = _sequence_of(records[-1]) if records else 0
            self._write_chain_anchor(
                anchored, records[-1]["record_hash"] if records else None)
            # Claims above the accepted tail belong to records this decision
            # just gave up; left standing they would refuse every next write.
            self._clear_claims_above(anchored)
        record = self.append(
            "action", "chain-reanchored",
            {
                "anchored_length": anchored,
                "hot_records": len(records),
                "previous_anchor_length": previous["length"] if previous else 0,
                "previous_anchor_present": previous is not None,
            },
            evidence=[],
        )
        return {
            "reanchored": True,
            "anchored_length": anchored,
            "record": f"seq:{record['sequence']}",
        }

    def repair_fork(self) -> dict[str, Any]:
        """Undo a same-sequence fork at the chain's tip, as an explicit
        operator decision (`godmode doctor --repair-fork`).

        Accepts exactly one shape: the highest sequence is held by two or
        more record files, every one of them intact (its own hash checks),
        all naming the same `previous_hash`, which is the record before
        them - and nothing else in the hot tier is duplicated. Anything
        else is refused unchanged. The sibling the chain anchor names is
        kept (no anchor at that sequence: the earliest recorded); the
        others are moved - never deleted - into `godmode-quarantine/`
        beside the events directory. The repair is chronicled as its own
        record, and the chain is re-verified.
        """
        with self.write_lock():
            by_sequence: dict[int, list[Path]] = {}
            for path in self.event_paths():
                try:
                    number = int(path.name[:12])
                except ValueError as exc:
                    raise ArchiveError(
                        f"Refusing to repair: {path.name} carries no sequence") from exc
                by_sequence.setdefault(number, []).append(path)
            forked = sorted(s for s, paths in by_sequence.items() if len(paths) > 1)
            if not forked:
                raise ArchiveError("No fork to repair: every sequence is held by one record.")
            tip = max(by_sequence)
            if forked != [tip]:
                raise ArchiveError(
                    f"Refusing to repair: sequence(s) {forked} are duplicated, and only a "
                    f"single fork at the tip (sequence {tip}) has a safe repair.")
            siblings = [(path, self._read_json(path)) for path in by_sequence[tip]]
            previous_hashes = {record.get("previous_hash") for _path, record in siblings}
            for path, record in siblings:
                if (record.get("sequence") != tip
                        or record.get("record_hash") != _record_hash(record)):
                    raise ArchiveError(
                        f"Refusing to repair: {path.name} is not an intact record "
                        f"at sequence {tip}.")
            if len(previous_hashes) != 1:
                raise ArchiveError(
                    f"Refusing to repair: the records at sequence {tip} do not share "
                    "one previous record - that is not a fork of one chain.")
            (previous_hash,) = previous_hashes
            if tip > 1:
                before = by_sequence.get(tip - 1)
                predecessor = self._read_json(before[0]) if before else None
                expected = predecessor.get("record_hash") if predecessor else None
                if expected is None:
                    registry = self._read_cold_registry()
                    expected = registry["hash_by_sequence"].get(tip - 1) if registry else None
                if expected is None or expected != previous_hash:
                    raise ArchiveError(
                        f"Refusing to repair: the records at sequence {tip} do not link "
                        f"to the record at sequence {tip - 1}.")
            elif previous_hash is not None:
                raise ArchiveError("Refusing to repair: a first record names a predecessor.")
            anchor_state = self._read_chain_anchor()
            keeper: tuple[Path, dict[str, Any]] | None = None
            kept_by = "earliest"
            if anchor_state is not None and anchor_state["length"] > tip:
                raise ArchiveError(
                    f"Refusing to repair: the chain anchor records {anchor_state['length']} "
                    f"records but the chain ends at {tip} - that is a truncation, not a fork.")
            if anchor_state is not None and anchor_state["length"] == tip:
                named = [item for item in siblings
                         if item[1].get("record_hash") == anchor_state["head_hash"]]
                if len(named) != 1:
                    raise ArchiveError(
                        f"Refusing to repair: the chain anchor names no single record at "
                        f"sequence {tip}.")
                keeper, kept_by = named[0], "anchor"
            if keeper is None:
                keeper = min(siblings, key=lambda item: (
                    str(item[1].get("recorded_at") or ""), item[0].name))
            quarantine = self.root / "godmode-quarantine" / (
                f"fork-{tip:012d}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
            quarantine.mkdir(parents=True, exist_ok=True)
            moved: list[str] = []
            for path, _record in siblings:
                if path == keeper[0]:
                    continue
                os.replace(_syscall_path(path), _syscall_path(quarantine / path.name))
                moved.append(path.name)
            self._write_chain_anchor(tip, keeper[1]["record_hash"])
            self._write_head(tip, keeper[1]["record_hash"])
            self._drop_events_cache(rewrite=True)
            outcome = self.verify([self._read_json(path) for path in self.event_paths()])
            if not outcome["ok"]:
                raise ArchiveError(
                    f"Fork moved to {quarantine}, but the chain still does not verify: "
                    f"{outcome['message']}")
        record = self.append(
            "action", "chain-fork-repaired",
            {
                "sequence": tip,
                "kept": keeper[0].name,
                "kept_by": kept_by,
                "quarantined": moved,
                "quarantine": str(quarantine.relative_to(self.root)).replace("\\", "/"),
            },
            evidence=[],
        )
        verified = self.verify(self.read_events(verify=False))
        return {
            "repaired": True,
            "sequence": tip,
            "kept": keeper[0].name,
            "kept_by": kept_by,
            "quarantined": moved,
            "quarantine": str(quarantine),
            "record": f"seq:{record['sequence']}",
            "chain": verified,
        }

    def expunge(self, sequence: int, reason: str) -> dict[str, Any]:
        """Erase a record's payload after a secret slipped past the scanner.

        The sentinel matches secret *shapes*, so a real credential in an
        unfamiliar format can reach disk. Deleting the file would break the hash
        chain and hide that history changed; leaving it keeps leaking. This is
        the middle path: the record's data and evidence are replaced with an
        expunge marker, that record and every subsequent one are re-sealed so
        verify() still passes, and an `incident` tombstone records the sequence,
        reason, and the old record_hash -- the rewrite is visible and auditable,
        never silent. The one deliberate integrity trade: payload bytes are
        unrecoverable, which is the point.
        """
        reason = reason.strip()
        if not reason:
            raise ArchiveError("Expunge requires a non-empty reason")
        self.initialize()
        with self.write_lock():
            # Shallow copies of the CACHED records, not the cached objects
            # themselves: this method mutates every record from the target
            # onward in place (data/evidence/hash rewrite) before writing
            # them back, and read_events() now returns the same list object
            # on every cache hit. Mutating that shared list here would let a
            # later read_events() call see partially-expunged content that
            # was never verified or written to disk.
            records = [dict(record) for record in self.read_events(verify=True)]
            # Looked up by the record's OWN
            # `sequence` field, not by `records[sequence - 1]` - the two
            # agreed only while `self.events` held every record ever sealed
            # (position N-1 was always sequence N); `rotate_to_cold` can
            # remove older hot files, after which a position-based lookup
            # would silently expunge the WRONG record. A sequence this
            # archive has forgotten to cold is not reachable here at all -
            # expunge rewrites files in place, and a cold record has none
            # left in `self.events` to rewrite.
            position = next(
                (i for i, r in enumerate(records) if _sequence_of(r) == sequence), None)
            if position is None:
                cold = self._read_cold_registry()
                if cold and sequence in cold["rotated"]:
                    raise ArchiveError(
                        f"Record {sequence} is in the cold tier (`godmode forget` "
                        "rotated it); expunge only reaches hot records"
                    )
                raise ArchiveError(f"No record with sequence {sequence} to expunge")
            # This method re-seals every record
            # from the target onward, so a COLD record sitting at or after
            # the target is not something it can repair - the segment's
            # bytes are immutable, and the link they claim into the hot
            # tier is exactly what the re-seal invalidates. Refused here,
            # before a single file is rewritten, rather than discovered
            # afterwards as a chain both verifiers call broken.
            cold = self._read_cold_registry()
            trailing_cold = sorted(s for s in (cold["rotated"] if cold else []) if s > sequence)
            if trailing_cold:
                raise ArchiveError(
                    f"Refusing to expunge record {sequence}: sequence(s) {trailing_cold} "
                    "after it are in the cold tier (`godmode forget` rotated them). "
                    "Re-sealing the records from here on would break the link the "
                    "cold segment's own bytes already claim, and a cold segment "
                    "cannot be rewritten. Expunge only reaches a record that nothing "
                    "cold follows."
                )
            # The tombstone's sequence is minted the way `append` mints
            # one - through `_chain_tail()`, which inherits all three fork
            # defences (the cold registry is consulted whenever it names a
            # higher sequence than the hot tier holds). Read BEFORE the
            # re-seal, while the anchor still matches the chain on disk.
            # The guard above already rules out a cold tail above the hot
            # one; this is what proves it rather than assuming it.
            chain_tail_sequence, _chain_tail_hash = self._chain_tail()
            hot_tail_sequence = _sequence_of(records[-1]) if records else 0
            if chain_tail_sequence != hot_tail_sequence:
                raise ArchiveError(
                    f"Refusing to expunge record {sequence}: the chain's newest "
                    f"sealed record is {chain_tail_sequence}, but the hot tier ends "
                    f"at {hot_tail_sequence} - the tombstone would reuse a sequence "
                    "that is already sealed. Run `godmode doctor` for the full "
                    "cross-tier walk."
                )
            target = records[position]
            old_hash = target["record_hash"]
            tombstone_data = {
                "expunged_sequence": sequence,
                "reason": reason,
                "expunged_record_hash": old_hash,
            }
            # Scan the tombstone before touching any file: failing after the
            # re-seal would leave a rewritten chain with no tombstone -- exactly
            # the silent rewrite this method exists to avoid.
            enforce_private_payload(
                {"subject": "expunge", "data": tombstone_data, "evidence": []}
            )
            marker = {"expunged": True, "reason": reason}
            target["data"] = dict(marker)
            target["evidence"] = dict(marker)
            paths = self.event_paths()
            # The target's OWN previous_hash is unchanged by this rewrite -
            # only its data/evidence (and therefore its own record_hash)
            # change - so capturing it before the loop mutates it, rather
            # than re-deriving it from `records[position - 1]`, is what
            # keeps this correct whether the predecessor is another hot
            # record or (post-rotation) a cold one this list does not hold.
            previous = target.get("previous_hash")
            for index in range(position, len(records)):
                record = records[index]
                record["previous_hash"] = previous
                record["record_hash"] = _record_hash(record)
                _atomic_json(paths[index], record)
                previous = record["record_hash"]
            # Never backwards: `chain_tail_sequence` is the chain's own tail,
            # proved equal to the hot tail above, so this head write can no
            # longer hand `_chain_tail`'s fast path a sequence below one
            # already sealed cold.
            tail_sequence = chain_tail_sequence
            self._write_head(tail_sequence, previous)
            # The files just rewrote in place: whatever the cache holds is
            # pre-expunge and must never be extended by the tombstone.
            self._drop_events_cache(rewrite=True)
            tombstone = self._write_record(
                "incident", "expunge", tombstone_data,
                [f"expunged-sequence:{sequence}"],
                sequence=tail_sequence + 1, previous_hash=previous,
            )
        return {"expunged": sequence, "old_record_hash": old_hash, "tombstone": tombstone}

    def rotate_to_cold(self, sequences: list[int]) -> dict[str, Any]:
        """Move the given sequence numbers out of `self.events` into a new,
        immutable `events-cold-<n>.jsonl` segment - the mechanism `godmode_forget`'s expire operation
        drives. A record's own bytes travel unchanged (same
        `record_hash`/`previous_hash`/`sequence`); only their storage
        moves, one JSON object per line, sorted by sequence.

        Never chain-breaking, by construction and by order of operations:
        the segment is written and fsync'd, its sha256 is registered, and
        only THEN is any hot file deleted, so a crash at any point during
        this call leaves the chain fully intact and re-readable - either the
        hot files are all still there (nothing registered yet, or registered
        but not yet deleted: `verify()` reads them as ordinary present
        records, the registry's claim is simply redundant), or some subset
        has been deleted and the registry already explains exactly that
        subset (see `verify()`'s gap-bridging comment).

        A crash between the registry write and
        the unlinks is a RESUME, not a duplicate. A sequence that is both
        registered cold and still hot has work left to do - its hot file -
        so this re-unlinks it and carries on; only a sequence that is cold
        and no longer hot is refused as a duplicate, because there is
        nothing left to move. Before this, that window wedged `godmode
        forget` permanently ("already in the cold tier", every run, forever)
        on an archive whose chain was perfectly intact, and `verify_cold()`
        - which now collapses a byte-identical twin - reported tamper on it.

        Pins are refused outright, never merely relied upon to fall outside
        whatever kind list a caller passes - a `pin` record silently
        losing its place in the hot tier `pinned_evaluators()` actually
        reads would drop its own protection without anything saying so.
        """
        targets = sorted({int(s) for s in sequences})
        if not targets:
            return {"rotated": [], "segment": None, "count": 0, "resumed": []}
        with self.write_lock():
            records = self.read_events(verify=True)
            by_sequence = {_sequence_of(r): r for r in records}
            existing = self._read_cold_registry()
            already_cold = frozenset(existing["rotated"]) if existing else frozenset()
            missing = [s for s in targets
                       if s not in by_sequence and s not in already_cold]
            if missing:
                raise ArchiveError(
                    f"Cannot rotate sequence(s) {missing} to cold: not present in the hot tier"
                )
            # Cold AND no longer hot: the move already completed, there is
            # nothing left to do for it (review A, B3).
            duplicate = [s for s in targets if s in already_cold and s not in by_sequence]
            if duplicate:
                raise ArchiveError(
                    f"Sequence(s) {duplicate} are already in the cold tier and no longer "
                    "hold a hot record file; nothing left to rotate - read them with "
                    "`godmode history --seq <n>`"
                )
            # Cold AND still hot: a rotation that crashed between the
            # registry write and the unlinks. Finish it.
            resumed = [s for s in targets if s in already_cold]
            fresh = [s for s in targets if s not in already_cold]
            # The newest record stays hot.
            # `_chain_tail`'s slow path takes the tail from the LAST hot
            # record, so rotating the true tail while older records remain
            # would hand the next append a sequence number already sealed -
            # a forked chain, from a pass whose whole point is that it never
            # breaks one. The docstring used to ASSERT this invariant
            # ("rotate_to_cold only ever moves records OLDER than the tail")
            # while nothing enforced it; now it is enforced here, and
            # `godmode_forget.eligible_for_expiry` never selects the tail in
            # the first place, so a pass never reaches this refusal.
            tail_sequence = max(by_sequence) if by_sequence else 0
            if tail_sequence and tail_sequence in fresh:
                raise ArchiveError(
                    f"Refusing to rotate sequence {tail_sequence} to cold: it is the "
                    "chain's newest record, and the next append links from it - the "
                    "hot tier always keeps the tail"
                )
            pinned = [s for s in targets
                      if s in by_sequence and by_sequence[s].get("kind") == "pin"]
            if pinned:
                raise ArchiveError(
                    f"Refusing to rotate pin record(s) {pinned} to cold - pins stay hot so "
                    "the enforcement they record is never silently dropped"
                )
            segment_name: str | None = None
            if fresh:
                moving = [by_sequence[s] for s in fresh]
                text = "\n".join(
                    json.dumps(record, sort_keys=True, separators=(",", ":")) for record in moving
                ) + "\n"
                segment_index = 1 + (len(existing["segments"]) if existing else 0)
                segment_name = f"events-cold-{segment_index}.jsonl"
                segment_path = self.root / segment_name
                handle, temporary = tempfile.mkstemp(
                    prefix=".cold", suffix=".tmp", dir=str(self.root))
                with os.fdopen(handle, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    # The segment's bytes must be on the platter before the
                    # registry claims them: a crash between the two otherwise
                    # leaves a registry pointing at a segment whose contents
                    # never landed, and the hot files it describes are about
                    # to be unlinked.
                    os.fsync(fh.fileno())
                os.replace(temporary, segment_path)
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                rotated = sorted(already_cold | set(fresh))
                hash_by_sequence = dict(existing["hash_by_sequence"]) if existing else {}
                for record in moving:
                    hash_by_sequence[_sequence_of(record)] = record["record_hash"]
                segments = list(existing["segments"]) if existing else []
                segments.append({"file": segment_name, "sequences": fresh, "sha256": digest})
                # Registry lands BEFORE any hot file is removed - see the
                # docstring's crash-safety ordering.
                self._write_cold_registry(rotated, hash_by_sequence, segments)
            elif existing:
                # Resume-only: the segment holding them was written and
                # registered by the pass that crashed; name it rather than
                # writing a second copy of records already cold.
                for entry in existing["segments"]:
                    held = entry.get("sequences") if isinstance(entry, dict) else None
                    if isinstance(held, list) and any(s in held for s in resumed):
                        segment_name = entry.get("file")
            # Sequence read straight from the filename (same convention
            # `_tail_entry` relies on) - no need to open and parse every
            # hot file just to learn which one to delete.
            hot_paths: dict[int, Path] = {}
            for path in self.event_paths():
                try:
                    hot_paths[int(path.name[:12])] = path
                except ValueError:
                    continue
            for sequence in targets:
                path = hot_paths.get(sequence)
                if path is None:
                    continue
                # The ONE delete this method performs
                # goes through `_syscall_path`, exactly as `_atomic_json`
                # and `_read_json` already do. `Path.unlink` has no
                # long-path form, so past MAX_PATH Windows answered
                # `ENOENT` and `missing_ok=True` swallowed it - the record
                # file stayed hot, this call reported a successful
                # rotation, and the next pass wrote ANOTHER segment holding
                # records that had never left. The verb whose job is to
                # shrink the archive grew it, silently.
                target = _syscall_path(path)
                try:
                    os.remove(target)
                except FileNotFoundError:  # godmode: swallow-ok: already gone is this loop's goal, not a failure
                    pass
                except OSError as exc:
                    raise ArchiveError(
                        f"Cannot remove the hot record file for sequence {sequence} "
                        f"({path.name}): {exc.strerror or exc}. The cold segment and "
                        "its registry entry are already on disk, so the record is "
                        "safe - re-run `godmode forget` once the file is writable "
                        "(close whatever holds it open, or clear its read-only flag) "
                        "and the pass resumes from here."
                    ) from exc
                # And PROVE it: a delete that returns without raising is not
                # the same claim as a file that is gone. A locked or
                # read-only file, or any future path form this helper does
                # not cover, must fail loudly rather than let the registry
                # be treated as settled over records still sitting hot.
                if os.path.exists(target):
                    raise ArchiveError(
                        f"The hot record file for sequence {sequence} ({path.name}) is "
                        "still present after being removed - refusing to report a "
                        "rotation that did not happen. The cold segment and its "
                        "registry entry are already on disk, so nothing is lost; "
                        "re-run `godmode forget` once the file can actually be "
                        "removed and the pass resumes from here."
                    )
            self._drop_events_cache(rewrite=True)
        return {"rotated": targets, "segment": segment_name,
                "count": len(targets), "resumed": resumed}

    @staticmethod
    def _require_intact(record: dict[str, Any], sequence: int, location: str) -> None:
        """Refuse to serve a record whose stored `record_hash` no longer
        matches its own content. One hash of one
        record - the cheapest possible check on a path that already read the
        bytes, and the difference between "reachable" and "trustworthy"."""
        if record.get("record_hash") != _record_hash(record):
            raise ArchiveError(
                f"Record {sequence} in {location} no longer matches its own content "
                "hash - refusing to serve a rewritten record as genuine. Run "
                "`godmode doctor` for the full chain walk, which names the break "
                "and every record after it."
            )

    def find_by_sequence(self, sequence: int) -> dict[str, Any] | None:
        """The record with this sequence number, hot or cold. Hot
        is checked first - a filename-prefix match over one directory
        listing, no per-file parse - since that is the overwhelming common
        case; only a miss there consults the cold segments the registry
        names, in the order they were written. `None` when the sequence
        was never sealed at all.

        Whatever this returns has had its own
        content hash recomputed and compared against the `record_hash` it
        carries, and a cold hit additionally re-hashes the segment it came
        out of against the digest the cold registry recorded at rotation
        time. `history --seq` is the ONLY way to read a cold record, so
        reachable must not mean unverified; a record failing either check is
        refused by name (with `godmode doctor` as the remedy) rather than
        served as genuine with its own stale hash still attached.
        """
        sequence = int(sequence)
        prefix = f"{sequence:012d}-"
        try:
            names = os.listdir(self.events)
        except OSError:
            names = []
        for name in names:
            if name.startswith(prefix) and _is_record_name(name):
                try:
                    record = self._read_json(self.events / name)
                except ArchiveError:
                    continue
                self._require_intact(record, sequence, name)
                return record
        registry = self._read_cold_registry()
        for entry in (registry["segments"] if registry else []):
            name = entry.get("file") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                continue
            path = self.root / name
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or _sequence_of(record) != sequence:
                    continue
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest != entry.get("sha256"):
                    raise ArchiveError(
                        f"Record {sequence} lives in cold segment {name}, whose bytes no "
                        "longer match the digest recorded when it was rotated - refusing "
                        "to serve it. Run `godmode doctor`, which re-walks every cold "
                        "segment and names what changed."
                    )
                self._require_intact(record, sequence, name)
                return record
        return None

    @staticmethod
    def _cold_broken(message: str) -> dict[str, Any]:
        """`verify_cold()`'s own refusal shape - the same `ok`/`valid`/
        `message` keys `verify()` returns for a named break, so `doctor`'s
        `cold-segment-broken` finding reads one way whichever check fired."""
        return {"ok": False, "valid": False, "message": message}

    def verify_cold(self) -> dict[str, Any]:
        """The thorough cross-tier check.
        It walks the cold segments THEMSELVES and never takes
        the registry's word for what they hold. Before this, a sequence listed
        in `rotated` but present in no segment file at all read as an
        explained gap - two records could be deleted outright and both
        verifiers still said the chain was intact.

        Five checks, then the walk:

        1. every segment file the registry names is readable and still hashes
           to the sha256 recorded when it was rotated;
        2. every line in it parses, and the sequences the file actually holds
           are exactly the sequences its own registry entry claims;
        3. the sequences parsed out of ALL segments are exactly the registry's
           `rotated` set - a dropped `segments` entry, or a line deleted from
           a segment whose sha256 was then refreshed, is a break here;
        4. every cold record still matches its own content hash, and that hash
           still matches the `hash_by_sequence` entry recorded for it;
        5. a sequence present in BOTH tiers - the window `rotate_to_cold`
           leaves open between registering a segment and unlinking the hot
           files it copied - collapses when the two copies are identical, and
           is a break when they differ.

        Then the WHOLE chain (cold records in sequence order, then the hot
        tail) is walked from position 0 through `verify()`'s ordinary
        per-record checks with `bridge_gaps=False`, so any hole in the
        combined list is a broken chain rather than a gap the registry may
        explain, and the first hot record's `previous_hash` is checked
        against the last cold record's `record_hash` by the same walk that
        checks every other link. This is the one path that re-reads cold
        bytes; an ordinary read (`resume`, `status`, a plain `verify()`)
        never does, which is the whole performance point of a cold tier -
        see THREAT-MODEL.md's clause on this. `godmode doctor` calls this
        whenever a cold segment exists; nothing on the ordinary read path
        does.
        """
        registry = self._read_cold_registry()
        segments = registry["segments"] if registry else []
        rotated = frozenset(registry["rotated"]) if registry else frozenset()
        hash_by_sequence = registry["hash_by_sequence"] if registry else {}
        cold_records: list[dict[str, Any]] = []
        cold_paths: list[Path] = []
        for entry in segments:
            name = entry.get("file") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                return self._cold_broken("cold registry names a segment with no file")
            path = self.root / name
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                return self._cold_broken(f"cold segment unreadable: {name}")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest != entry.get("sha256"):
                return self._cold_broken(
                    f"cold segment tampered: {name} no longer matches the digest "
                    "recorded when it was rotated"
                )
            held: list[int] = []
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return self._cold_broken(
                        f"cold segment {name} line {line_number} is not valid JSON")
                if not isinstance(record, dict):
                    return self._cold_broken(
                        f"cold segment {name} line {line_number} is not a record object")
                cold_records.append(record)
                cold_paths.append(path)
                held.append(_sequence_of(record))
            claimed = entry.get("sequences")
            claimed_sequences = (
                sorted(int(s) for s in claimed if isinstance(s, int) and not isinstance(s, bool))
                if isinstance(claimed, list) else None
            )
            if claimed_sequences != sorted(held):
                return self._cold_broken(
                    f"cold segment {name} holds sequence(s) {sorted(held)}, but the cold "
                    f"registry records {claimed} for it"
                )
        parsed = sorted(_sequence_of(record) for record in cold_records)
        if parsed != sorted(rotated):
            unheld = sorted(rotated - set(parsed))
            unlisted = sorted(set(parsed) - rotated)
            return self._cold_broken(
                "the cold segments do not hold what the cold registry says they do: "
                f"rotated but in no segment {unheld}, in a segment but not rotated {unlisted}"
            )
        for record in cold_records:
            sequence = _sequence_of(record)
            if record.get("record_hash") != _record_hash(record):
                return self._cold_broken(
                    f"cold record {sequence} no longer matches its own content hash")
            if hash_by_sequence.get(sequence) != record.get("record_hash"):
                return self._cold_broken(
                    f"cold record {sequence} does not match the hash the cold registry "
                    "recorded for it when it was rotated"
                )
        hot_records = self.read_events(verify=False)
        hot_paths = self.event_paths()
        cold_by_sequence = {_sequence_of(record): record for record in cold_records}
        combined: list[tuple[dict[str, Any], Path | None]] = list(zip(cold_records, cold_paths))
        for index, record in enumerate(hot_records):
            sequence = _sequence_of(record)
            twin = cold_by_sequence.get(sequence)
            if twin is not None:
                # The rotation window (check 5 above): the same record in
                # both tiers is one record, not a duplicate sequence - as
                # long as the two copies really are the same bytes.
                if _canonical_json(twin) != _canonical_json(record):
                    return self._cold_broken(
                        f"sequence {sequence} is in both a cold segment and the hot tier, "
                        "and the two copies are not the same record"
                    )
                continue
            combined.append((record, hot_paths[index] if index < len(hot_paths) else None))
        combined.sort(key=lambda pair: _sequence_of(pair[0]))
        walked = [record for record, _ in combined]
        paths = [path for _, path in combined]

        def _path_at(position: int) -> Path | None:
            # `records` here is the combined list, so `event_paths()` alone
            # would name the wrong file for a break inside the cold portion.
            return paths[position] if 0 <= position < len(paths) else None

        return self.verify(walked, check_anchor=True, trusted_prefix=0,
                           use_checkpoint=False, bridge_gaps=False, path_at=_path_at)

    def latest(self, kind: str | None = None) -> dict[str, Any] | None:
        records = self.read_events()
        for record in reversed(records):
            if kind is None or record["kind"] == kind:
                return record
        return None

    def select(
        self, *, kind: str | None = None, subject: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        records = self.read_events()
        selected = [
            record
            for record in records
            if (kind is None or record["kind"] == kind)
            and (subject is None or record["subject"] == subject)
        ]
        return selected[-max(1, min(limit, 500)) :]
