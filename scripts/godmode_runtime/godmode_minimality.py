"""Minimality report: one ranked view over surfaces that already measure it.

Aggregation only - no new analysis, with one exception noted below. Four
checks each answer a narrow question (are there two of this? is anything
unreached? does a module serve only one caller? has a charter rule gone
dormant?) and nobody read all four together, so the ranked-by-count view
they deserved never got built until now.

**`duplicate-authority` (GAP-2) is new analysis, deliberately reusing old
machinery.** `atlas.duplicates()` already finds one capability implemented
twice under two names, by Jaccard similarity over name-shingles and
body-shingles (C-17). Nothing measured the adjacent case: two *data*
literals - a string-list constant, an enum-like dict, a version pin -
independently asserting the same fact and free to drift because nothing
forces them to agree. This module extracts small literal collections
(module-level list/set/tuple/dict-key literals, and name-hinted version
string constants) via `ast`, then hands their *member sets* to the exact
same `_jaccard()` this file already imports from `godmode_atlas` for
`duplicates()` - the near-dup signature machinery is reused, not rebuilt;
only what gets fingerprinted (a set of literal values instead of a set of
name/body shingles) is new.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
from typing import Any

from .godmode_atlas import _is_test_path, _jaccard, build as build_atlas, speculative_seams
from .godmode_attest import advisory_decay
from .godmode_census import census
from .godmode_charter import compile_charter
from .godmode_constants import IGNORED_DIRECTORY_NAMES
from .godmode_errors import GodmodeError


def minimality_report(project: Path, archive: Any = None,
                      duplicate_authority_threshold: float = 0.6) -> dict[str, Any]:
    """Rank existing minimality-pressure surfaces into one report.

    Every count here is produced by a check that already exists and is
    tested on its own; this only sorts and totals what those checks already
    found. An archive-less or empty project reports honest zeros with the
    basis stated, never a manufactured finding.

    `duplicate_authority_threshold` (default 0.6, GAP-2) is the one tunable
    number in this report: the member-overlap fraction at which two data
    literals are "near-identical enough to be the same fact declared
    twice." Documented here rather than buried in the detector so a project
    with unusually large or small enum-like collections can adjust it
    without reading the implementation.
    """
    project = Path(project)
    atlas = build_atlas(project)
    duplicates = atlas.duplicates()
    orphans = atlas.orphans()
    seams = speculative_seams(atlas)["findings"]
    authority = duplicate_authority_findings(project, threshold=duplicate_authority_threshold)

    sections: list[dict[str, Any]] = [
        {"section": "duplicate-symbols", "count": len(duplicates), "items": duplicates[:10],
         "basis": "godmode_atlas.Atlas.duplicates (near-duplicate symbol bodies)"},
        {"section": "orphan-symbols", "count": len(orphans), "items": orphans[:10],
         "basis": "godmode_atlas.Atlas.orphans (unreached symbols)"},
        {"section": "speculative-seams", "count": len(seams), "items": seams[:10],
         "basis": "godmode_atlas.speculative_seams (single-consumer modules)"},
        {"section": "duplicate-authority", "count": len(authority["findings"]),
         "items": authority["findings"][:10],
         "basis": f"godmode_minimality.duplicate_authority_findings (near-dup data literals, "
                  f"threshold={authority['threshold']}, via godmode_atlas._jaccard)",
         "note": authority["note"]},
    ]

    unused: list[dict[str, Any]] = []
    dormant: list[dict[str, Any]] = []
    unused_basis = "no archive supplied; census not run"
    dormant_basis = "no archive supplied; advisory_decay not run"
    if archive is not None:
        try:
            unused = census(archive)["unused"]
            unused_basis = "godmode_census.census (declared surfaces never recorded here)"
        except Exception:  # noqa: BLE001 - this section degrades, never fails, the report
            unused_basis = "census could not run against this archive"
        try:
            charter = compile_charter(project)
            decay = advisory_decay(archive, charter)
            dormant = decay["dormant"]
            dormant_basis = "godmode_attest.advisory_decay (rules untouched in the recent window)"
        except GodmodeError:
            dormant_basis = "no charter compiled for this project; advisory_decay not run"

    sections.append({"section": "unexercised-surfaces", "count": len(unused), "items": unused[:10],
                     "basis": unused_basis})
    sections.append({"section": "charter-decay", "count": len(dormant), "items": dormant[:10],
                     "basis": dormant_basis})

    ranked = sorted(sections, key=lambda s: s["count"], reverse=True)
    total = sum(s["count"] for s in sections)
    return {
        "sections": ranked,
        "total_findings": total,
        "verdict": "minimal" if total == 0 else "reinvention-pressure-present",
    }


# ---- duplicate-authority (GAP-2): near-dup data literals ---------------------
#
# A small literal collection is a module-level list/set/tuple/dict-key
# literal (min 3 members - two members is nearly always a deliberate pair,
# not an enumeration someone might duplicate) or a string constant whose
# name says it pins a version. Only module-level assignments count: a
# literal built inside a function body is local state, not an authority
# another file could independently restate.
_MIN_MEMBERS = 3
_VERSION_NAME_HINT = re.compile(r"version", re.IGNORECASE)
# A numeric dotted value, gated on the name hint above so an unrelated
# string ("1.5" as some ratio, "3.10" as a Python constraint) is never
# compared against an actual version pin just because it looks numeric.
_VERSION_VALUE_SHAPE = re.compile(r"^\d+(?:\.\d+){1,3}")


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _collection_members(node: ast.AST) -> frozenset[str] | None:
    """Member set of a list/set/tuple/dict-keys literal, unwrapping a single
    `frozenset(...)`/`set(...)`/`tuple(...)`/`list(...)` call around one -
    the exact shape `EVENT_KINDS = frozenset({...})` takes. `None` when the
    node is not one of these shapes, or when any element is not a plain
    string constant (a collection of expressions is not a fact to compare)."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set", "list", "tuple") and len(node.args) == 1):
        node = node.args[0]
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        values = [_string_constant(elt) for elt in node.elts]
        if values and all(v is not None for v in values):
            return frozenset(values)
        return None
    if isinstance(node, ast.Dict) and node.keys:
        # An enum-like dict's keys are the vocabulary being asserted (the
        # MASKS / EVENT_KINDS shape); the values are per-key detail that a
        # second site restating the same vocabulary would not need to copy.
        if all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.keys):
            return frozenset(k.value for k in node.keys)  # type: ignore[union-attr]
        return None
    return None


