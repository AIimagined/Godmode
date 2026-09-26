"""The design boundary this project declared, and the glob matching it uses.

A leaf: it reads `.godmode-boundaries.json` and matches a path against the
declared globs, and depends on nothing that judges an operation. The fence
refuses an edit onto a design surface and the capability broker lets the
operator stage an approval for one; both read the same declaration here, so
neither has to import the other to answer "is this a design surface".
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from .godmode_paths import contain


def _relative(path: str, project_root: Path) -> str | None:
    """The path as the fence spells it, or `None` when it escapes the project.

    The host hands over whatever the agent typed, which is usually absolute and
    on Windows usually backslashed. Judging the raw string would let one file
    pass or fail depending on how it was written, and would make `../` a way
    through any fence. Delegates to `godmode_paths.contain` so a symlink out
    of the project is refused the same way here as everywhere else a path is
    resolved.
    """
    resolved = contain(path, [project_root])
    if resolved is None:
        return None
    return resolved.relative_to(Path(project_root).resolve()).as_posix()


@lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str]:
    """`src/*.py` and `src/**` are different claims and stay different.

    `fnmatch` cannot draw that line - its `*` crosses separators, so every
    shallow pattern would quietly widen into its whole subtree, and a fence
    that widens on its own is not a fence. `PurePath.full_match` does draw it
    but arrived in 3.13, and CI runs 3.11.

    So each segment is translated: `**` spans any number of segments, a single
    `*` is confined to one, `?` to one character.
    """
    parts = pattern.split("/")
    built = ""
    for index, part in enumerate(parts):
        final = index == len(parts) - 1
        if part == "**":
            # Zero or more segments, and the separator belongs to the wildcard
            # rather than to the join: `a/**/b.py` has to match `a/b.py`, or
            # every `**` silently requires an intermediate directory that most
            # of the files it is meant to cover do not have.
            built += "(?:[^/]+/)*[^/]*" if final else "(?:[^/]+/)*"
        else:
            built += re.escape(part).replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
            if not final:
                built += "/"
    return re.compile("^" + built + "$")


def _matches(relative: str, pattern: str) -> bool:
    return _compiled(pattern).match(relative) is not None


BOUNDARY_CONFIG = ".godmode-boundaries.json"

# What a design surface looks like, for the *proposer* only. Nothing here ever
# refuses anything: a `.tsx` file can be pure server-side data loading, a UI
# change can be a string in a plain route file, and an import added tomorrow
# would move the set without a diff to explain it. Enforcement reads declared
# globs; this reads the tree and hands a human a starting point.
_DESIGN_SUFFIXES = frozenset({
    ".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less",
})


def declared_design(project_root: Path | str) -> dict[str, list[str]] | None:
    """The design boundary this project declared, or `None` when it has none.

    An empty list is somebody who started and did not finish, and reading it as
    a boundary would freeze nothing while reporting configured - so it reads as
    absent. Malformed JSON raises rather than degrading to absent: a boundary
    that silently opens because its config failed to parse is the worst of both
    behaviours.
    """
    config = Path(project_root) / BOUNDARY_CONFIG
    if not config.exists():
        return None
    payload = json.loads(config.read_text(encoding="utf-8"))
    section = (payload or {}).get("ui") or {}
    declared = [str(p).strip() for p in (section.get("declared") or []) if str(p).strip()]
    if not declared:
        return None
    return {
        "declared": declared,
        "except": [str(p).strip() for p in (section.get("except") or []) if str(p).strip()],
    }


def design_surface(project_root: Path | str, path: str) -> str | None:
    """The project-relative path when `path` lands on a declared design
    surface, else None - the refusal half of `godmode_fence.design_verdict`
    without its remedy text."""
    root = Path(project_root)
    declared = declared_design(root)
    if declared is None:
        return None
    relative = _relative(path, root)
    if relative is None:
        return None
    if any(_matches(relative, pattern) for pattern in declared["except"]):
        return None
    if not any(_matches(relative, pattern) for pattern in declared["declared"]):
        return None
    return relative
