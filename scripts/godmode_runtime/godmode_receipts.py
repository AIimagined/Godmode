"""I-2: read receipts for research depth.

A sweep's depth used to be unmeasured - "read" meant README seven times in
one day, and nothing distinguished that from a source file actually opened.
`godmode read` records what was opened: the path, the line range if one was
given, and a digest of exactly that slice. An absorb decision that says
adopt or extend can then cite `receipt:<source>:<path>` the same way it
cites `file:<path>` - and `godmode_absorb.validate_absorb` refuses a decision
whose only receipts are surface (README, docs, changelog, release notes).

A `--root` is the operator's own explicit claim of where an external source
lives; a path outside the project is accepted only when it resolves inside
that named root (`godmode_paths.contain`, the one containment rule every
other path Godmode resolves from an operator input goes through). Without
`--root`, the path must resolve inside the project itself.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .godmode_absorb import _SURFACE
from .godmode_errors import ArchiveError
from .godmode_paths import contain


def _normalise_path(path: str) -> str:
    cleaned = str(path).replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def record_receipt(
    archive: Any,
    project_root: str | Path,
    source: str,
    path: str,
    *,
    lines: tuple[int, int] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Record a `receipt` event: what was actually opened.

    Refuses a path that does not resolve inside `root` (when given) or
    inside `project_root` (when it is not) - the same containment every
    other path Godmode resolves from an operator input goes through.
    """
    roots = [Path(root)] if root is not None else [Path(project_root)]
    resolved = contain(path, roots)
    if resolved is None:
        where = f"--root {root}" if root is not None else "the project"
        raise ArchiveError(
            f"read refused: {path} does not resolve inside {where}; pass "
            "--root <dir> naming the directory a path outside the project "
            "lives in"
        )
    if not resolved.is_file():
        raise ArchiveError(f"read refused: {resolved} is not a file Godmode can read")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines()
    line_range: list[int] | None = None
    if lines is not None:
        lo, hi = lines
        if lo < 1 or hi < lo:
            raise ArchiveError(
                f"read refused: --lines {lo}-{hi} is not an ascending 1-based range")
        slice_lines = all_lines[lo - 1:hi]
        line_range = [lo, hi]
    else:
        slice_lines = all_lines
    digest = hashlib.sha256("\n".join(slice_lines).encode("utf-8")).hexdigest()
    clean_path = _normalise_path(path)
    data = {"source": source, "path": clean_path, "lines": line_range, "digest": digest}
    subject = f"{source}:{clean_path}"
    return archive.append("receipt", subject, data, evidence=[])


def receipts_for(archive: Any, source: str) -> list[dict[str, Any]]:
    """Every receipt recorded for `source`, oldest first."""
    return [
        record for record in archive.select(kind="receipt", limit=500)
        if str((record.get("data") or {}).get("source")) == source
    ]


def surface_only(receipts: list[dict[str, Any]]) -> bool:
    """True only when every receipt's path is surface
    (`godmode_absorb._SURFACE`: README, changelog, release notes, docs/).

    An empty list is deliberately NOT surface-only: nothing was read is a
    different gap than "only the README was read", and a vacuous `all([])`
    would silently conflate the two.
    """
    paths = [str((record.get("data") or {}).get("path") or "") for record in receipts]
    paths = [path for path in paths if path]
    if not paths:
        return False
    return all(_SURFACE.search(path.replace("\\", "/")) for path in paths)


def sources_report(archive: Any) -> dict[str, Any]:
    """Per-source files-opened count and a surface-only flag, for
    `godmode parity --sources`."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in archive.select(kind="receipt", limit=500):
        source = str((record.get("data") or {}).get("source") or "")
        if not source:
            continue
        grouped.setdefault(source, []).append(record)
    sources: dict[str, Any] = {}
    for source, records in grouped.items():
        paths = {str((record.get("data") or {}).get("path")) for record in records}
        sources[source] = {
            "files_opened": len(paths),
            "surface_only": surface_only(records),
        }
    return {"sources": sources}
