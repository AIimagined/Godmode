"""Acting on an install manifest: bounded, reversible, ownership-checked.

Separate from `godmode_installmanifest` on purpose. Writing a record and
deleting from disk are different privileges; the module that only writes should
not import the one that removes.

The governing stance is that **the manifest is untrusted input to the code that
wrote it.** A file on disk can be hand-edited, half-written by an interrupted
process, or restored from a backup of a different install. Feeding it straight
into a removal loop is how a cleanup step ends up outside its own directory.

So removal is all-or-nothing: every entry is validated before anything moves.
A manifest with one bad entry removes *nothing*, rather than everything except
the bad entry - a partially-applied removal leaves an install in a state no
code was written to handle.

Nothing here unlinks. Artifacts move into a timestamped archive directory, so
a mistake costs a rename to undo rather than a restore from backup.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import godmode_installmanifest as manifest_io


class UnsafeManifest(Exception):
    """A manifest entry failed containment; the whole removal was refused."""


def is_safe_managed_path(root: Path | str, candidate: Any) -> bool:
    """True when `candidate` is a relative path that stays inside `root`.

    Three layers, cheapest first, because the last one is the only sound one
    and the first two make its failures rarer and its reasons clearer:

    1. reject anything that is not a non-empty string,
    2. reject absolute paths and any `..` segment, split on **both**
       separators so the check does not change meaning between platforms,
    3. resolve the candidate against the resolved root and require containment.

    Layer 3 uses an explicit separator check rather than `str.startswith`
    alone, so a sibling directory whose name merely begins with the root's name
    does not pass.
    """
    if not isinstance(candidate, str) or not candidate:
        return False

    if Path(candidate).is_absolute():
        return False
    # A drive-relative or UNC-ish form is absolute on Windows and not on POSIX;
    # reject the shapes outright so the verdict does not depend on the host.
    if candidate.startswith(("/", "\\")) or (len(candidate) > 1 and candidate[1] == ":"):
        return False

    segments = candidate.replace("\\", "/").split("/")
    if any(segment == ".." for segment in segments):
        return False

    resolved_root = Path(root).resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved == resolved_root:
        return False
    return resolved_root in resolved.parents


def plan_removal(project: Path | str, plugin_name: str) -> list[str]:
    """Every recorded path, validated. Raises rather than returning a subset.

    An empty list means "nothing recorded", which is a legitimate state and not
    an error. A refusal means the manifest cannot be trusted at all.
    """
    entries = manifest_io.recorded_paths(project, plugin_name)
    unsafe = [entry for entry in entries if not is_safe_managed_path(project, entry)]
    if unsafe:
        raise UnsafeManifest(
            "refusing the whole removal; these entries are not contained by "
            f"{Path(project).resolve()}: {unsafe}"
        )
    return entries


def archive_dirname(now: datetime | None = None) -> str:
    """A timestamped directory name that is a legal filename on every host.

    No colon: `%H:%M:%S` is legal on macOS and illegal on Windows, so a name
    built that way round-trips on one platform and raises OSError on the other.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return stamp


def archive(
    project: Path | str,
    plugin_name: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Move this plugin's recorded artifacts into a timestamped archive.

    Returns what was moved, what was already gone, and where it went. A project
    with no manifest for this plugin is a no-op, not an error: asking a clean
    machine to uninstall should succeed quietly.
    """
    root = Path(project)
    entries = plan_removal(root, plugin_name)
    if not entries:
        return {"archived": [], "missing": [], "archive_dir": None}

    destination = (
        manifest_io.manifest_path(root, plugin_name).parent
        / "removed"
        / archive_dirname(now)
    )

    archived: list[str] = []
    missing: list[str] = []
    for entry in entries:
        source = root / entry
        if not source.exists():
            missing.append(entry)
            continue
        target = destination / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        archived.append(entry)

    # The files are gone from the project, so the record of them goes too:
    # a manifest still naming them would make `hooks status` report each one
    # missing, and an install of the next version would inherit this one's
    # retired paths as if it had written them.
    manifest_io.forget(root, plugin_name, archived + missing)

    return {
        "archived": archived,
        "missing": missing,
        "archive_dir": str(destination) if archived else None,
    }
