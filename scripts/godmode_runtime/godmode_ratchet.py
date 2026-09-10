"""Project ratchets (2026-09-10, field report file Part 4, 4.8): the
repository's own debt counters - a lint-debt total, a memoization-bailout
count, a bundle size - declared in `.godmode-ratchets.json` as
`{"<name>": "<command>"}`. `run` executes each, reads the first integer
on its last non-empty stdout line, records it, and names every counter
that rose since its last record. Integrity's `project-ratchet` monitor
reads those records. Godmode owns no counter; it remembers the project's.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

RATCHETS_FILENAME = ".godmode-ratchets.json"
_INTEGER = re.compile(r"-?\d+")


def declared_ratchets(project: Path) -> dict[str, str]:
    path = Path(project) / RATCHETS_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}


def last_values(archive: Any) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in archive.select(kind="ratchet", limit=500):
        data = record.get("data") or {}
        latest[str(data.get("name") or record.get("subject") or "")] = {
            "value": data.get("value"), "sequence": record.get("sequence")}
    return latest


def _measure(project: Path, command: str, timeout: int) -> tuple[int | None, str]:
    try:
        # The command is the project's own declaration (like an npm script),
        # run through the shell so Windows paths and quoting survive.
        done = subprocess.run(command, shell=True, cwd=str(project), capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, f"{exc.__class__.__name__}: {exc}"[:120]
    lines = [line for line in (done.stdout or "").splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    match = _INTEGER.search(tail)
    if not match:
        return None, f"no integer on the last stdout line (exit {done.returncode})"
    return int(match.group(0)), f"exit {done.returncode}"


def run_ratchets(archive: Any, project: Path, timeout: int = 600) -> dict[str, Any]:
    declared = declared_ratchets(project)
    previous = last_values(archive)
    rows: list[dict[str, Any]] = []
    for name, command in declared.items():
        value, detail = _measure(project, command, timeout)
        before = (previous.get(name) or {}).get("value")
        row: dict[str, Any] = {"name": name, "value": value, "previous": before, "detail": detail}
        if value is not None:
            row["delta"] = None if before is None else value - before
            row["rose"] = before is not None and value > before
            archive.append("ratchet", name, {"name": name, "value": value, "previous": before,
                                             "digest": __import__("hashlib").sha256(command.encode("utf-8")).hexdigest()[:12]},
                           evidence=[])
        rows.append(row)
    rose = [r["name"] for r in rows if r.get("rose")]
    return {"declared": len(declared), "measured": sum(1 for r in rows if r["value"] is not None),
            "rows": rows, "rose": rose, "ok": not rose}


def ratchet_findings(archive: Any) -> list[dict[str, Any]]:
    """The last two records per counter; a rise is a finding."""
    history: dict[str, list[tuple[int, int]]] = {}
    for record in archive.select(kind="ratchet", limit=500):
        data = record.get("data") or {}
        try:
            history.setdefault(str(data.get("name") or ""), []).append(
                (int(record.get("sequence", 0)), int(data.get("value"))))
        except (TypeError, ValueError):
            continue
    out: list[dict[str, Any]] = []
    for name, runs in history.items():
        runs.sort()
        if len(runs) >= 2 and runs[-1][1] > runs[-2][1]:
            out.append({"name": name, "before": runs[-2][1], "after": runs[-1][1],
                        "detail": f"project ratchet {name} rose from {runs[-2][1]} to {runs[-1][1]} "
                                  f"(seq {runs[-2][0]} -> {runs[-1][0]})"})
    return out
