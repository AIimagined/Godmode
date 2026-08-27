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
from .godmode_constants import IGNORED_DIRECTORY_NAMES

INDEX_FILENAME = "structure_index.json"

# Fixed walk bounds - tune when a real tree measurably exceeds them.
MAX_FILES = 2000
MAX_PARSE_BYTES = 256_000

# Owned by `godmode_constants`, so "which directories does godmode ignore?"
# has one answer rather than depending on which module a reader opens. The
# private copy this replaces had drifted both ways: it walked into
# `coverage`, `target`, `.research`, `.evidence` and `.decisions`, while
# every other walker descended into the tool caches it alone skipped.
_SKIP_DIRS = IGNORED_DIRECTORY_NAMES

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
        # An unreadable or corrupt index is indistinguishable from no index:
        # both mean "nothing may be reused", and the next build re-parses
        # every file. Returned here rather than falling through, so the
        # empty result is the stated answer to a failed read and not a
        # shared exit two different outcomes arrive at.
        return {"files": {}}
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
    calls: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls[f"{node.name}.{item.name}"] = _callee_names(item)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            calls[node.name] = _callee_names(node)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return {
        "classes": sorted(classes),
        "functions": sorted(functions),
        "imports": sorted(set(imports)),
        # L2 (absorbed 2026-08-27): per definition, the names it calls.
        # Names only - a callee is `f` or the `attr` of `x.attr(...)`, never
        # an argument or a body. Resolution to files happens at index time,
        # where every file's definitions are known.
        "calls": {name: callees for name, callees in sorted(calls.items())},
    }


def _callee_names(node: ast.AST) -> list[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return sorted(names)


def _resolve_dependencies(files: dict[str, dict[str, Any]]) -> int:
    """Fill each entry's `dependencies`: the other indexed files that define
    a name it calls. Returns the edge count. Recomputed on every build from
    the whole index, so a reused (unchanged) entry still sees a dependency
    that moved files."""
    defined: dict[str, set[str]] = {}
    for relative, entry in files.items():
        for name in list(entry.get("classes", ())) + list(entry.get("functions", ())):
            defined.setdefault(name, set()).add(relative)
    edges = 0
    for relative, entry in files.items():
        targets: set[str] = set()
        for callees in (entry.get("calls") or {}).values():
            for callee in callees:
                targets.update(f for f in defined.get(callee, ()) if f != relative)
        entry["dependencies"] = sorted(targets)
        edges += len(targets)
    return edges


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
    edges = _resolve_dependencies(files)
    payload = {"files": files}
    try:
        _index_path(archive).write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8")
    except OSError:
        # An index that cannot be written must not leave the PREVIOUS one
        # standing: the report below would say these files were indexed
        # while the cache on disk still describes an older tree, and the
        # next `structure` render would answer from it. Dropping it makes
        # the next build re-parse everything, which is the honest cost of
        # a failed write.
        _index_path(archive).unlink(missing_ok=True)
    return {
        "files": len(files),
        "indexed": indexed,
        "edges": edges,
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
        if entry.get("dependencies"):
            parts.append("-> " + ", ".join(entry["dependencies"]))
        lines.append(f"{relative}" + (f"  ({'; '.join(parts)})" if parts else ""))
    shown = lines[:max(1, limit_lines - 1)]
    rendered = shown[:]
    if len(lines) > len(shown):
        rendered.append(f"... {len(lines) - len(shown)} more entries not shown "
                        f"(limit {limit_lines} lines)")
    return "\n".join(rendered) + "\n"
