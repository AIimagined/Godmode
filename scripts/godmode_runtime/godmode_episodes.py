"""Iteration episodes: the progress contract, computed from the host
transcript (PRD P-1, P-3, P-4; research brief Slice B and Slice D).

An episode is a run of failed command results that share one normalised
error signature, where the edits between runs overlap the same hunks, no
new file joined the set, and no new failing assertion appeared. Its length
is the loop count; the last turn that brought new information (a changed
signature, a new file, a new assertion) is where the loop began. Nothing
here calls a model; every field is a count or a position in the log.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_FAIL = re.compile(r"(?im)\bexit(?:ed)?(?: code)?\s+[1-9]\d*\b|^Traceback|\bFAILED\b|\bError\b:|\bfatal:|"
                   r"\bAssertionError\b|\bpanic:|\bnpm ERR!|\bError:|\bERROR\b|\bfailed\b")
_ASSERTION_LINE = re.compile(r"(?im)^(?:E\s+)?(?:assert|AssertionError|expected|expect\(|✕|✗|FAIL\s)[^\n]{0,160}")
_NOISE = re.compile(r"0x[0-9a-fA-F]+|\d+(?:\.\d+)?|[A-Za-z]:\\[^\s'\"]+|/[^\s'\":]+|\b[0-9a-f]{7,}\b")
THRESHOLDS = {"novice": 4, "standard": 6, "strict": 8}


def error_signature(text: str) -> str:
    """A stable hash of the failure's shape: the last error-bearing lines
    with numbers, paths and hashes normalised away."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    keep = [l for l in lines if _FAIL.search(l) or "Error" in l or "assert" in l.lower()]
    tail = (keep or lines)[-6:]
    normalised = " | ".join(_NOISE.sub("#", l) for l in tail)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12]


def _assertions(text: str) -> set[str]:
    return {_NOISE.sub("#", m.group(0)).strip()[:120] for m in _ASSERTION_LINE.finditer(text or "")}


def _hunk(part: dict[str, Any]) -> tuple[str, str] | None:
    data = part.get("input") or {}
    path = str(data.get("file_path", "")).replace("\\", "/").lower()
    if not path:
        return None
    anchor = str(data.get("old_string") or data.get("content") or "")[:80]
    return path, anchor


def loop_episodes(transcript_path: str | Path | None, threshold: int = 6) -> dict[str, Any]:
    """Every iteration episode in the transcript, longest first, plus the
    turn index where new information last arrived."""
    out: dict[str, Any] = {"episodes": [], "loop_detected": [], "turns": 0,
                           "last_new_information_turn": None, "threshold": threshold}
    if not transcript_path:
        return out
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    pending: dict[str, str] = {}
    turn = 0
    edits_since: list[tuple[str, str]] = []
    new_files_since: set[str] = set()
    current: dict[str, Any] | None = None
    episodes: list[dict[str, Any]] = []
    last_new = None

    def close() -> None:
        nonlocal current
        if current and current["attempts"] >= 2:
            episodes.append(current)
        current = None

    for line in lines[-12000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user" and isinstance(content, str):
            turn += 1
            continue
        if entry.get("type") == "assistant" and isinstance(content, list):
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                name = part.get("name")
                if name in ("Edit", "MultiEdit", "NotebookEdit"):
                    hunk = _hunk(part)
                    if hunk:
                        edits_since.append(hunk)
                elif name == "Write":
                    hunk = _hunk(part)
                    if hunk:
                        new_files_since.add(hunk[0])
                elif name in ("Bash", "PowerShell"):
                    pending[str(part.get("id"))] = str((part.get("input") or {}).get("command", ""))
            continue
        if entry.get("type") != "user" or not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "tool_result":
                continue
            command = pending.pop(str(part.get("tool_use_id")), None)
            if command is None:
                continue
            body = part.get("content")
            if isinstance(body, list):
                body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
            text = str(body or "")
            failed = bool(part.get("is_error")) or bool(_FAIL.search(text))
            if not failed:
                last_new = turn
                close()
                edits_since, new_files_since = [], set()
                continue
            signature = error_signature(text)
            assertions = _assertions(text)
            files = {p for p, _ in edits_since}
            same = (current is not None and current["signature"] == signature
                    and not new_files_since
                    and not (assertions - current["assertions"])
                    and (not files or files & current["files"] or not current["files"]))
            if same and current is not None:
                current["attempts"] += 1
                current["last_turn"] = turn
                current["files"] |= files
                current["hunks"] += len(edits_since)
            else:
                close()
                last_new = turn
                current = {"signature": signature, "attempts": 1, "first_turn": turn, "last_turn": turn,
                           "files": set(files), "assertions": set(assertions), "hunks": len(edits_since),
                           "command": " ".join(command.split())[:120]}
            edits_since, new_files_since = [], set()
    close()
    for episode in episodes:
        episode["files"] = sorted(episode["files"])
        episode["assertions"] = len(episode["assertions"])
    episodes.sort(key=lambda e: -e["attempts"])
    out["episodes"] = episodes
    out["loop_detected"] = [e for e in episodes if e["attempts"] >= threshold]
    out["turns"] = turn
    out["last_new_information_turn"] = last_new
    return out


def backtrack_context(archive: Any, episode: dict[str, Any]) -> dict[str, Any]:
    """P-3: the last checkpoint on the record and what the loop rejected -
    files and the error class. Names, never reverts."""
    checkpoints = archive.select(kind="checkpoint", limit=50)
    last = checkpoints[-1] if checkpoints else None
    return {
        "last_checkpoint": {"sequence": last.get("sequence"), "subject": last.get("subject"),
                            "head": (last.get("data") or {}).get("head")} if last else None,
        "rejected_premise": {"files": episode.get("files", []), "error_signature": episode.get("signature"),
                             "attempts": episode.get("attempts"), "command": episode.get("command")},
        "next": ("record the premise as failed (`godmode checkpoint --status failed --hypothesis \"<the premise>\"`), "
                 "then re-read the failing artifact before the next edit"),
    }


def reobserve_needed(transcript_path: str | Path | None, k: int = 8) -> dict[str, Any] | None:
    """P-4 / Slice D, observe-first: after `k` edits with no Read of any
    file named in the current failure, or after the error class changed
    since the last Read, the diagnosis is stale. Returns the data or None."""
    if not transcript_path:
        return None
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    edits_since_read = 0
    last_signature: str | None = None
    signature_at_last_read: str | None = None
    pending: dict[str, bool] = {}
    for line in lines[-8000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                name = part.get("name")
                if name == "Read":
                    edits_since_read = 0
                    signature_at_last_read = last_signature
                elif name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                    edits_since_read += 1
                elif name in ("Bash", "PowerShell"):
                    pending[str(part.get("id"))] = True
            elif part.get("type") == "tool_result" and pending.pop(str(part.get("tool_use_id")), False):
                body = part.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                text = str(body or "")
                if part.get("is_error") or _FAIL.search(text):
                    last_signature = error_signature(text)
    changed = bool(last_signature and signature_at_last_read and last_signature != signature_at_last_read)
    if edits_since_read >= k or changed:
        return {"edits_since_read": edits_since_read, "error_class_changed": changed,
                "detail": (f"{edits_since_read} edit(s) since the last Read"
                           + (" and the error class changed since that read" if changed else "")
                           + " - the diagnosis is older than the tree; re-read the failing artifact before the next edit")}
    return None
