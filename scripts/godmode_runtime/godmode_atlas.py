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
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable

from .godmode_constants import CODE_SUFFIXES, IGNORED_DIRECTORY_NAMES
from .godmode_errors import GodmodeError

EXTRACTED = "extracted"
INFERRED = "inferred"

DEFINES = "defines"
IMPORTS = "imports"
CALLS = "calls"
# A test importing a module and an app importing it are different obligations:
# one breaks at runtime, the other is the safety net. Distinct relation kinds
# keep "who calls this" and "what covers this" answerable separately.
TESTED_BY = "tested-by"
DOCUMENTS = "documents"

# Traversal results are bucketed by what the relation means to a caller, not by
# its literal name, so adding a relation kind does not change the report shape.
_RELATION_BUCKET = {CALLS: "callers", IMPORTS: "callers",
                    TESTED_BY: "tests", DOCUMENTS: "docs"}

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
    # symbol id -> shingles over its (approximate) body, so duplicates are found
    # by what code does, not what it happens to be called.
    body_signatures: dict[str, frozenset] = field(default_factory=dict)

    # ---- queries -------------------------------------------------------------

    def by_path(self, path: str) -> list[Symbol]:
        return [symbol for symbol in self.symbols if symbol.path == path]

    def affected(self, target: str, depth: int = 2, evidence: str | None = EXTRACTED,
                 relations: set[str] | None = None) -> dict[str, Any]:
        """Reverse traversal: what breaks if `target` changes.

        Defaults to extracted edges only. A blast radius built from guesses is
        worse than none, because it reads as a complete answer.

        `relations` narrows traversal to those relation kinds, because "what
        tests cover this" and "who calls this" are different questions that
        happen to share one graph. The answer is also bucketed by relation
        (callers / tests / docs) so a README mention is never mistaken for a
        runtime dependency when the two land in one flat list.
        """
        edges = [e for e in self.edges
                 if (evidence is None or e.evidence == evidence)
                 and (relations is None or e.relation in relations)]
        # Index by module key so a query works whether the caller names a file path
        # or an import name.
        incoming: dict[str, list[Edge]] = {}
        for edge in edges:
            incoming.setdefault(module_key(edge.target), []).append(edge)

        # `seen` is keyed by module key throughout; mixing keys with full ids would
        # let the same dependent be rediscovered at every level and report the
        # distance of its last visit rather than its first.
        root = module_key(target)
        seen: dict[str, tuple[str, int, set[str]]] = {}
        frontier = [root]
        for level in range(1, max(1, depth) + 1):
            following: list[str] = []
            for node in frontier:
                for edge in incoming.get(node, []):
                    source = module_key(edge.source)
                    if source == root:
                        continue
                    if source in seen:
                        # A rediscovered dependent keeps its first distance but
                        # gains the relation kind: a file can import a module
                        # and also test it, and both facts belong in the answer.
                        seen[source][2].add(edge.relation)
                        continue
                    seen[source] = (edge.source, level, {edge.relation})
                    following.append(source)
            frontier = following
            if not frontier:
                break
        buckets: dict[str, list[dict[str, Any]]] = {"callers": [], "tests": [], "docs": []}
        dependents: list[dict[str, Any]] = []
        for _, (identifier, level, kinds) in sorted(seen.items()):
            entry = {"id": identifier, "distance": level, "relations": sorted(kinds)}
            dependents.append(entry)
            for bucket in {_RELATION_BUCKET.get(kind, kind) for kind in kinds}:
                buckets.setdefault(bucket, []).append(entry)
        return {
            "target": target,
            "depth": depth,
            "evidence": evidence or "any",
            "relations": sorted(relations) if relations else "any",
            "dependents": dependents,
            "count": len(seen),
            **buckets,
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
        # An import edge targets `module::name`; a symbol id is `dir/module.py::name`.
        # Match on (module stem, symbol name) as well, or cross-module references
        # never resolve and the orphan list is mostly noise.
        referenced_names = {
            (module_key(target.rsplit("::", 1)[0]), target.rsplit("::", 1)[1])
            for target in referenced if "::" in target
        }
        return [
            symbol.view()
            for symbol in self.symbols
            if symbol.kind in ("function", "class")
            and symbol.id not in referenced
            and (module_key(symbol.path), symbol.name) not in referenced_names
            and not symbol.name.startswith("_")
            # Test files are entry points: the runner discovers them by pattern,
            # so "never imported" is their normal state, not a defect.
            and not _is_test_path(symbol.path)
        ]

    def duplicates(self, threshold: float = 0.6) -> list[dict[str, Any]]:
        """Near-duplicate symbol names by character-shingle similarity.

        Catches the same capability implemented twice under different names, which a
        literal search never finds because the names differ by design.

        Two populations are excluded because they are conventions, not
        duplication, and reporting them buries the real finding: test methods,
        which are named descriptively and therefore similarly by design, and
        private helpers, where a repeated `_self_check` or `_finding` across
        modules is the house pattern being followed rather than a capability
        built twice.
        """
        candidates = [
            s for s in self.symbols
            if s.kind in ("function", "class")
            and len(s.name) >= 6
            and not s.name.startswith("_")
            and not _is_test_path(s.path)
        ]
        signatures = {s.id: _shingles(s.name) for s in candidates}
        pairs: list[dict[str, Any]] = []
        for index, first in enumerate(candidates):
            for second in candidates[index + 1:]:
                if first.name == second.name and first.path == second.path:
                    continue
                name_score = _jaccard(signatures[first.id], signatures[second.id])
                # Two implementations of one behaviour under unrelated names have
                # similar bodies; the name comparison alone would never see them.
                body_score = _jaccard(
                    self.body_signatures.get(first.id, frozenset()),
                    self.body_signatures.get(second.id, frozenset()),
                ) if self.body_signatures.get(first.id) and self.body_signatures.get(second.id) else 0.0
                score, basis = max((name_score, "name"), (body_score, "body"))
                # An identical name in two modules with different bodies is an
                # interface convention - every detector exposing `analyze` is the
                # pattern being followed, not a capability built twice. Only the
                # bodies agreeing makes it a duplicate worth reporting.
                if first.name == second.name and body_score < threshold:
                    continue
                if score >= threshold:
                    pairs.append({"a": first.view(), "b": second.view(),
                                  "similarity": round(score, 3), "basis": basis})
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
        # A mostly-orphaned graph is a resolution failure in the atlas, not a
        # mostly-dead project - report it as this map's defect.
        named = [s for s in self.symbols if s.kind in ("function", "class")
                 and not s.name.startswith("_")]
        if named:
            orphan_ratio = len(self.orphans()) / len(named)
            if orphan_ratio > 0.4:
                findings.append(
                    f"{orphan_ratio:.0%} of public symbols resolve as orphans; the "
                    "reference resolver is likely missing edges - distrust the orphan list"
                )
        # Per-suffix honesty: a suffix whose files yielded no symbols is counted,
        # not understood, and any structural claim about those files is unsafe.
        by_suffix: dict[str, dict[str, int]] = {}
        symbol_paths = {s.path for s in self.symbols}
        for name in self.files:
            suffix = "." + name.rsplit(".", 1)[-1] if "." in name else "(none)"
            entry = by_suffix.setdefault(suffix, {"files": 0, "understood": 0})
            entry["files"] += 1
            if name in symbol_paths:
                entry["understood"] += 1
        suffix_support = {
            suffix: ("parsed" if counts["understood"] else "counted, not understood")
            for suffix, counts in sorted(by_suffix.items())
        }
        opaque = sorted(s for s, v in suffix_support.items() if v != "parsed")
        if opaque:
            findings.append(
                f"suffixes counted but not understood: {', '.join(opaque)}; "
                "structural claims about those files are unsafe"
            )
        return {
            "files": len(self.files),
            "unparsed": self.unparsed,
            "symbols": len(self.symbols),
            "suffix_support": suffix_support,
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


def speculative_seams(atlas: "Atlas") -> dict[str, Any]:
    """Modules that exist for exactly one consumer.

    "One adapter means a hypothetical seam. Two adapters means a real one." An
    interface with a single consumer may be right - a module can be young, or
    genuinely deep - but it is the shape a speculative abstraction takes, and
    nothing here looked for it.

    Tests do not count as consumers. Every module has one importing it, so
    counting them would make every speculative seam look justified and the
    check would report nothing forever.

    Zero consumers is not reported: that is what `orphans` answers, and a
    finding two surfaces report is a finding neither gets fixed for.

    The deletion test that accompanies this rule - delete the module and see
    whether complexity vanishes or reappears across N callers - is not
    computable from an import graph. It is asked, not pretended at.
    """
    consumers: dict[str, set[str]] = {}
    modules: set[str] = set()
    for edge in atlas.edges:
        if edge.relation != IMPORTS or edge.evidence != EXTRACTED:
            continue
        target = module_key(edge.target)
        source = str(edge.source).replace("\\", "/").split("::")[0]
        modules.add(target)
        if _looks_like_a_test(source):
            continue
        consumers.setdefault(target, set()).add(source)

    by_key = {module_key(path): path for path in atlas.files}
    findings: list[dict[str, Any]] = []
    for target, users in sorted(consumers.items()):
        if len(users) != 1:
            continue
        # Only modules this project owns. An import edge also names the
        # standard library, and `import base64` used once is not a seam anybody
        # can delete - reporting it buries the actionable findings under a list
        # of Python's own modules.
        module = by_key.get(target)
        if module is None:
            continue
        consumer = sorted(users)[0]
        findings.append({
            "module": module,
            "consumer": consumer,
            "question": f"'{module}' is used only by '{consumer}'. Delete it in your head: "
                        "does the complexity vanish, or reappear across its callers? If it "
                        "vanishes, this seam is a guess about a second caller that has not "
                        "arrived.",
        })
    return {
        "modules_examined": len(modules),
        "findings": findings,
        "verdict": "speculative-seams" if findings else "no-single-consumer-modules",
    }


def _looks_like_a_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return (stem.startswith("test_") or stem.endswith("_test")
            or stem.endswith(".test") or stem.endswith(".spec")
            or "tests/" in path or "/test/" in path or path.startswith("test/"))


def unfollowed_dependents(atlas: "Atlas", changed: Iterable[str],
                          depth: int = 1) -> dict[str, Any]:
    """What depended on this change and was not itself touched.

    `affected` already answers "what breaks if this changes". Nothing consumed
    that answer, so it stayed a query somebody had to think to run - and the
    moment worth running it is exactly the moment nobody is thinking about it.
    This turns it around: given what actually changed, what else was in the
    blast radius and left alone.

    Findings, never closures - the contract requests and obligations keep. A
    dependent reported here is not thereby wrong: it may need updating, or it
    may be genuinely unaffected, and only a person can say which. What must not
    happen is nobody saying either, because that is the case that ships broken.

    Depth 1 by default. A second hop is real but weaker, and a report that
    lists a third of the repository is one nobody reads.
    """
    changed_paths = [str(path).replace("\\", "/") for path in changed]
    if not changed_paths:
        return {"changed": [], "dependents_seen": 0, "findings": [],
                "verdict": "nothing-changed"}

    changed_keys = {module_key(path) for path in changed_paths}
    findings: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    dependents_seen = 0

    for path in changed_paths:
        for entry in atlas.affected(path, depth=depth)["dependents"]:
            dependents_seen += 1
            # `affected` answers in symbol ids (`login.py::<module>`). The
            # question here is which *file* was left alone, so the symbol is
            # dropped - and dropping it is also what collapses six symbols in
            # one untouched file into one finding rather than six.
            dependent = str(entry["id"]).replace("\\", "/").split("::")[0]
            # A file that was itself changed was dealt with; reporting it
            # anyway trains the reader to skim the ones that were not.
            if module_key(dependent) in changed_keys:
                continue
            if (dependent, path) in seen_pairs:
                continue
            seen_pairs.add((dependent, path))
            # Bucketed, because a test covering the changed code and a module
            # calling it need different things done to them, and one flat list
            # hides which is which.
            relations = [str(kind) for kind in entry.get("relations", ())]
            bucket = next((_RELATION_BUCKET.get(kind, kind) for kind in relations),
                          "callers")
            # A test file that imports the changed module records an IMPORTS
            # edge like any other caller, so the graph alone buckets it as one.
            # The distinction matters to the reader - a stale test and a stale
            # caller need different work - so the name is used to correct it.
            # This is a heuristic in a *report*, never in a refusal: it can be
            # wrong here at the cost of one mislabelled line, where the same
            # guess inside a gate would be a scope that moves on its own.
            if bucket == "callers" and _looks_like_a_test(dependent):
                bucket = "tests"
            findings.append({
                "dependent": dependent,
                "because_of": path,
                "relation": bucket,
                "distance": int(entry.get("distance", 1)),
                "question": f"'{path}' changed and '{dependent}' depends on it - was it "
                            "updated, or is there a reason it did not need to be?",
            })

    findings.sort(key=lambda f: (f["distance"], f["relation"], f["dependent"]))
    return {
        "changed": changed_paths,
        # Stated so an empty report cannot be read as "nothing was examined".
        "dependents_seen": dependents_seen,
        "findings": findings,
        "verdict": "unfollowed-dependents" if findings else "closure-complete",
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
            # The imported NAMES are references too. Without them every function
            # consumed cross-module reads as an orphan, which once made the
            # orphan report 57% noise - worse than no report.
            for alias in node.names:
                if alias.name != "*":
                    edges.append(Edge(
                        f"{path}::<module>",
                        f"{node.module.split('.')[-1]}::{alias.name}",
                        IMPORTS, EXTRACTED, node.lineno,
                    ))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name and name in defined:
                edges.append(Edge(f"{path}::<module>", defined[name], CALLS, EXTRACTED, node.lineno))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in defined:
            # A function passed as a value (a handler, a callback, a registry
            # entry) is referenced without being called; missing these once made
            # every CLI handler read as dead code.
            edges.append(Edge(f"{path}::<module>", defined[node.id], CALLS, EXTRACTED, node.lineno))
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


# Suffix -> extractor. Only Python has a stdlib parser, so it is the only entry
# by default; every other CODE_SUFFIXES entry falls back to `_generic_symbols`.
# The registry exists so a third language is one `register_extractor` call, not
# an edit to `build()` — dispatch hardcoded in core is how language support
# quietly becomes a fork.
EXTRACTORS: dict[str, Callable[[str, str], tuple[list[Symbol], list[Edge]]]] = {
    ".py": _python_symbols,
}


def register_extractor(suffix: str,
                       extractor: Callable[[str, str], tuple[list[Symbol], list[Edge]]]) -> None:
    """Route files with `suffix` through `extractor` on the next build.

    Registration also makes the suffix eligible for scanning, so a language
    outside CODE_SUFFIXES becomes visible with this one call and no core edit.
    """
    if not suffix.startswith("."):
        raise GodmodeError(f"Extractor suffix must start with '.', got {suffix!r}")
    EXTRACTORS[suffix.lower()] = extractor


def _is_test_path(path: str) -> bool:
    """Whether a relative posix path looks like a test file.

    A test's import is not a runtime dependency but a coverage promise; telling
    the two apart is what lets `affected` answer "what covers this" honestly.
    """
    parts = path.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


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
    # Registered suffixes are scanned even outside CODE_SUFFIXES: a registration
    # that still needed a constants edit would defeat the registry's purpose.
    allowed = set(suffixes) if suffixes else set(CODE_SUFFIXES) | set(EXTRACTORS)
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
        extractor = EXTRACTORS.get(path.suffix.lower(), _generic_symbols)
        try:
            symbols, edges = extractor(relative, text)
        except SyntaxError as exc:
            atlas.unparsed.append({"path": relative, "reason": f"syntax error line {exc.lineno}"})
            continue
        if _is_test_path(relative):
            # The import stays (it is a real import) and gains a coverage twin,
            # so evidence tiers and dependent counts are unchanged while the
            # tests bucket becomes answerable.
            edges = list(edges) + [
                Edge(e.source, e.target, TESTED_BY, e.evidence, e.line)
                for e in edges if e.relation == IMPORTS
            ]
        atlas.symbols.extend(symbols)
        atlas.edges.extend(edges)
        # Approximate bodies: a symbol runs from its line to the next symbol's.
        lines = text.splitlines()
        ordered = sorted((s for s in symbols if s.kind in ("function", "class")),
                         key=lambda s: s.line)
        for position, symbol in enumerate(ordered):
            end = ordered[position + 1].line - 1 if position + 1 < len(ordered) else len(lines)
            body = " ".join(
                stripped for raw in lines[symbol.line:end]
                if (stripped := raw.strip()) and not stripped.startswith(("#", "//"))
            )
            if len(body) >= 40:
                atlas.body_signatures[symbol.id] = _shingles(body)
    _link_documentation(project, atlas)
    return atlas


def _link_documentation(project: Path, atlas: Atlas) -> None:
    """Connect markdown files to the modules they mention.

    Documentation is part of a change's blast radius: a rename that leaves the
    README describing the old name ships a lie. A stem match in prose is still a
    name match, so these edges are INFERRED — leads to check, never facts — and
    the markdown files are not added to `atlas.files`, because a doc scan must
    not change what the atlas claims to have parsed.
    """
    # Very short stems ("a", "io") match prose constantly and would drown real
    # documentation links in noise.
    stems = {stem: name for name in atlas.files
             if len(stem := module_key(name)) >= 3}
    if not stems:
        return
    for doc_path in sorted(project.rglob("*.md")):
        if not doc_path.is_file():
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in doc_path.parts):
            continue
        doc_relative = doc_path.relative_to(project).as_posix()
        try:
            doc_text = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for stem, module_file in sorted(stems.items()):
            if module_key(doc_relative) == stem:
                continue
            match = re.search(rf"\b{re.escape(stem)}\b", doc_text)
            if match:
                line = doc_text.count("\n", 0, match.start()) + 1
                atlas.edges.append(
                    Edge(doc_relative, f"{module_file}::<module>", DOCUMENTS, INFERRED, line))


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def save_index(atlas: Atlas, destination: Path) -> dict[str, Any]:
    """Persist the atlas as JSON with per-file content hashes.

    An atlas rebuilt on every question re-reads the world; a persisted one
    answers instantly but can lie about a world that moved on. Content hashes
    are stored so a later load can say exactly which answers are still safe —
    from bytes, not timestamps, because clocks drift across machines and
    checkouts while content does not.
    """
    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": atlas.project.as_posix(),
        "files": {name: _file_sha256(atlas.project / name) for name in atlas.files},
        "symbols": [symbol.view() for symbol in atlas.symbols],
        "edges": [edge.view() for edge in atlas.edges],
        "unparsed": atlas.unparsed,
    }
    try:
        # sort_keys makes the output deterministic, so two saves of the same
        # atlas are byte-identical (bar built_at) and diff cleanly.
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True),
                               encoding="utf-8")
    except OSError as exc:
        raise GodmodeError(f"Cannot write index {destination}: {exc}") from exc
    return {
        "path": str(destination),
        "built_at": payload["built_at"],
        "files": len(atlas.files),
        "symbols": len(atlas.symbols),
        "edges": len(atlas.edges),
    }


