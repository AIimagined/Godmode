"""Project mode (spec R1): enforce harm, advise on quality.

`strict` is today's behaviour, byte-identical - every quality-class Stop
gate still blocks. `advise` (the default) leaves the harm gates (the
pre-action path: tag/release/push checks) untouched, since Stop can never
prevent a harmful action in the first place, but turns every Stop-time
block/continue decision into a once-per-kind-per-session line of advice
instead of an enforced stop.

Stored at `<archive.root>/mode.json`, private and never tracked - the same
local-state convention every other per-project file under the archive root
already follows. Missing or unreadable reads as `advise`: a project that
never opted in gets the safer, non-enforcing default rather than silently
inheriting yesterday's strict behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MODES = ("advise", "strict")
_MODE_FILE = "mode.json"
_SHOWN_FILE = "godmode-advise-shown.json"


def project_mode(archive: Any) -> str:
    """`"advise"` or `"strict"`. Any read failure - missing file,
    unparseable JSON, an unrecognized value - reads as `"advise"`."""
    path = Path(archive.root) / _MODE_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        mode = payload.get("mode")
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable mode file is the safer, non-enforcing default
        return "advise"
    return mode if mode in _MODES else "advise"


def set_project_mode(archive: Any, mode: str) -> None:
    if mode not in _MODES:
        raise ValueError(f"unknown project mode: {mode!r} (expected 'advise' or 'strict')")
    root = Path(archive.root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / _MODE_FILE
    # LF only: write_text on Windows would translate \n to \r\n, and this
    # file is never meant to round-trip through a text editor.
    path.write_bytes(json.dumps({"mode": mode}).encode("utf-8"))


def advise_seen(archive: Any, session_id: str | None, kind: str) -> bool:
    """First call for a given `(session_id, kind)` pair returns True and
    records it as shown; every later call for the same pair returns False.
    Best-effort: a state file that cannot be read or written costs a
    session one repeated advisory, never a crash."""
    path = Path(archive.root) / _SHOWN_FILE
    key = str(session_id or "")
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable shown-state file starts empty, not fatal
        state = {}
    if not isinstance(state, dict):
        state = {}
    shown = state.get(key)
    if not isinstance(shown, list):
        shown = []
    if kind in shown:
        return False
    shown.append(kind)
    state[key] = shown
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(state, ensure_ascii=False).encode("utf-8"))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a write that fails costs one repeated advisory next time, not a crash
        pass
    return True
