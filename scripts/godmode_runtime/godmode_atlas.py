"""A native map of a project's symbols and the relationships between them.

The corpus ranks documents; this ranks code. Without symbol-level structure a
detector cannot answer what a change touches, whether an implementation is
reachable, or whether a capability already exists under a different name — it can
only grep, which is how a capability gets built twice.

Two rules shape the design:

* Extracted and inferred relationships are never blurred. An edge parsed from a
  syntax tree is a fact; an edge guessed from a name match is a lead. Reporting a
  guess as a fact once cost a scheduled work item on a defect that did not exist,
  so `evidence` is carried on every edge and callers may filter on it.
* Absence is only claimed from a complete read. A file that could not be parsed is
  recorded as unparsed rather than silently contributing nothing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable

from .godmode_constants import CODE_SUFFIXES, IGNORED_DIRECTORY_NAMES
from .godmode_errors import GodmodeError

EXTRACTED = "extracted"
INFERRED = "inferred"

DEFINES = "defines"
IMPORTS = "imports"
CALLS = "calls"

# Languages without a stdlib parser get a shape-matched extractor. Its output is
# INFERRED by construction: a regex cannot prove a definition is reachable.
_GENERIC_DEFINITION = re.compile(
    r"^[ \t]*(?:export\s+)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*"
    r"(?:function|func|fn|def|class|interface|struct|type|impl|trait|enum)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
# Two shapes: a quoted module anywhere on the line (covers `import { x } from './m'`
# and `require("m")`), or a bare module directly after the keyword (Python, Go).
_GENERIC_IMPORT = re.compile(
    r"^[ \t]*(?:import|from|require|use|include|#include)\b"
    r"(?:[^\n]*?[\"'<]([A-Za-z0-9_./@-]+)[\"'>]|\s+([A-Za-z0-9_./-]+))",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    path: str
    line: int

    @property
    def id(self) -> str:
        return f"{self.path}::{self.name}"

    def view(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "path": self.path, "line": self.line}


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str
    evidence: str
    line: int = 0

    def view(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target,
                "relation": self.relation, "evidence": self.evidence, "line": self.line}


@dataclass
class Atlas:
    project: Path
    symbols: list[Symbol] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    unparsed: list[dict[str, str]] = field(default_factory=list)

    # ---- queries -------------------------------------------------------------

    def by_path(self, path: str) -> list[Symbol]:
        return [symbol for symbol in self.symbols if symbol.path == path]

    def affected(self, target: str, depth: int = 2, evidence: str | None = EXTRACTED) -> dict[str, Any]:
        """Reverse traversal: what breaks if `target` changes.

        Defaults to extracted edges only. A blast radius built from guesses is
        worse than none, because it reads as a complete answer.
        """
        edges = [e for e in self.edges if evidence is None or e.evidence == evidence]
        # Index by module key so a query works whether the caller names a file path
        # or an import name.
        incoming: dict[str, list[Edge]] = {}
        for edge in edges:
            incoming.setdefault(module_key(edge.target), []).append(edge)

        # `seen` is keyed by module key throughout; mixing keys with full ids would
        # let the same dependent be rediscovered at every level and report the
        # distance of its last visit rather than its first.
        root = module_key(target)
        seen: dict[str, tuple[str, int]] = {}
        frontier = [root]
        for level in range(1, max(1, depth) + 1):
            following: list[str] = []
            for node in frontier:
                for edge in incoming.get(node, []):
                    source = module_key(edge.source)
                    if source in seen or source == root:
                        continue
                    seen[source] = (edge.source, level)
                    following.append(source)
            frontier = following
            if not frontier:
                break
        return {
            "target": target,
            "depth": depth,
            "evidence": evidence or "any",
            "dependents": [
                {"id": identifier, "distance": level}
                for _, (identifier, level) in sorted(seen.items())
            ],
            "count": len(seen),
        }

    def cycles(self) -> list[list[str]]:
        """File-level import cycles, from extracted edges only."""
        # An import names a module ("b"); a source names a file ("b.py"). Compare
        # them on a common key, or a cycle is invisible because the two spellings
        # never meet.
        key = module_key
        known = {key(f) for f in self.files}
        graph: dict[str, set[str]] = {}
        for edge in self.edges:
            if edge.relation != IMPORTS or edge.evidence != EXTRACTED:
                continue
            source, target = key(edge.source), key(edge.target)
            # Only local modules can participate; a third-party import is not a cycle.
            if source != target and target in known:
                graph.setdefault(source, set()).add(target)

        found: list[list[str]] = []
        state: dict[str, int] = {}

        def walk(node: str, trail: list[str]) -> None:
            state[node] = 1
            for neighbour in sorted(graph.get(node, ())):
                if state.get(neighbour) == 1:
                    cycle = trail[trail.index(neighbour):] + [neighbour]
                    if cycle not in found:
                        found.append(cycle)
                elif state.get(neighbour, 0) == 0:
                    walk(neighbour, trail + [neighbour])
            state[node] = 2

        for node in sorted(graph):
            if state.get(node, 0) == 0:
                walk(node, [node])
        return found

    def orphans(self) -> list[dict[str, Any]]:
        """Symbols defined but never referenced anywhere extracted.

        Presence is not wiring. A capability that exists and is never reached is a
        different defect from one that is missing, and they need different fixes.
        """
        referenced = {edge.target for edge in self.edges if edge.relation in (CALLS, IMPORTS)}
        return [
            symbol.view()
            for symbol in self.symbols
            if symbol.kind in ("function", "class") and symbol.id not in referenced
            and not symbol.name.startswith("_")
        ]

    def duplicates(self, threshold: float = 0.6) -> list[dict[str, Any]]:
        """Near-duplicate symbol names by character-shingle similarity.

        Catches the same capability implemented twice under different names, which a
        literal search never finds because the names differ by design.
        """
        candidates = [s for s in self.symbols if s.kind in ("function", "class") and len(s.name) >= 6]
        signatures = {s.id: _shingles(s.name) for s in candidates}
        pairs: list[dict[str, Any]] = []
        for index, first in enumerate(candidates):
            for second in candidates[index + 1:]:
                if first.name == second.name and first.path == second.path:
                    continue
                score = _jaccard(signatures[first.id], signatures[second.id])
                if score >= threshold:
                    pairs.append({"a": first.view(), "b": second.view(), "similarity": round(score, 3)})
        pairs.sort(key=lambda pair: (-pair["similarity"], pair["a"]["id"]))
        return pairs

    def diagnose(self) -> dict[str, Any]:
        """Report on the atlas itself, so a bad map is not mistaken for a bad project."""
        extracted = sum(1 for e in self.edges if e.evidence == EXTRACTED)
        inferred = len(self.edges) - extracted
        findings: list[str] = []
        if self.unparsed:
            findings.append(f"{len(self.unparsed)} files could not be parsed; absence claims about them are unsafe")
        if self.edges and inferred / len(self.edges) > 0.5:
            findings.append("most relationships are inferred; treat traversal results as leads")
        if not self.symbols:
            findings.append("no symbols extracted; the atlas cannot answer structural questions")
        return {
            "files": len(self.files),
            "unparsed": self.unparsed,
            "symbols": len(self.symbols),
            "edges": {"total": len(self.edges), "extracted": extracted, "inferred": inferred},
            "findings": findings,
            "trustworthy": not findings,
        }

    def view(self) -> dict[str, Any]:
        return {
            "files": len(self.files),
            "symbols": len(self.symbols),
            "edges": len(self.edges),
            "diagnosis": self.diagnose(),
        }


def module_key(node: str) -> str:
    """Reduce a file path or an import name to one comparable module key.

    `from .godmode_chronicle import Chronicle` records the module name, while the
    file that defines it is a path. Without a common key the two spellings never
    meet and every structural query silently answers zero.
    """
    head = node.split("::")[0].replace("\\", "/").lstrip(".")
    head = re.sub(r"\.[A-Za-z0-9]+$", "", head)
    return head.rsplit("/", 1)[-1]


def _shingles(text: str, width: int = 3) -> set[str]:
    lowered = re.sub(r"[^a-z0-9]", "", text.lower())
    if len(lowered) <= width:
        return {lowered}
    return {lowered[i:i + width] for i in range(len(lowered) - width + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _python_symbols(path: str, text: str) -> tuple[list[Symbol], list[Edge]]:
    """Exact extraction via the standard library parser."""
    tree = ast.parse(text)
    symbols: list[Symbol] = []
    edges: list[Edge] = []
    defined: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            symbol = Symbol(name=node.name, kind=kind, path=path, line=node.lineno)
            symbols.append(symbol)
            defined[node.name] = symbol.id
        elif isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(Edge(f"{path}::<module>", f"{alias.name}::<module>", IMPORTS, EXTRACTED, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            edges.append(Edge(f"{path}::<module>", f"{node.module}::<module>", IMPORTS, EXTRACTED, node.lineno))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name and name in defined:
                edges.append(Edge(f"{path}::<module>", defined[name], CALLS, EXTRACTED, node.lineno))
    return symbols, edges


def _generic_symbols(path: str, text: str) -> tuple[list[Symbol], list[Edge]]:
    """Shape-matched extraction for languages without a stdlib parser."""
    symbols: list[Symbol] = []
    edges: list[Edge] = []
    for match in _GENERIC_DEFINITION.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        symbols.append(Symbol(name=match.group(1), kind="function", path=path, line=line))
    for match in _GENERIC_IMPORT.finditer(text):
        module = match.group(1) or match.group(2)
        if not module:
            continue
        line = text.count("\n", 0, match.start()) + 1
        edges.append(Edge(f"{path}::<module>", f"{module}::<module>", IMPORTS, INFERRED, line))
    return symbols, edges


def slice_file(path: Path, start: int = 1, end: int | None = None, limit: int = 400) -> dict[str, Any]:
    """Return a bounded window that declares its own edges.

    Every slice states what it covers, so a later claim of "not present" can be
    checked against whether the reader ever saw the whole file.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise GodmodeError(f"Cannot read {path}: {exc}") from exc
    total = len(lines)
    start = max(1, start)
    end = total if end is None else min(end, total)
    if end - start + 1 > limit:
        end = start + limit - 1
    window = lines[start - 1:end]
    return {
        "path": str(path),
        "total_lines": total,
        "start": start,
        "end": end,
        "complete": start == 1 and end == total,
        "truncated_before": start > 1,
        "truncated_after": end < total,
        "text": "\n".join(window),
    }


