"""B4-6 MVP: a per-project structural index, so resume-time context comes
from a cache instead of re-reading source files.

Deliberately narrow, and the narrowness is stated rather than implied:
Python files get top-level classes, top-level functions, and imported
module names via `ast`; every other text file gets a file-level entry
(path + content hash) and nothing more. NOT claimed: methods, call
graphs, control flow, data flow, non-Python symbols - the sweep source's
full ladder is roadmap, and the coverage map carries this row as partial.

Privacy: the index stores names and content hashes only - never a source
body, never a docstring. Incremental by content hash: an unchanged file is
never re-parsed, which is the entire point (the cache must be cheaper than
the re-read it replaces). The index is disposable operational state in the
state home, outside the hash chain - losing it costs one rebuild.

Bounds are stated, never silent: the walk caps files and per-file parse
size, and the report says how many fell outside each cap; the outline caps
its lines and says how many entries are not shown.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle

INDEX_FILENAME = "structure_index.json"

# [private]: fixed walk bounds, tune when a real tree measurably exceeds them.
MAX_FILES = 2000
MAX_PARSE_BYTES = 256_000

_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build",
})

# File-level entries are only worth carrying for things a person edits.
_TEXT_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".js", ".ts", ".tsx", ".jsx", ".mjs", ".sh", ".ps1", ".html", ".css",
    ".sql", ".rs", ".go", ".java", ".rb", ".c", ".h", ".cpp",
})


def _index_path(archive: Chronicle) -> Path:
    return archive.root / INDEX_FILENAME


def _load_index(archive: Chronicle) -> dict[str, Any]:
    try:
        raw = json.loads(_index_path(archive).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("files"), dict):
            return raw
    except (OSError, json.JSONDecodeError):
        pass
    return {"files": {}}


def _python_symbols(source: str) -> dict[str, list[str]] | None:
    """Top-level names only; None when the file does not parse - the entry
    degrades to file-level rather than failing the build."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    classes: list[str] = []
    functions: list[str] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return {
        "classes": sorted(classes),
        "functions": sorted(functions),
        "imports": sorted(set(imports)),
    }


def build_structure_index(archive: Chronicle, project: Path) -> dict[str, Any]:
    """Build or refresh the index; unchanged hashes are never re-parsed."""
    project = Path(project)
    previous = _load_index(archive)["files"]
    files: dict[str, Any] = {}
    indexed = reused = 0
    skipped_over_cap = skipped_oversize = 0
    seen = 0
    for base, directories, names in os.walk(project):
        directories[:] = sorted(
            d for d in directories
            if d not in _SKIP_DIRS and not d.startswith(".godmode"))
        for name in sorted(names):
            path = Path(base) / name
            if path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            seen += 1
            if len(files) >= MAX_FILES:
                skipped_over_cap += 1
                continue
            relative = path.relative_to(project).as_posix()
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            prior = previous.get(relative)
            if prior is not None and prior.get("hash") == digest:
                files[relative] = prior
                reused += 1
                continue
            entry: dict[str, Any] = {"hash": digest}
            if path.suffix.lower() == ".py":
                if len(raw) > MAX_PARSE_BYTES:
                    skipped_oversize += 1
                else:
                    symbols = _python_symbols(
                        raw.decode("utf-8", errors="replace"))
                    if symbols is not None:
                        entry.update(symbols)
            files[relative] = entry
            indexed += 1
    payload = {"files": files}
    try:
        _index_path(archive).write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8")
    except OSError:
        # An index that cannot be written is one rebuild away, never an error.
        pass
    return {
        "files": len(files),
        "indexed": indexed,
        "reused": reused,
        "skipped_over_file_cap": skipped_over_cap,
        "skipped_oversized_parse": skipped_oversize,
    }


def structure_outline(archive: Chronicle, limit_lines: int = 200) -> str:
    """A bounded outline rendered from the INDEX alone - the source may be
    gone, and reading it here would defeat the cache. Deterministic order;
    the cut is stated."""
    entries = _load_index(archive)["files"]
    lines: list[str] = []
    for relative in sorted(entries):
        entry = entries[relative]
        parts = []
        if entry.get("classes"):
            parts.append("classes: " + ", ".join(entry["classes"]))
        if entry.get("functions"):
            parts.append("functions: " + ", ".join(entry["functions"]))
        if entry.get("imports"):
            parts.append("imports: " + ", ".join(entry["imports"]))
        lines.append(f"{relative}" + (f"  ({'; '.join(parts)})" if parts else ""))
    shown = lines[:max(1, limit_lines - 1)]
    rendered = shown[:]
    if len(lines) > len(shown):
        rendered.append(f"... {len(lines) - len(shown)} more entries not shown "
                        f"(limit {limit_lines} lines)")
    return "\n".join(rendered) + "\n"