def load_index(path: Path, project: Path) -> dict[str, Any]:
    """Load a saved index and report which of its claims are still safe.

    The index is not blindly trusted: every stored hash is compared against the
    file on disk now, so the caller learns what is fresh, what changed, and what
    vanished — and gets a confidence number instead of a stale map that reads
    as current.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GodmodeError(f"Cannot read index {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GodmodeError(f"Index {path} is not valid JSON: {exc}") from exc
    fresh: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    stored = data.get("files", {})
    for name in sorted(stored):
        current = project / name
        if not current.is_file():
            missing.append(name)
        elif stored[name] is not None and _file_sha256(current) == stored[name]:
            fresh.append(name)
        else:
            # A null stored hash means the file was unreadable at save time; a
            # claim that could not be pinned to content is treated as stale.
            stale.append(name)
    total = len(stored)
    return {
        "atlas": {
            "built_at": data.get("built_at"),
            "project": data.get("project"),
            "files": total,
            "symbols": len(data.get("symbols", [])),
            "edges": len(data.get("edges", [])),
            "unparsed": len(data.get("unparsed", [])),
        },
        "fresh": fresh,
        "stale": stale,
        "missing": missing,
        "confidence": round(len(fresh) / total, 2) if total else 0.0,
    }


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

        # A new language is one registration away, never a core edit.
        (project / "spec.xyz").write_text("anything\n", encoding="utf-8")
        register_extractor(".xyz", lambda path, text: (
            [Symbol(name="from_xyz", kind="function", path=path, line=1)], []))
        try:
            assert "from_xyz" in {s.name for s in build(project).symbols}
        finally:
            EXTRACTORS.pop(".xyz", None)

        # A test import and a README mention land in their own buckets, so a
        # doc mention is never mistaken for a caller.
        (project / "test_core.py").write_text("import core\n", encoding="utf-8")
        (project / "README.md").write_text("The core module rotates tokens.\n",
                                           encoding="utf-8")
        scoped = build(project).affected("core", evidence=None)
        assert any("test_core.py" in d["id"] for d in scoped["tests"]), scoped
        assert any("README.md" in d["id"] for d in scoped["docs"]), scoped
        only_docs = build(project).affected("core", evidence=None,
                                            relations={DOCUMENTS})
        assert only_docs["docs"] and not only_docs["callers"], only_docs

        # A saved index reports staleness from content hashes, not clocks.
        index_path = project / "atlas-index.json"
        save_index(build(project), index_path)
        assert load_index(index_path, project)["confidence"] == 1.0
        (project / "core.py").write_text("def rotate_token():\n    return 9\n",
                                         encoding="utf-8")
        moved = load_index(index_path, project)
        assert "core.py" in moved["stale"] and moved["confidence"] < 1.0, moved

    print("godmode_atlas self-check OK")


if __name__ == "__main__":
    _self_check()
