"""C-52: capabilities install as extensions rather than growing the core.

An extension is a directory under the private state home,
`<state-home>/extensions/<name>/`, holding an `extension.json` manifest:

    {"name": "<dir name>", "version": "0.1.0", "entry": "main.py",
     "about": "one line"}

and the entry module, which exposes `run(argv, context) -> dict`.

Two operations, kept apart on purpose. `list_extensions` reads manifests
only and imports nothing, so a listing can never execute code that merely
sits in the directory. `run_extension` imports and runs one, and only
when the project's authorization policy names it in an `extensions` list.
That file is already a protected surface the gate guards, so enabling an
extension is an operator act on a governed file - never a side effect of
placing a directory, and never something a tool call can do unasked.

Godmode's own doctrine holds: an extension is a way to split godmode's
capabilities, not a runtime dependency on a third party.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
from typing import Any

from .godmode_anchor import application_home
from .godmode_errors import AuthorizationError, GodmodeError
from .godmode_profile import POLICY_FILENAME, _read_policy

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class ExtensionRefused(GodmodeError):
    """The extension exists but the project's policy does not name it."""


def extensions_root(home: Path | str | None = None) -> Path:
    return Path(home) if home else application_home() / "extensions"


def list_extensions(home: Path | str | None = None) -> list[dict[str, Any]]:
    root = (Path(home) / "extensions") if home else extensions_root()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest_path = directory / "extension.json"
        entry: dict[str, Any] = {"name": directory.name, "path": str(directory)}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
            if manifest.get("name") != directory.name or not _NAME.match(directory.name):
                raise ValueError("manifest name must equal the directory name")
            entry_file = str(manifest.get("entry") or "")
            if (not entry_file.endswith(".py") or "/" in entry_file or "\\" in entry_file
                    or ".." in entry_file):
                raise ValueError("entry must be a .py file in the extension directory")
            entry.update({
                "version": str(manifest.get("version") or ""),
                "about": str(manifest.get("about") or "")[:200],
                "entry": entry_file,
            })
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            entry["error"] = f"{exc}"
        out.append(entry)
    return out


def allowed_extensions(project: Path) -> set[str]:
    raw = _read_policy(Path(project)).get("extensions")
    if raw is None:
        return set()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise AuthorizationError(
            f"{POLICY_FILENAME}'s extensions must be a list of strings, not {type(raw).__name__}")
    return set(raw)


def run_extension(project: Path | str, name: str, argv: list[str],
                  home: Path | str | None = None) -> dict[str, Any]:
    project = Path(project)
    listed = {e["name"]: e for e in list_extensions(home)}
    if name not in listed:
        raise GodmodeError(f"no extension named {name!r} under {extensions_root(home) if home is None else Path(home) / 'extensions'}")
    if "error" in listed[name]:
        raise GodmodeError(f"extension {name!r} has a malformed manifest: {listed[name]['error']}")
    if name not in allowed_extensions(project):
        raise ExtensionRefused(
            f"extension {name!r} is not named in {POLICY_FILENAME}'s `extensions` list "
            "for this project; add it there to allow it - the policy file is a "
            "protected surface, so that is an operator act")
    entry = Path(listed[name]["path"]) / listed[name]["entry"]
    spec = importlib.util.spec_from_file_location(f"godmode_extension_{name.replace('-', '_')}", entry)
    if spec is None or spec.loader is None:
        raise GodmodeError(f"extension {name!r}: cannot load {entry.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise GodmodeError(f"extension {name!r}: {entry.name} defines no run(argv, context)")
    result = run(list(argv), {"project": str(project), "extension": name})
    if not isinstance(result, dict):
        raise GodmodeError(f"extension {name!r}: run() must return a dict")
    return result
