"""NS-2 + NS-10j (0.3.28 Plan 5 Task 2): structured lessons that graduate
through approval.

A lesson's data schema names five fields: `root_cause`, `correction`,
`reflection`, `guard` (stored under the archive's own long-standing
`generalized_guard` key), `falsifier` (stored under `refuted_by`). NS-10j's
rule is deliberately permissive at write time - a lesson missing any of the
five is `status: candidate`, never refused (`normalize_lesson_write`, called
by `remember --kind lesson` only when the caller is authoring the structured
schema at all, i.e. gave at least one of `--root-cause`/`--correction`/
`--reflection`/`--falsifier`; a plain `--guard`-only lesson is the
pre-existing advisory shape and is untouched by this rule).

NS-10j's write-time rule STAYS opt-in, and fix round 1 (M1) is the reason
it can: with NS-2's compile gate in place
(`godmode_law.lesson_carries_authority`), an agent's guard never reaches
the law without an approval, and `promote` refuses to mint that approval
for a lesson missing any of the five fields - naming them. So the schema is
mandatory exactly where it decides something. Making it mandatory at WRITE
time as well would force `status: candidate` onto every `--guard`-only
enforce lesson, and `candidate` is in `LESSON_DORMANT_STATUSES`, which is
what `Chronicle._enforced_refusal` reads - it would silently switch off
Task 4's guards-that-execute for every lesson that predates this schema.
The two divergences the review found compounded only while B1 was open;
with B1 closed, this one is an ergonomic carve-out with a named cost.

Graduating a candidate into the compiled law is a SEPARATE act, and it is
where NS-2's refusal lives: `promote` refuses a lesson that is not fully
structured, naming exactly which fields it lacks - "never refused at
candidate stage" describes the WRITE, not the promotion. `approve` refuses
a promotion approved by its own promoter (actor compared by fingerprint,
never by role label - Task 5's `agent_id()`, the same identity
`godmode_bonds.py`'s proposer/checker separateness already compares by) or
re-cited with the promoter's own rerun_hash (the checker merely re-cited
the author's re-run instead of running its own). Once a promotion carries a
genuinely independent, genuinely different approval, `approve` is what
actually graduates the lesson: a fresh `lesson` append, same subject,
status `active`, carrying the `approval_seq` that
`godmode_law.lesson_carries_authority` reads - the newest-per-subject dedup
in `_guarded_lessons` compiles it from there.

The existing three-session correction/instruction ladder
(`godmode_law.promote_candidate`) now feeds this same pipeline instead of
writing an active lesson directly: it authors a (synthesized) structured
lesson, candidate at first, then calls `promote` here itself. Its own
proposer/approval separateness rule is unaffected by this - only a REVIEW,
never the ladder's own promotion, can approve.
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import agent_id
from .godmode_errors import ArchiveError

# Actor separateness cannot rest on `GODMODE_AGENT_ID` alone: any process
# may set it, so one process could promote and then approve under a renamed
# id. Both records therefore also carry the writing process's binding - its
# own pid, its ancestor chain, the first ancestor that is not a shell,
# launcher or interpreter (the program driving it: an agent host, a
# terminal), and the session it declared - and `approve` refuses when the
# two bindings share a process, a session, any ancestor below the system
# roots, or a driver. Read from the operating system, not from the
# environment, so renaming an id changes none of it.
_LINEAGE_DEPTH = 8
_PASS_THROUGH = frozenset({
    "bash", "sh", "zsh", "dash", "fish", "ksh", "tcsh", "csh", "busybox",
    "cmd", "conhost", "pwsh", "powershell", "wsl", "env", "sudo", "nohup",
    "timeout", "py", "pyw", "uv", "time", "xargs", "perl", "ruby", "node",
    "nodejs", "bun", "deno", "php", "git", "make", "gmake", "find", "awk",
    "gawk", "setsid", "nice", "stdbuf", "npx", "npm",
})
# Ancestors that processes of different actors routinely share: the system
# init, the desktop shell, and the terminal emulators, IDEs, multiplexers
# and remote-login daemons an operator opens a tab or pane in. An agent host
# and the operator's own tab of the same terminal or IDE both descend from
# it, so sharing one of these says nothing about who the actor is: the
# ancestor comparison skips them and none is taken as the driving program.
# Sharing any other ancestor - the agent host itself, or an interpreter it
# started - is one actor.
_SYSTEM_ROOTS = frozenset({
    "init", "systemd", "launchd", "kernel_task", "explorer", "wininit",
    "winlogon", "services", "svchost", "smss", "csrss", "userinit", "sihost",
    # Terminal emulators and console hosts.
    "windowsterminal", "wt", "openconsole", "conhost", "cmd", "powershell",
    "pwsh", "iterm2", "terminal", "gnome-terminal", "gnome-terminal-server",
    "gnome-terminal-", "konsole", "xterm", "alacritty", "kitty", "wezterm-gui",
    # IDEs whose integrated terminal hosts both.
    "code", "code - insiders", "code-insiders", "cursor",
    # Multiplexers and remote login.
    "tmux", "tmux: server", "screen", "sshd",
})


def _is_system_root(name: str) -> bool:
    return _base_name(name) in _SYSTEM_ROOTS


def _base_name(name: str) -> str:
    base = os.path.basename(str(name or "")).strip().lower()
    return base[:-4] if base.endswith(".exe") else base


def _passes_through(name: str) -> bool:
    base = _base_name(name)
    return base in _PASS_THROUGH or base.startswith("python")


def _windows_process_table() -> dict[int, tuple[int, str]]:
    """pid -> (parent pid, image name), from one Toolhelp snapshot."""
    import ctypes
    from ctypes import wintypes

    class _Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return {}
    table: dict[int, tuple[int, str]] = {}
    try:
        entry = _Entry()
        entry.dwSize = ctypes.sizeof(_Entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            table[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), str(entry.szExeFile))
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return table


def _proc_parent(pid: int) -> tuple[int, str] | None:
    """(parent pid, name) from /proc, where the platform has one."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2:].split()
    try:
        return int(fields[1]), name
    except (IndexError, ValueError):
        return None


