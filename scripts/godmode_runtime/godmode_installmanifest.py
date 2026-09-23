"""What an install created, written down instead of guessed at later.

Host artifact writers (`godmode_host_manifests.write_codex_project_hooks` and
its siblings) put files into a project. Nothing recorded which files were ours,
so "which files on this host belong to us" was answerable only by matching a
glob against paths we happened to remember - a guess that decays with every
release, and one that cannot distinguish our file from an identically-named
file another tool wrote.

Three properties this module exists to hold:

- **Per-plugin.** Two plugins installing into one project must not read,
  migrate, or remove each other's artifacts. Ownership is checked on read, not
  inferred from the path, because a path is easy to collide with and a
  recorded name is not.
- **Portable.** Paths are stored relative and POSIX-shaped. A manifest
  carrying an absolute Windows path is unusable on macOS, and one carrying a
  backslash separator is unreadable there. The manifest is data that outlives
  the machine that wrote it.
- **Bounded.** A path outside the project root is refused at record time, so a
  later reader cannot be handed one.

Removal lives in `godmode_installremove.py`, not here: writing a record and
acting on it are different privileges, and the module that only writes should
not import the one that deletes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

#: Bump when the on-disk shape changes. A reader that does not know a version
#: must refuse the file rather than interpret it optimistically.
SCHEMA = 1

MANIFEST_NAME = "install-manifest.json"
STATE_DIRNAME = ".godmode"

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_plugin_name(name: str) -> str:
    """A directory-safe form of a plugin name.

    Separators and traversal segments are collapsed, so a hostile or careless
    name cannot place the manifest outside the project's state directory.
    """
    cleaned = _UNSAFE_NAME.sub("-", name.strip())
    cleaned = cleaned.strip(".-") or "plugin"
    return cleaned


def state_root(project: Path | str) -> Path:
    return Path(project) / STATE_DIRNAME


def manifest_path(project: Path | str, plugin_name: str) -> Path:
    """Where this plugin's manifest lives inside the project."""
    return state_root(project) / sanitize_plugin_name(plugin_name) / MANIFEST_NAME


def relative_posix(project: Path | str, target: Path | str) -> str:
    """`target` as a POSIX path relative to `project`.

    Raises ValueError when the target is outside the project. Resolving both
    sides first is what makes this hold for a symlinked temp directory, which
    is the default on macOS and would otherwise make every path look foreign.
    """
    root = Path(project).resolve()
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"refusing to record {candidate} - outside the install root {root}"
        ) from exc
    return PurePosixPath(*rel.parts).as_posix()


def read(project: Path | str, plugin_name: str) -> dict[str, Any] | None:
    """This plugin's manifest, or None.

    None is returned for an absent file, an unreadable one, an unknown schema
    version, and - importantly - a manifest whose recorded plugin name is not
    ours. A manifest belonging to another installer is left for that installer.
    """
    path = manifest_path(project, plugin_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != SCHEMA:
        return None
    if data.get("pluginName") != plugin_name:
        return None
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return None
    return data


def record(
    project: Path | str,
    plugin_name: str,
    group: str,
    paths: Iterable[Path | str],
) -> dict[str, Any]:
    """Add `paths` to `group` in this plugin's manifest and return it.

    Additive and idempotent: recording the same path twice leaves one entry.
    Every path is validated against the project root before anything is
    written, so a rejected path leaves the manifest untouched.
    """
    entries = [relative_posix(project, p) for p in paths]

    existing = read(project, plugin_name)
    manifest: dict[str, Any] = existing or {
        "version": SCHEMA,
        "pluginName": plugin_name,
        "groups": {},
    }

    current = list(manifest["groups"].get(group, []))
    for entry in entries:
        if entry not in current:
            current.append(entry)
    manifest["groups"][group] = sorted(current)

    path = manifest_path(project, plugin_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return manifest


def forget(
    project: Path | str,
    plugin_name: str,
    entries: Iterable[str],
) -> dict[str, Any] | None:
    """Drop `entries` from every group of this plugin's manifest.

    The counterpart of `record` for a path that is no longer ours on disk:
    an uninstall archives the files, and a manifest that kept listing them
    would report every one as missing and would carry a retired version's
    paths into the next install. A group left empty is removed. Returns the
    rewritten manifest, or None when there is no manifest of ours to edit.
    """
    manifest = read(project, plugin_name)
    if manifest is None:
        return None
    dropped = set(entries)
    groups = {}
    for group, paths in manifest["groups"].items():
        kept = sorted(p for p in paths if p not in dropped)
        if kept:
            groups[group] = kept
    manifest["groups"] = groups
    path = manifest_path(project, plugin_name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return manifest


def recorded_paths(project: Path | str, plugin_name: str) -> list[str]:
    """Every path this plugin recorded, across all groups, sorted and unique."""
    manifest = read(project, plugin_name)
    if not manifest:
        return []
    seen: set[str] = set()
    for entries in manifest["groups"].values():
        seen.update(entries)
    return sorted(seen)
