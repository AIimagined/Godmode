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

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import godmode_installmanifest as manifest_io


class UnsafeManifest(Exception):
    """A manifest entry failed containment; the whole removal was refused."""


# Groups whose recorded path is a file this plugin only partly owns - a JSON
# object keyed by tool, so an uninstall must strip only this plugin's key and
# leave any other tool's key (and the file) in place. Maps the manifest group
# name to the JSON key this plugin's entries live under.
#
# Antigravity's `.agents/hooks.json` maps hook names to configs, one
# key per tool (`write_antigravity_project_hooks` merges only the `godmode`
# key in). Treating the recorded path as a whole-file artifact on removal -
# the same handling every other host writer gets - moved the entire file into
# the archive, taking every other tool's hooks with it.
SHARED_KEY_GROUPS: dict[str, str] = {
    "antigravity-hooks": "godmode",
}


def _strip_shared_key(source: Path, backup_target: Path, key: str) -> bool:
    """Remove `key` from the JSON object at `source`, in place.

    `source` is a file this plugin does not own outright; other tools' keys in
    the same object must survive. The removed fragment is written to
    `backup_target` so the operation stays recoverable the same way a whole-
    file move is - the archive holds what was taken.

    When the object holds no other key after removal, the file itself is
    removed rather than left behind as an empty shell (an uninstall must
    still leave nothing behind for the common case of a project no other tool
    has touched).

    Returns False - nothing removed - for a file that is not a JSON object or
    does not carry `key`: a corrupt or foreign-shaped file is never rewritten.
    """
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or key not in data:
        return False

    removed = data.pop(key)
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    backup_target.write_text(
        json.dumps({key: removed}, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if data:
        source.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        source.unlink()
    return True


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

    manifest = manifest_io.read(root, plugin_name) or {"groups": {}}
    shared_key_of: dict[str, str] = {}
    for group, key in SHARED_KEY_GROUPS.items():
        for entry in manifest["groups"].get(group, []):
            shared_key_of[entry] = key

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
        owned_key = shared_key_of.get(entry)
        if owned_key is not None:
            if _strip_shared_key(source, destination / entry, owned_key):
                archived.append(entry)
            else:
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