def build(project: Path, suffixes: Iterable[str] | None = None) -> Atlas:
    allowed = set(suffixes) if suffixes else set(CODE_SUFFIXES)
    atlas = Atlas(project=project)
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        relative = path.relative_to(project).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            atlas.unparsed.append({"path": relative, "reason": str(exc)[:120]})
            continue
        atlas.files.append(relative)
        try:
            if path.suffix.lower() == ".py":
                symbols, edges = _python_symbols(relative, text)
            else:
                symbols, edges = _generic_symbols(relative, text)
        except SyntaxError as exc:
            atlas.unparsed.append({"path": relative, "reason": f"syntax error line {exc.lineno}"})
            continue
        atlas.symbols.extend(symbols)
        atlas.edges.extend(edges)
    return atlas


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "core.py").write_text(
            "def rotate_token():\n    return 1\n\n"
            "class TokenStore:\n    pass\n",
            encoding="utf-8",
        )
        (project / "api.py").write_text(
            "from core import rotate_token\n\n"
            "def handler():\n    return rotate_token()\n",
            encoding="utf-8",
        )
        (project / "widget.ts").write_text(
            "import { thing } from './core';\nexport function renderWidget() {}\n",
            encoding="utf-8",
        )

        atlas = build(project)
        names = {s.name for s in atlas.symbols}
        assert {"rotate_token", "TokenStore", "handler", "renderWidget"} <= names, names

        # Python edges are extracted; the TypeScript import is only inferred.
        kinds = {(e.relation, e.evidence) for e in atlas.edges}
        assert (IMPORTS, EXTRACTED) in kinds and (IMPORTS, INFERRED) in kinds, kinds

        # Reverse traversal finds the dependent module, extracted-only by default.
        impact = atlas.affected("core::<module>")
        assert impact["count"] >= 1, impact
        assert any(d["id"].startswith("api.py") for d in impact["dependents"]), impact

        # Inferred edges are excluded unless asked for, so a guess never inflates
        # a blast radius that reads as complete.
        strict = atlas.affected("core")
        loose = atlas.affected("core", evidence=None)
        strict_ids = {d["id"] for d in strict["dependents"]}
        loose_ids = {d["id"] for d in loose["dependents"]}
        assert not any("widget.ts" in i for i in strict_ids), strict
        assert any("widget.ts" in i for i in loose_ids), loose
        assert loose["count"] > strict["count"], (strict, loose)
        # A direct dependent is distance 1, not the level it was last revisited at.
        assert all(d["distance"] == 1 for d in strict["dependents"]), strict

        diagnosis = atlas.diagnose()
        assert diagnosis["edges"]["extracted"] >= 1
        assert diagnosis["symbols"] == len(atlas.symbols)

        # Unparsable input is recorded, never silently skipped.
        (project / "broken.py").write_text("def (:\n", encoding="utf-8")
        broken = build(project)
        assert broken.unparsed and broken.unparsed[0]["path"] == "broken.py", broken.unparsed
        assert not broken.diagnose()["trustworthy"]

        # Near-duplicate detection catches one capability written twice.
        (project / "dup.py").write_text(
            "def rotate_tokens():\n    return 2\n", encoding="utf-8"
        )
        pairs = build(project).duplicates(threshold=0.6)
        assert any({p["a"]["name"], p["b"]["name"]} == {"rotate_token", "rotate_tokens"} for p in pairs), pairs

        # A cycle is reported only from extracted edges.
        (project / "a.py").write_text("import b\n", encoding="utf-8")
        (project / "b.py").write_text("import a\n", encoding="utf-8")
        assert any(set(cycle) >= {"a", "b"} for cycle in build(project).cycles())

        window = slice_file(project / "core.py", start=2, end=3)
        assert window["truncated_before"] and not window["complete"], window
        whole = slice_file(project / "core.py")
        assert whole["complete"] and not whole["truncated_after"], whole

    print("godmode_atlas self-check OK")


if __name__ == "__main__":
    _self_check()