def _literal_target(node: ast.AST) -> tuple[str, ast.AST] | None:
    """`(name, value)` of a module-level `NAME = ...` or `NAME: T = ...`, or
    `None` for every other statement shape (multi-target, tuple-unpacking,
    augmented assignment - none of these declare one named authority)."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return node.target.id, node.value
    return None


def _extract_python_literals(path: str, text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found: list[dict[str, Any]] = []
    for node in tree.body:  # module level only, see docstring above
        target = _literal_target(node)
        if target is None:
            continue
        name, value = target
        members = _collection_members(value)
        if members is not None and len(members) >= _MIN_MEMBERS:
            found.append({"name": name, "path": path, "line": node.lineno,
                         "kind": "collection", "members": members})
            continue
        text_value = _string_constant(value)
        if text_value and _VERSION_NAME_HINT.search(name) and _VERSION_VALUE_SHAPE.match(text_value):
            found.append({"name": name, "path": path, "line": node.lineno,
                         "kind": "version", "members": frozenset({text_value})})
    return found


def _extract_json_version(path: str, text: str) -> list[dict[str, Any]]:
    """A top-level `"version": "..."` field, the shape every plugin manifest
    in this repo pins its release string with."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    value = data.get("version")
    if isinstance(value, str) and _VERSION_VALUE_SHAPE.match(value):
        return [{"name": "version", "path": path, "line": 1,
                 "kind": "version", "members": frozenset({value})}]
    return []


def _walk_literals(project: Path) -> list[dict[str, Any]]:
    literals: list[dict[str, Any]] = []
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".py", ".json"):
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        relative = path.relative_to(project).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix.lower() == ".py":
            literals.extend(_extract_python_literals(relative, text))
        else:
            literals.extend(_extract_json_version(relative, text))
    return literals


