"""C-55: a watchdog over the agent's own record, on demand.

No daemon. Godmode is invoked, never resident, and the privacy boundary
forbids a watcher; "during a run" means between steps, and the report says
so in its `note`. The watchdog reads the newest window of the archive and
names three anomaly shapes, each one a failure that has actually been
observed in agent runs:

- `repeated-operation`: the same operation attempted N times in a row -
  the loop an agent falls into when a step keeps failing the same way.
- `refusal-burst`: several refusals close together - the agent is probing
  the gate rather than doing the work.
- `unattested-run`: a run of actions with no attestation behind any of
  them - work that is not being verified as it goes.

`interrupt` writes the operator-stop flag the stop algebra
(`godmode_stop.OperatorStop`) already honours, so an anomaly halts the
next guarded step with no new mechanism. Operations are reported by
digest prefix, not by text: the archive already holds the text, and the
report should not be a second copy of it.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from .godmode_constants import BOOKKEEPING_SUBJECTS, RUN_INERT_SUBJECTS
from .godmode_guardrails import OPERATOR_STOP_FLAG

WINDOW = 50
REPEAT_THRESHOLD = 3
REFUSAL_THRESHOLD = 3
REFUSAL_SPAN = 10
UNATTESTED_THRESHOLD = 5

NOTE = ("on demand, read between steps - godmode runs no daemon; invoke "
        "this before the next guarded step, or pass --interrupt to halt it")

# 2026-09-25: a scratch Python child spawned during preflight ran to 8.9 GB
# before anything noticed. No stdlib API returns a running child's RSS
# directly (`resource.getrusage` only sees a reaped child), so this polls
# the OS's own per-process memory view instead: /proc on POSIX,
# GetProcessMemoryInfo via ctypes on Windows - no psutil, no daemon, the
# poll thread lives only as long as the one call that started it.
DEFAULT_CHILD_MEMORY_LIMIT_MB = 4096
MEMORY_POLL_SECONDS = 2.0


def child_memory_limit_bytes() -> int:
    """The cap `run_with_memory_cap` uses when the caller passes none - a
    fixed default, overridable per host via `GODMODE_CHILD_MEMORY_LIMIT_MB`
    (0 disables the cap)."""
    raw = os.environ.get("GODMODE_CHILD_MEMORY_LIMIT_MB")
    if raw is None:
        return DEFAULT_CHILD_MEMORY_LIMIT_MB * 1024 * 1024
    try:
        mb = int(raw)
    except ValueError:
        return DEFAULT_CHILD_MEMORY_LIMIT_MB * 1024 * 1024
    return max(mb, 0) * 1024 * 1024


def child_rss_bytes(pid: int) -> int | None:
    """The current resident-set size of `pid`, in bytes; None when it can't
    be read (the process already exited, no permission, or an unsupported
    platform) - never raises, so a failed read only means "no sample"."""
    if os.name == "nt":
        return _child_rss_bytes_windows(pid)
    return _child_rss_bytes_posix(pid)


def _child_rss_bytes_posix(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024  # kB -> bytes
    except (OSError, ValueError, IndexError):
        return None
    return None


def _child_rss_bytes_windows(pid: int) -> int | None:
    try:
        import ctypes
        from ctypes import wintypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        psapi = ctypes.windll.psapi  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
            ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            if not ok:
                return None
            return int(counters.WorkingSetSize)
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return None


def run_with_memory_cap(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
    check: bool = False,
    memory_limit_bytes: int | None = None,
    poll_seconds: float = MEMORY_POLL_SECONDS,
) -> subprocess.CompletedProcess:
    """`subprocess.run`, with the child's peak RSS polled and the child
    killed the moment it crosses `memory_limit_bytes` (defaults to
    `child_memory_limit_bytes()`; pass 0 to disable the cap - report-only).

    The returned `CompletedProcess` carries two extra attributes:
    `peak_rss_bytes` (best sample seen, 0 if the platform never yielded
    one) and `memory_killed` (True when the cap fired). A timeout still
    raises `subprocess.TimeoutExpired` exactly as `subprocess.run` does;
    that exception also carries `peak_rss_bytes` for the same reporting.
    """
    if memory_limit_bytes is None:
        memory_limit_bytes = child_memory_limit_bytes()
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )
    state: dict[str, Any] = {"peak": 0, "memory_killed": False}
    stop = threading.Event()

    def _poll() -> None:
        while not stop.wait(poll_seconds):
            rss = child_rss_bytes(proc.pid)
            if rss is None:
                continue
            if rss > state["peak"]:
                state["peak"] = rss
            if memory_limit_bytes and rss > memory_limit_bytes:
                state["memory_killed"] = True
                try:
                    proc.kill()
                except OSError:
                    # The child exited on its own between the sample and
                    # the kill: it was not stopped for memory.
                    state["memory_killed"] = proc.poll() is None
                return

    monitor = threading.Thread(target=_poll, daemon=True)
    monitor.start()
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        stop.set()
        monitor.join(timeout=poll_seconds + 1)
        expired = subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
        expired.peak_rss_bytes = state["peak"]  # type: ignore[attr-defined]
        raise expired
    stop.set()
    monitor.join(timeout=poll_seconds + 1)
    result = subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
    result.peak_rss_bytes = state["peak"]  # type: ignore[attr-defined]
    result.memory_killed = state["memory_killed"]  # type: ignore[attr-defined]
    if result.memory_killed and result.returncode == 0:
        result.returncode = -9
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, argv, stdout, stderr)
    return result


def _operation_digest(record: dict[str, Any]) -> str:
    data = record.get("data") or {}
    text = str(data.get("operation") or data.get("command") or record.get("subject") or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else ""


def watchdog_report(archive: Any, *, window: int = WINDOW) -> dict[str, Any]:
    records = archive.read_events(verify=False)[-window:] if archive.initialized() else []
    anomalies: list[dict[str, Any]] = []

    run, previous = 0, ""
    for record in records:
        if record.get("kind") not in ("action", "refusal"):
            continue
        # Task 7 review (fix round 1, C1; fix round 2, N1): a bookkeeping
        # record about a read (`untrusted-content-seen`, `flaky-retry`,
        # `usage-observed` - `RUN_INERT_SUBJECTS`) is not an attempt at a
        # step - three fetches of the same instruction-shaped page must
        # not manufacture a `repeated-operation` anomaly about the agent.
        # `edit-recorded` is deliberately NOT in this skip, unlike the
        # `unattested-run` counter below: round 1 skipped the whole of
        # `BOOKKEEPING_SUBJECTS` here, which also skipped `edit-recorded`
        # and cost this counter its only way to see that an edit happened
        # between two otherwise-identical command runs - an ordinary
        # edit-then-rerun cycle started reading as one unbroken repeated
        # run. Letting `edit-recorded` fall through to the ordinary digest
        # check below restores that: its own (distinct-per-path) operation
        # digest differs from whatever command ran before it, so `run`
        # resets to 1 exactly as it did before round 1's fix.
        if record.get("kind") == "action" and record.get("subject") in RUN_INERT_SUBJECTS:
            continue
        digest = _operation_digest(record)
        run = run + 1 if digest and digest == previous else 1
        previous = digest
        if run == REPEAT_THRESHOLD:
            anomalies.append({
                "kind": "repeated-operation",
                "operation": digest,
                "sequence": record.get("sequence"),
                "detail": f"the same operation attempted {REPEAT_THRESHOLD} times in a row",
            })

    recent = records[-REFUSAL_SPAN:]
    refusals = [r for r in recent if r.get("kind") == "refusal"]
    if len(refusals) >= REFUSAL_THRESHOLD:
        anomalies.append({
            "kind": "refusal-burst",
            "count": len(refusals),
            "sequence": refusals[-1].get("sequence"),
            "detail": f"{len(refusals)} refusals in the last {len(recent)} records",
        })

    since_attestation = 0
    for record in records:
        if record.get("kind") == "attestation":
            since_attestation = 0
        # Fix round 2 (Task 8 review, B3): `edit-recorded` is bookkeeping
        # about an edit, never a run that wants attesting on its own - the
        # edit it describes is the thing that would be attested, not a
        # step this counter should treat as one more unverified action.
        # Task 7 (NS-8f): `BOOKKEEPING_SUBJECTS` also excludes
        # `untrusted-content-seen` for the same reason - the read it
        # describes is the thing an attestation could speak to, not one
        # more unverified action of its own.
        elif record.get("kind") == "action" and record.get("subject") not in BOOKKEEPING_SUBJECTS:
            since_attestation += 1
    if since_attestation >= UNATTESTED_THRESHOLD:
        anomalies.append({
            "kind": "unattested-run",
            "count": since_attestation,
            "detail": f"{since_attestation} actions since the last attestation",
        })

    return {
        "window": len(records),
        "anomalies": anomalies,
        "verdict": "anomaly" if anomalies else "clean",
        "note": NOTE,
    }


def interrupt(project: Path | str, reason: str) -> Path:
    """Write the operator-stop flag. Presence is the signal the stop
    algebra reads; the content is diagnostic only."""
    flag = Path(project) / OPERATOR_STOP_FLAG
    flag.write_text(f"watchdog: {reason}\n", encoding="utf-8")
    return flag
