"""An approval nobody answered for thirty minutes is a stall, not a wait.

Two overnight stalls cost the 0.3.31 release about ten hours: the hook
asked, the operator was away, and the agent sat on the ask. The hook
cannot see the wait (the agent is blocked until the host answers), so it
starts one detached watcher per ask. After the delay the watcher looks at
the archive: any record newer than the ask means the session moved on;
none means it is still waiting, and the watcher records the stall once
and shows one notification naming what waits. The ask itself already
told the agent to continue on files the call does not touch.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

STALL_SECONDS = 30 * 60
SUBJECT = "approval-stall"
_SCRIPTS = Path(__file__).resolve().parents[1]
_RUN = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
        "from godmode_runtime.godmode_stallwatch import main;raise SystemExit(main(sys.argv[1:]))")


def answered(archive: Any, ask_sequence: int) -> bool:
    """Whether anything was recorded after the ask: the session moved on."""
    return any(int(record.get("sequence", 0)) > ask_sequence
               for record in archive.read_events(verify=False))


def record_stall(archive: Any, ask_sequence: int, waited_seconds: int,
                 what: str) -> dict[str, Any] | None:
    """One `approval-stall` action per ask; None when it is already there."""
    for record in archive.select(kind="action", subject=SUBJECT, limit=100):
        if int((record.get("data") or {}).get("ask_sequence", -1)) == ask_sequence:
            return None
    return archive.append("action", SUBJECT, {
        "ask_sequence": int(ask_sequence),
        "waited_seconds": int(waited_seconds),
        "what": what[:200],
    }, evidence=[])


def notify_argv(text: str, platform: str | None = None,
                exists: Callable[[str], bool] = os.path.exists) -> list[str] | None:
    """The one command that shows `text` on this machine, or None. The
    text travels as an argument or an environment value, never inside a
    script string."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[void][System.Windows.Forms.MessageBox]::Show($env:GODMODE_NOTE, 'Godmode')"]
    if platform == "darwin":
        if exists("/usr/bin/osascript"):
            return ["/usr/bin/osascript", "-e", "on run argv",
                    "-e", 'display notification (item 1 of argv) with title "Godmode"',
                    "-e", "end run", text]
        return None
    if exists("/usr/bin/notify-send"):
        return ["/usr/bin/notify-send", "Godmode", text]
    return None


def notify(text: str, run: Callable[..., Any] = subprocess.run,
           platform: str | None = None) -> bool:
    argv = notify_argv(text, platform)
    if argv is None:
        return False
    try:
        run(argv, env={**os.environ, "GODMODE_NOTE": text}, timeout=4 * 3600,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:  # noqa: BLE001 - a notification that cannot be shown is not an error worth raising
        return False


def watch(project: str, ask_sequence: int, what: str,
          wait_seconds: int = STALL_SECONDS, sleep: Callable[[float], None] = time.sleep,
          notifier: Callable[[str], bool] = notify) -> str:
    """`answered` or `stalled`, after waiting."""
    sleep(wait_seconds)
    from .godmode_anchor import resolve_anchor
    from .godmode_chronicle import Chronicle
    archive = Chronicle(resolve_anchor(project))
    if answered(archive, ask_sequence):
        return "answered"
    if record_stall(archive, ask_sequence, wait_seconds, what) is not None:
        notifier(f"Godmode: an approval has waited {wait_seconds // 60} minutes: {what[:120]}. "
                 "The agent was told to continue on other files; answer it when you are back.")
    return "stalled"


def spawn_watch(project: str, ask_sequence: int, what: str,
                popen: Callable[..., Any] = subprocess.Popen) -> bool:
    """Start the detached watcher; best effort, never raises."""
    argv = [sys.executable, "-I", "-c", _RUN, str(_SCRIPTS), project, str(ask_sequence), what]
    detached: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        detached["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        detached["start_new_session"] = True
    try:
        popen(argv, **detached)
        return True
    except Exception:  # noqa: BLE001 - the ask stands with or without its watcher
        return False


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 2
    print(watch(argv[0], int(argv[1]), " ".join(argv[2:])))
    return 0