def _process_lineage() -> list[dict[str, Any]]:
    """This process's ancestors, nearest first, as {pid, name}. Best
    effort: Windows reads a Toolhelp snapshot, Linux reads /proc, and any
    other platform records the parent pid alone, with no name."""
    lineage: list[dict[str, Any]] = []
    seen = {os.getpid()}
    try:
        if os.name == "nt":
            table = _windows_process_table()
            pid = table.get(os.getpid(), (0, ""))[0]
            while pid > 4 and pid not in seen and len(lineage) < _LINEAGE_DEPTH:
                seen.add(pid)
                parent, name = table.get(pid, (0, ""))
                if pid not in table:
                    break
                lineage.append({"pid": pid, "name": name})
                pid = parent
        elif Path("/proc/self/stat").exists():
            pid = os.getppid()
            while pid > 1 and pid not in seen and len(lineage) < _LINEAGE_DEPTH:
                seen.add(pid)
                found = _proc_parent(pid)
                if found is None:
                    break
                lineage.append({"pid": pid, "name": found[1]})
                pid = found[0]
        elif os.getppid() > 1:
            lineage.append({"pid": os.getppid(), "name": ""})
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a lineage that cannot be read binds by pid and session alone, and says so by being empty
        return lineage
    return lineage


def process_binding() -> dict[str, Any]:
    """The writing process as the operating system knows it - recorded on
    every promotion and approval, and compared by `approve`."""
    lineage = _process_lineage()
    driver = None
    if lineage and all(entry.get("name") for entry in lineage):
        driver = next((entry for entry in lineage
                       if not _passes_through(entry["name"])
                       and not _is_system_root(entry["name"])), None)
    return {
        "pid": os.getpid(),
        "platform": sys.platform,
        "lineage": lineage,
        "driver": driver,
        "session": os.environ.get("GODMODE_SESSION", "").strip(),
    }


