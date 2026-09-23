"""One containment rule for every path Godmode resolves from a record, manifest or host payload."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .godmode_errors import ArchiveError


def contain(path: str | Path, roots: Sequence[Path]) -> Path | None:
    if not roots:
        return None
    candidate = Path(str(path).replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = Path(roots[0]) / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    for root in roots:
        try:
            if resolved.is_relative_to(Path(root).resolve()):
                return resolved
        except (OSError, RuntimeError):
            continue
    return None


def contained_or_refuse(path: str | Path, roots: Sequence[Path], what: str) -> Path:
    resolved = contain(path, roots)
    if resolved is None:
        raise ArchiveError(f"{what} escapes the project or state home: {path}")
    return resolved