def duplicate_authority_findings(project: Path, threshold: float = 0.6) -> dict[str, Any]:
    """Two or more independently-declared literals asserting the same fact.

    Reuses `godmode_atlas._jaccard` (C-17's near-dup machinery) over the
    literal's own member set - for a collection that is genuinely the same
    Jaccard formula `Atlas.duplicates()` already applies to name/body
    shingles; for a version pin (a singleton set) it collapses to "equal or
    not", which is exactly the right question for a fact that has exactly
    one correct value.

    Two exemptions, both narrow on purpose:

    * A collection pair is skipped only when it is an EXACT match (not
      merely near-dup) AND exactly one side lives under `tests/` - a
      fixture intentionally restating a source list verbatim as a
      known-good sample is the classic false positive this whole class of
      detector earns a bad reputation from. Two SOURCE sites, or a
      near-but-not-exact test/source pair (which is the shape of a fixture
      that has actually drifted from what it samples), still flag.
    * A version pair compares by name-hint first (`_VERSION_NAME_HINT`) so
      an unrelated numeric-looking string is never pulled into the
      comparison just because it parses as digits-and-dots.
    """
    project = Path(project)
    literals = _walk_literals(project)
    collections = [entry for entry in literals if entry["kind"] == "collection"]
    versions = [entry for entry in literals if entry["kind"] == "version"]

    findings: list[dict[str, Any]] = []
    for i, a in enumerate(collections):
        for b in collections[i + 1:]:
            if a["path"] == b["path"] and a["name"] == b["name"]:
                continue
            score = _jaccard(a["members"], b["members"])
            if score < threshold:
                continue
            exactly_one_is_test = _is_test_path(a["path"]) != _is_test_path(b["path"])
            if score >= 1.0 and exactly_one_is_test:
                continue
            findings.append({
                "kind": "collection",
                "a": {"name": a["name"], "path": a["path"], "line": a["line"]},
                "b": {"name": b["name"], "path": b["path"], "line": b["line"]},
                "similarity": round(score, 3),
                "shared_members": sorted(a["members"] & b["members"])[:10],
                "question": f"'{a['name']}' ({a['path']}:{a['line']}) and '{b['name']}' "
                            f"({b['path']}:{b['line']}) share {round(score * 100)}% of their "
                            "members but are not identical - one source of truth (delete the "
                            "derivable half, or funnel both through one function), or a "
                            "deliberate divergence worth a `paired-artifact` declaration "
                            "(see godmode_precheck.py)?",
            })

    for i, a in enumerate(versions):
        for b in versions[i + 1:]:
            if a["path"] == b["path"]:
                continue
            value_a, value_b = next(iter(a["members"])), next(iter(b["members"]))
            if value_a == value_b:
                continue
            findings.append({
                "kind": "version",
                "a": {"name": a["name"], "path": a["path"], "line": a["line"], "value": value_a},
                "b": {"name": b["name"], "path": b["path"], "line": b["line"], "value": value_b},
                "similarity": 0.0,
                "shared_members": [],
                "question": f"'{a['name']}' ({a['path']}:{a['line']}) pins '{value_a}' but "
                            f"'{b['name']}' ({b['path']}:{b['line']}) pins '{value_b}' for what "
                            "reads like the same released version - which one is the authority?",
            })

    findings.sort(key=lambda f: (-f["similarity"], f["a"]["path"]))
    return {
        "threshold": threshold,
        "collections_examined": len(collections),
        "version_literals_examined": len(versions),
        "findings": findings,
        # The magic-count anti-pattern the spec asks this report to name,
        # not enforce: a v1 finding-class note, no detector behind it yet.
        "note": "magic-count anti-pattern: `assert len(x) == N` looks like coverage while "
                "hiding exactly the drift this check exists to catch, because a second site "
                "that grows or shrinks with the first passes the count check either way; "
                "prefer a subset/superset assertion against the real source object instead "
                "(e.g. `assert declared <= EVENT_KINDS`, not `assert len(declared) == 27`). "
                "No code enforcement of this note in v1 - advisory only.",
        "verdict": "duplicate-authority-found" if findings else "no-drift-found",
    }