def _same_process(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not left or not right:
        return False
    if int(left.get("pid", -1)) != int(right.get("pid", -2)):
        return False
    left_name, right_name = str(left.get("name") or ""), str(right.get("name") or "")
    return not (left_name and right_name and _base_name(left_name) != _base_name(right_name))


def shared_actor(promoter: dict[str, Any] | None, approver: dict[str, Any]) -> str | None:
    """Why two bindings are one actor, or None when nothing ties them."""
    if not isinstance(promoter, dict) or "pid" not in promoter:
        return ("the promotion carries no process binding, so nothing shows it "
                "came from a different process - re-mint the promotion")
    if int(promoter["pid"]) == int(approver["pid"]) and promoter.get("platform") == approver.get("platform"):
        return f"the same process (pid {approver['pid']})"
    if promoter.get("session") and promoter.get("session") == approver.get("session"):
        return f"the same session ({approver['session']})"
    promoter_lineage = list(promoter.get("lineage") or [])
    approver_lineage = list(approver.get("lineage") or [])
    if any(int(entry.get("pid", -1)) == int(approver["pid"]) for entry in promoter_lineage):
        return "the approving process started the promoting one"
    if any(int(entry.get("pid", -1)) == int(promoter["pid"]) for entry in approver_lineage):
        return "the promoting process started the approving one"
    if promoter_lineage and approver_lineage and _same_process(promoter_lineage[0], approver_lineage[0]):
        return f"the same parent process (pid {approver_lineage[0].get('pid')})"
    driver_name = str((approver.get("driver") or {}).get("name") or "")
    if (not _is_system_root(driver_name)
            and _same_process(promoter.get("driver"), approver.get("driver"))):
        driver = approver["driver"]
        return f"the same driving process ({driver.get('name')}, pid {driver.get('pid')})"
    for entry in approver_lineage:
        if _is_system_root(str(entry.get("name") or "")):
            continue
        if any(_same_process(entry, other) for other in promoter_lineage):
            return (f"a shared ancestor process ({entry.get('name') or 'unnamed'}, "
                    f"pid {entry.get('pid')})")
    return None

# NS-10j's five fields, in the archive's own canonical keys. `guard` and
# `falsifier` are NS-10j's names for the pre-existing `generalized_guard`/
# `refuted_by` keys - never a second, parallel pair of field names.
REQUIRED_LESSON_FIELDS: tuple[str, ...] = (
    "root_cause", "correction", "reflection", "generalized_guard", "refuted_by",
)
# canonical archive key -> NS-10j's own name, for refusal/report text an
# operator actually typed (`--falsifier`, never `refuted_by`).
_SPEC_NAMES: dict[str, str] = {
    "root_cause": "root_cause",
    "correction": "correction",
    "reflection": "reflection",
    "generalized_guard": "guard",
    "refuted_by": "falsifier",
}

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

# NS-2: the live candidate set is bounded on two axes - count and combined
# text - never unbounded (an unbounded candidate set is the named failure
# mode this guards against). `godmode_law.shelve_oldest_candidates`
# enforces both, and `law_candidates` honours the result.
MAX_CANDIDATES = 200
MAX_CANDIDATE_CHARS = 64_000


def missing_structured_fields(data: dict[str, Any]) -> list[str]:
    """Which of NS-10j's five fields `data` lacks (absent, blank, or
    non-string all count as missing), named the way the operator typed
    them (`guard`, `falsifier`), not the archive's own storage keys."""
    missing = []
    for field in REQUIRED_LESSON_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(_SPEC_NAMES[field])
    return missing


def normalize_lesson_write(data: dict[str, Any]) -> dict[str, Any]:
    """NS-10j: a lesson missing any structured field is `status: candidate`
    on write - never refused. Mutates and returns `data`. Overrides
    whatever `status` the caller asked for: an incomplete lesson claiming
    `active` status is exactly the silently-untrustworthy shape this rule
    exists to prevent, and promotion (below) is the only way past it."""
    if missing_structured_fields(data):
        data["status"] = "candidate"
    return data


def _validate_rerun_hash(rerun_hash: str, *, label: str = "--rerun-hash") -> str:
    text = str(rerun_hash or "").strip().lower()
    if not _SHA256_HEX.match(text):
        raise ArchiveError(
            f"{label} must be a sha256 hex digest (64 hex characters) - the "
            "independent re-run's own evidence fingerprint, not a label"
        )
    return text


def _record_by_seq(archive: Chronicle, kind: str, sequence: int) -> dict[str, Any] | None:
    # `read_events`, never `select` - `select` clamps to 500 (the same S5
    # fix `godmode_bonds._record_by_sequence` already documents), and an
    # older lesson/promotion would otherwise resolve as "not found".
    for record in archive.read_events(verify=False):
        if record.get("kind") == kind and int(record.get("sequence", 0)) == int(sequence):
            return record
    return None


def _newest_lesson_for_subject(archive: Chronicle, subject: str) -> dict[str, Any] | None:
    """The subject's CURRENT lesson record - highest sequence wins, exactly
    the fold `godmode_law._guarded_lessons` uses to decide which record IS
    the subject's state. Deliberately the same rule as the compiler's, not
    Task 6's supersession-aware `latest_by_subject`: what `approve` must
    not contradict is what the law compiler will actually read."""
    newest: dict[str, Any] | None = None
    for record in archive.read_events(verify=False):
        if record.get("kind") != "lesson":
            continue
        if str(record.get("subject", "")) != str(subject):
            continue
        if newest is None or int(record.get("sequence", 0)) > int(newest.get("sequence", 0)):
            newest = record
    return newest


_UNATTENDED_PINNED_REMEDY = (
    "run it from an attended session, or set GODMODE_ATTENDED=1 if one truly is one"
)


def guard_pinned_lesson(
    archive: Chronicle, *, attended_flag: bool, subject: str | None = None,
    sequence: int | None = None, new_data: dict[str, Any] | None = None,
    action: str = "edit",
) -> list[str]:
    """A pinned lesson - one whose current record is `standing`, the flag
    that pins it ahead of every other law in the brief - is stricter for an
    actor nobody is watching. Unattended, any write that would edit or
    remove it is refused. Attended, it proceeds and this returns the
    unified diff between the pinned record and what replaces it, for the
    caller to show; an empty list means the subject is not pinned.

    The lesson is named by `subject`, or by `sequence` (any record of the
    subject). Removal is never a delete here: retiring a lesson appends a
    record, and the pinned one stays in the archive, restorable by seq."""
    if subject is None and sequence is not None:
        named = _record_by_seq(archive, "lesson", int(sequence))
        if named is None:
            return []
        subject = str(named.get("subject", ""))
    if subject is None:
        return []
    current = _newest_lesson_for_subject(archive, subject)
    if current is None or not bool((current.get("data") or {}).get("standing")):
        return []
    if not attended_flag:
        raise ArchiveError(
            f"Refusing to {action} pinned lesson {subject[:60]!r} (seq "
            f"{current.get('sequence')}): a standing lesson is not edited or "
            "removed by an actor nobody is watching - "
            + _UNATTENDED_PINNED_REMEDY
        )
    before = json.dumps(current.get("data") or {}, indent=2, sort_keys=True,
                        ensure_ascii=False).splitlines()
    after = json.dumps(new_data or {}, indent=2, sort_keys=True,
                       ensure_ascii=False).splitlines() if new_data is not None else []
    return list(difflib.unified_diff(
        before, after, f"seq:{current.get('sequence')}", f"{action}", lineterm=""))


def _existing_approval(archive: Chronicle, promotion_seq: int) -> dict[str, Any] | None:
    """The first `lesson_approval` already standing against this promotion,
    if any - NS-2 fix round 1 (M2): a promotion is approved ONCE."""
    for record in archive.read_events(verify=False):
        if record.get("kind") != "lesson_approval":
            continue
        if int((record.get("data") or {}).get("promotion_seq", 0)) == int(promotion_seq):
            return record
    return None


def promote(
    archive: Chronicle, lesson_seq: int, cite: list[str], rerun_hash: str,
) -> dict[str, Any]:
    """`lessons promote <seq> --cite ... --rerun-hash <h>`: refused (naming
    the exact rule) when no lesson exists at that sequence, when it is
    missing any of NS-10j's five structured fields (named, never merely
    counted), when no citation is given, or when `--rerun-hash` is not a
    sha256 digest. Writes a `lesson_promotion`; actor is Task 5's own
    `agent_id()` - the CLI takes no actor override.

    Fix round 1 (nit 5): the lesson must still be a CANDIDATE. Promoting an
    already-active lesson granted nothing - `approve` would write a real
    `lesson_approval` and then graduate nothing, reporting
    `graduated_seq: None` - and promoting a retired one was an attempt to
    resurrect a guard its own subject had deliberately lifted. A promotion
    that cannot graduate anything is refused here, where the operator can
    still read why, rather than succeeding quietly and failing at approval.
    """
    lesson = _record_by_seq(archive, "lesson", lesson_seq)
    if lesson is None:
        raise ArchiveError(f"No lesson record at sequence {lesson_seq}")
    status = str((lesson.get("data") or {}).get("status", "active")).strip().lower()
    if status != "candidate":
        raise ArchiveError(
            f"Refusing to promote lesson {lesson_seq}: its status is "
            f"{status!r}, not 'candidate' - promotion is what graduates a "
            "candidate into the law, and it has nothing to grant a lesson "
            "that is already active, or that was deliberately retired"
        )
    # B2, at the near end: a promotion is written against the subject's
    # CURRENT record or it is stale at birth. `approve` checks this again at
    # the far end, because the subject can move in between - but refusing
    # here is what lets the operator read why while they are still the one
    # acting.
    subject = str(lesson.get("subject", ""))
    newest = _newest_lesson_for_subject(archive, subject)
    newest_seq = int((newest or {}).get("sequence", 0))
    if newest_seq != lesson_seq:
        newest_status = str(
            ((newest or {}).get("data") or {}).get("status", "active")).strip().lower()
        raise ArchiveError(
            f"Refusing to promote lesson {lesson_seq}: the newest record for "
            f"{subject!r} is seq {newest_seq} (status {newest_status!r}), so "
            f"{lesson_seq} is no longer what this subject says - promote the "
            "current record, or record a fresh candidate"
        )
    missing = missing_structured_fields(lesson.get("data") or {})
    if missing:
        raise ArchiveError(
            f"Refusing to promote lesson {lesson_seq}: missing structured "
            f"field(s) {', '.join(missing)} - a lesson graduates only once "
            "it names its own root_cause, correction, reflection, guard and "
            "falsifier"
        )
    cite_list = [str(c) for c in (cite or []) if str(c).strip()]
    if not cite_list:
        raise ArchiveError(
            "`lessons promote` needs at least one --cite; an unevidenced "
            "promotion is a request, not a claim"
        )
    digest = _validate_rerun_hash(rerun_hash)
    actor = agent_id()
    record = archive.append(
        "lesson_promotion",
        f"promotion:{lesson['subject']}",
        {
            "lesson_seq": int(lesson_seq), "actor": actor,
            "evidence": cite_list, "rerun_hash": digest,
            "binding": process_binding(),
        },
        evidence=cite_list + [f"seq:{lesson_seq}"],
    )
    return {
        "sequence": record["sequence"], "lesson_seq": int(lesson_seq),
        "actor": actor, "evidence": cite_list, "rerun_hash": digest,
    }


def approve(archive: Chronicle, promotion_seq: int, rerun_hash: str) -> dict[str, Any]:
    """`lessons approve <promotion-seq> --rerun-hash <h>`: refused (naming
    the exact rule) when no promotion exists at that sequence, when
    `--rerun-hash` is not a sha256 digest, when the approver is the same
    actor as the promoter (compared by Task 5's fingerprint, never by role
    label), or when the rerun hash equals the promotion's own (the checker
    merely re-cited the author's re-run). On success, this IS the
    graduation: a fresh `lesson` append, same subject, `status: active`,
    carrying the `approval_seq` that `godmode_law.lesson_carries_authority`
    reads - the newest-per-subject dedup in `_guarded_lessons` compiles it
    from there.

    Fix round 1 (M2): a promotion is approved ONCE. A second approval is
    refused by name, citing the first. Without this, one promotion minted
    as many active `lesson` records on one subject as it was approved
    times - the exact duplicate-active shape `_guarded_lessons`'s own
    2026-08-29 dedup comment records as a bug already fixed once, and the
    shape `godmode forget`'s contradiction pass exists to flag.

    Fix round 1 (B2): an approval graduates the subject's CURRENT state,
    never a sequence pinned when the promotion was written. If the newest
    `lesson` record for the subject is no longer the promoted one, the
    promotion is STALE and is refused, naming what changed. Retirement is
    the archive's own documented way to lift a bad guard
    (`Chronicle._enforced_refusal`); before this, a promotion minted BEFORE
    a retirement could be approved after it by a third party and put the
    retired guard back into the compiled law with no refusal anywhere.
    """
    promotion = _record_by_seq(archive, "lesson_promotion", promotion_seq)
    if promotion is None:
        raise ArchiveError(f"No lesson_promotion record at sequence {promotion_seq}")
    promotion_data = promotion.get("data") or {}
    prior = _existing_approval(archive, promotion_seq)
    if prior is not None:
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: it was already "
            f"approved at seq {prior['sequence']} by "
            f"{(prior.get('data') or {}).get('actor')} - a promotion is "
            "approved once; re-affirming a standing law means a fresh "
            "promotion against its current record, not a second approval of "
            "the same one"
        )
    digest = _validate_rerun_hash(rerun_hash)
    actor = agent_id()
    promoter = promotion_data.get("actor")
    if actor == promoter:
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: the approver "
            f"and the promoter are the same actor ({actor}), compared by "
            "fingerprint, not by role label - a promotion cannot approve "
            "itself"
        )
    # The id above is only a declaration; the binding is what the operating
    # system says about who is writing, and a renamed id changes none of it.
    binding = process_binding()
    shared = shared_actor(promotion_data.get("binding"), binding)
    if shared is not None:
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: the approver and "
            f"the promoter resolve to {shared}, whatever agent ids they "
            "declare - approve from a separate agent process or terminal"
        )
    if digest == promotion_data.get("rerun_hash"):
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: --rerun-hash "
            "equals the promotion's own rerun_hash - the checker merely "
            "re-cited the author's re-run instead of running its own"
        )
    lesson_seq = int(promotion_data.get("lesson_seq", 0))
    lesson = _record_by_seq(archive, "lesson", lesson_seq)
    if lesson is None:
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: it names lesson "
            f"{lesson_seq}, which the archive does not hold"
        )
    # B2, checked BEFORE the approval record is written: an approval that
    # cannot graduate anything must leave no `lesson_approval` behind
    # claiming it did.
    subject = str(lesson.get("subject", ""))
    newest = _newest_lesson_for_subject(archive, subject)
    newest_seq = int((newest or {}).get("sequence", 0))
    if newest_seq != lesson_seq:
        newest_status = str(
            ((newest or {}).get("data") or {}).get("status", "active")).strip().lower()
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: it was written "
            f"against lesson {lesson_seq}, but the newest record for "
            f"{subject!r} is now seq {newest_seq} (status {newest_status!r}) "
            "- the promotion is stale and describes a state the subject has "
            "left. Re-mint it against the current record; a retirement in "
            "particular is the documented way to lift a guard and an "
            "approval may not silently undo one"
        )
    status = str((lesson.get("data") or {}).get("status", "active")).strip().lower()
    if status != "candidate":
        raise ArchiveError(
            f"Refusing to approve promotion {promotion_seq}: lesson "
            f"{lesson_seq} is {status!r}, not 'candidate' - approval is what "
            "graduates a candidate, and there is nothing here for it to "
            "graduate"
        )
    record = archive.append(
        "lesson_approval",
        f"approval:{promotion_seq}",
        {"promotion_seq": int(promotion_seq), "actor": actor, "rerun_hash": digest,
         "binding": binding},
        evidence=[f"seq:{promotion_seq}", f"seq:{lesson_seq}"],
    )
    graduated = archive.append(
        "lesson", subject,
        {
            **(lesson.get("data") or {}),
            "status": "active",
            "graduated_from": lesson_seq,
            "promotion_seq": int(promotion_seq),
            "approval_seq": record["sequence"],
        },
        evidence=[f"seq:{promotion_seq}", f"seq:{record['sequence']}"],
    )
    return {
        "sequence": record["sequence"], "promotion_seq": int(promotion_seq),
        "lesson_seq": lesson_seq, "actor": actor, "rerun_hash": digest,
        "graduated_seq": graduated["sequence"],
    }
