"""Parity governance: turn "how do we compare" into decisions, not feelings.

A file-count diff answers whether two trees differ; it never answers what to do
about it, so every gap becomes a debate. The matrix here compares eleven
capability-level dimensions - what each tree can do (public symbols via the
atlas), how it is shaped, and what is wired versus merely present - and attaches
one of five verdicts (ADOPT, EXTEND, DIVERGE-DELIBERATELY, REJECT, ALIGNED) with
a one-line reason. The verdict-and-reason pair IS the decision, made once in
code instead of per-gap in conversation, and it is conservative by construction:
a reference-ahead gap names its adopt candidates, a project-ahead gap lists the
local extensions to keep (never "ignore"), and a sensitive surface never
auto-resolves. Two rules temper adoption further. Recorded invariants are a
floor: an ADOPT whose paths overlap a protected local fix flips to REJECT,
because parity must never regress a deliberate repair. And a matrix is
"accepted" only when every open recommendation has been settled or waived in
writing, so a half-read comparison cannot pass for a reviewed one. The same
discipline covers two adjacent lies: a synced file is not an absorbed capability
until something reads it and something guards it (a copy with no reader and no
guard is just weight), and a schema proposal is not a new table until the rungs
below it - an existing column, an existing table - have been exhausted and a
reviewer has said so in writing. All comparison is against an explicit local
directory; a reference reached over the network is refused outright.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .godmode_atlas import Atlas, build as build_atlas
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError, IdentityError
from .godmode_lens import collect_inventory

_STALE_AFTER_DAYS = 30
_PATH_SAMPLE = 20
# Reasons are one line and must stay readable; name a few items, count the rest.
_NAME_SAMPLE = 5

ADOPT = "ADOPT"
EXTEND = "EXTEND"
DIVERGE = "DIVERGE-DELIBERATELY"
REJECT = "REJECT"
ALIGNED = "ALIGNED"

# Mismatches on these surfaces are never auto-adopted or listed for extension:
# a licence or a security posture that disagrees needs a human eye, so the
# verdict demands a deliberate, waived decision instead of recommending motion.
_SENSITIVE_DIMENSIONS = frozenset({"licence", "security-docs"})

# The E-14 floor's fixed sentence: adopting over a recorded local fix would
# regress it, so the flip carries the same words everywhere it happens.
_FLOOR_REASON = "protected local fix; parity is a floor, not a ceiling"

# Verdicts that need no further human word before a matrix counts as accepted:
# ALIGNED has no gap and REJECT is already backed by a recorded invariant.
# ADOPT, EXTEND, and DIVERGE-DELIBERATELY are open until waived with a reason.
_SETTLED_VERDICTS = frozenset({ALIGNED, REJECT})

_CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"})
_DEPENDENCY_NAMES = frozenset({
    "package.json", "package-lock.json", "pyproject.toml", "pipfile", "pipfile.lock",
    "setup.cfg", "environment.yml", "cargo.toml", "go.mod", "gemfile", "gemfile.lock",
})


def _is_test(path: str, name: str) -> bool:
    first = path.split("/", 1)[0]
    return "test" in name or "spec" in name or first in ("test", "tests")


def _is_licence(name: str) -> bool:
    stem = name.split(".", 1)[0]
    return stem in ("license", "licence", "copying", "notice")


def _surface_paths(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    surfaces: dict[str, list[str]] = {name: [] for name in (
        "tests", "documentation", "configuration", "dependency-declarations",
        "licence", "security-docs",
    )}
    for entry in entries:
        path = entry["path"]
        lowered = path.lower()
        name = Path(lowered).name
        suffix = Path(name).suffix
        if _is_test(lowered, name):
            surfaces["tests"].append(path)
        if suffix in (".md", ".rst"):
            surfaces["documentation"].append(path)
        if suffix in _CONFIG_SUFFIXES:
            surfaces["configuration"].append(path)
        if name in _DEPENDENCY_NAMES or name.startswith("requirements"):
            surfaces["dependency-declarations"].append(path)
        if _is_licence(name):
            surfaces["licence"].append(path)
        if name.startswith("security") or name.startswith("threat"):
            surfaces["security-docs"].append(path)
    return surfaces


def _sample(names: list[str]) -> str:
    shown = ", ".join(names[:_NAME_SAMPLE])
    remainder = len(names) - _NAME_SAMPLE
    return shown + (f" (+{remainder} more)" if remainder > 0 else "")


def _decide(name: str, project_only: list[str], reference_only: list[str],
            unit: str) -> tuple[str, str]:
    # This mapping is the decision matrix: gap in, verdict and obligation out.
    # It is deliberately conservative: a mixed gap still says ADOPT (the
    # reference-ahead half must be considered), and project-ahead is never a
    # licence to ignore - the extensions are named so they get kept on purpose.
    if not project_only and not reference_only:
        return ALIGNED, f"no gap: both trees present the same {unit}"
    if name in _SENSITIVE_DIMENSIONS:
        return DIVERGE, ("sensitive surface differs; never auto-adopted - "
                         "resolve it deliberately and waive with the recorded decision")
    if reference_only:
        reason = f"reference-ahead: adopt candidates {_sample(reference_only)}"
        if project_only:
            reason += f"; local extensions kept in view: {_sample(project_only)}"
        return ADOPT, reason
    return EXTEND, (f"project-ahead: local extensions {_sample(project_only)} stay; "
                    "upstream or document them, never ignore them")


def _set_dimension(name: str, project_items: set[str], reference_items: set[str],
                   *, unit: str, project_paths: set[str] | None = None,
                   reference_paths: set[str] | None = None) -> dict[str, Any]:
    project_only = sorted(project_items - reference_items)
    reference_only = sorted(reference_items - project_items)
    verdict, reason = _decide(name, project_only, reference_only, unit)
    return {
        "verdict": verdict,
        "reason": reason,
        "present_in_project": len(project_items),
        "present_in_reference": len(reference_items),
        "delta": len(project_items) - len(reference_items),
        "shared": sorted(project_items & reference_items)[:_PATH_SAMPLE],
        "project_only": project_only[:_PATH_SAMPLE],
        "reference_only": reference_only[:_PATH_SAMPLE],
        "adopt_candidates": reference_only[:_PATH_SAMPLE],
        "local_extensions": project_only[:_PATH_SAMPLE],
        # The path universe the E-14 floor checks invariants against; for
        # symbol dimensions these are defining files, not the symbol names.
        "project_paths": sorted(project_paths if project_paths is not None
                                else project_items)[:_PATH_SAMPLE],
        "reference_paths": sorted(reference_paths if reference_paths is not None
                                  else reference_items)[:_PATH_SAMPLE],
    }


def _public_symbols(atlas: Atlas) -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for symbol in atlas.symbols:
        if symbol.kind in ("function", "class") and not symbol.name.startswith("_"):
            names.setdefault(symbol.name, set()).add(symbol.path)
    return names


def _capability_dimension(project_atlas: Atlas, reference_atlas: Atlas) -> dict[str, Any]:
    project = _public_symbols(project_atlas)
    reference = _public_symbols(reference_atlas)
    return _set_dimension(
        "capability", set(project), set(reference), unit="public symbols",
        project_paths={path for paths in project.values() for path in paths},
        reference_paths={path for paths in reference.values() for path in paths},
    )


def _wiring(atlas: Atlas) -> tuple[float, list[dict[str, Any]], int]:
    named = [symbol for symbol in atlas.symbols
             if symbol.kind in ("function", "class") and not symbol.name.startswith("_")]
    orphans = atlas.orphans() if named else []
    ratio = round(len(orphans) / len(named), 3) if named else 0.0
    return ratio, orphans, len(named)


def _wiring_dimension(project_atlas: Atlas, reference_atlas: Atlas) -> dict[str, Any]:
    # Presence is not wiring: a tree can hold every capability and reach none
    # of it. Comparing orphan ratios says whose shipped code is actually used.
    project_ratio, project_orphans, project_named = _wiring(project_atlas)
    reference_ratio, reference_orphans, reference_named = _wiring(reference_atlas)
    orphan_names = sorted({orphan["name"] for orphan in project_orphans})
    if project_ratio == reference_ratio:
        verdict, reason = ALIGNED, (
            f"orphan ratios match ({project_ratio}); presence and wiring track together")
        candidates: list[str] = []
    elif project_ratio > reference_ratio:
        verdict, reason = ADOPT, (
            f"reference wires more of what it ships (orphan ratio {project_ratio} vs "
            f"{reference_ratio}); wire local orphans first: {_sample(orphan_names)}")
        candidates = orphan_names[:_PATH_SAMPLE]
    else:
        verdict, reason = EXTEND, (
            f"project wiring is tighter (orphan ratio {project_ratio} vs "
            f"{reference_ratio}); keep the discipline, never ignore it")
        candidates = []
    return {
        "verdict": verdict,
        "reason": reason,
        "present_in_project": project_named,
        "present_in_reference": reference_named,
        "delta": project_named - reference_named,
        "project_ratio": project_ratio,
        "reference_ratio": reference_ratio,
        "adopt_candidates": candidates,
        "local_extensions": [],
        "project_paths": sorted({orphan["path"] for orphan in project_orphans})[:_PATH_SAMPLE],
        "reference_paths": sorted({orphan["path"] for orphan in reference_orphans})[:_PATH_SAMPLE],
    }


def _top_level(entries: list[dict[str, Any]]) -> set[str]:
    return {entry["path"].split("/", 1)[0] for entry in entries if "/" in entry["path"]}


def _newest_mtime_ns(entries: list[dict[str, Any]]) -> int | None:
    stamps = [entry["mtime_ns"] for entry in entries if entry.get("mtime_ns")]
    return max(stamps) if stamps else None


def _freshness_dimension(project_entries: list[dict[str, Any]],
                         reference_entries: list[dict[str, Any]]) -> dict[str, Any]:
    # A reference that stopped moving long before the project did makes the
    # project look ahead on every dimension; judge the comparison itself so no
    # single verdict quietly flatters the project.
    project_newest = _newest_mtime_ns(project_entries)
    reference_newest = _newest_mtime_ns(reference_entries)
    behind_days: int | None = None
    verdict, reason = ALIGNED, "reference and project last moved within the staleness window"
    if project_newest is None or reference_newest is None:
        reason = "timestamps unavailable on one side; freshness cannot be judged"
    else:
        behind_days = (project_newest - reference_newest) // (86_400 * 1_000_000_000)
        if behind_days > _STALE_AFTER_DAYS:
            verdict = DIVERGE
            reason = (f"reference is {behind_days} days behind the project; "
                      "reference-ahead verdicts flatter the project until it is refreshed")
    return {
        "verdict": verdict,
        "reason": reason,
        "present_in_project": 1 if project_newest is not None else 0,
        "present_in_reference": 1 if reference_newest is not None else 0,
        "delta": (1 if project_newest is not None else 0)
        - (1 if reference_newest is not None else 0),
        "behind_days": behind_days,
        "adopt_candidates": [],
        "local_extensions": [],
        "project_paths": [],
        "reference_paths": [],
    }


def _protected_invariant_paths(archive: Chronicle) -> set[str]:
    protected: set[str] = set()
    for record in archive.select(kind="invariant", limit=500):
        for evidence in record.get("evidence") or []:
            if evidence.startswith("file:"):
                protected.add(_normalise(evidence[len("file:"):].split("#")[0]))
    return protected


def _invariants_dimension(archive: Chronicle | None, project_paths: set[str],
                          reference_paths: set[str]) -> dict[str, Any]:
    # Invariant records citing files that exist only locally are the recorded
    # shape of deliberate divergence: the fixes parity must never erase.
    if archive is None:
        protected_local: list[str] = []
        verdict, reason = ALIGNED, "no archive supplied; the invariant floor was not evaluated"
    else:
        protected_local = sorted(
            path for path in _protected_invariant_paths(archive)
            if path in project_paths and path not in reference_paths
        )
        if protected_local:
            verdict, reason = DIVERGE, (
                f"invariant-protected paths exist only locally: {_sample(protected_local)}; "
                "parity is a floor, not a ceiling")
        else:
            verdict, reason = ALIGNED, "no invariant-protected path is local-only"
    return {
        "verdict": verdict,
        "reason": reason,
        "present_in_project": len(protected_local),
        "present_in_reference": 0,
        "delta": len(protected_local),
        "protected_paths": protected_local[:_PATH_SAMPLE],
        "adopt_candidates": [],
        "local_extensions": protected_local[:_PATH_SAMPLE],
        "project_paths": protected_local[:_PATH_SAMPLE],
        "reference_paths": [],
    }


def _accepted(matrix: dict[str, Any]) -> bool:
    return all(
        dimension["verdict"] in _SETTLED_VERDICTS or "waived" in dimension
        for dimension in matrix["dimensions"].values()
    )


def parity_matrix(project: str | Path, reference: str | Path,
                  archive: Chronicle | None = None) -> dict[str, Any]:
    """Compare two local trees across eleven capability-level dimensions.

    Every dimension carries a verdict from {ADOPT, EXTEND, DIVERGE-DELIBERATELY,
    REJECT, ALIGNED} plus a one-line reason, because a delta without an
    obligation is just a debate scheduled for later. When an archive is passed,
    recorded invariants become the E-14 floor: ADOPT recommendations whose paths
    overlap a protected local fix flip to REJECT. Returns the full matrix, an
    overall "aligned" flag, and an "accepted" flag that stays False while any
    open recommendation lacks a waiver. Nothing is copied and nothing fetched.
    """
    for candidate in (project, reference):
        if "://" in str(candidate):
            raise IdentityError(
                "Parity accepts an explicit local directory only; network retrieval is disabled"
            )
    project_path = Path(project)
    reference_path = Path(reference)
    if not project_path.is_dir():
        raise IdentityError("Parity project directory does not exist")
    if not reference_path.is_dir():
        raise IdentityError("Local parity reference does not exist")

    project_inventory = collect_inventory(project_path)
    reference_inventory = collect_inventory(reference_path)
    project_atlas = build_atlas(project_path)
    reference_atlas = build_atlas(reference_path)
    project_files = {entry["path"] for entry in project_inventory["entries"]}
    reference_files = {entry["path"] for entry in reference_inventory["entries"]}

    dimensions: dict[str, dict[str, Any]] = {}
    dimensions["capability"] = _capability_dimension(project_atlas, reference_atlas)
    dimensions["architecture"] = _set_dimension(
        "architecture",
        _top_level(project_inventory["entries"]),
        _top_level(reference_inventory["entries"]),
        unit="top-level directories",
    )
    dimensions["runtime-wiring"] = _wiring_dimension(project_atlas, reference_atlas)
    project_surfaces = _surface_paths(project_inventory["entries"])
    reference_surfaces = _surface_paths(reference_inventory["entries"])
    for name in project_surfaces:
        dimensions[name] = _set_dimension(
            name, set(project_surfaces[name]), set(reference_surfaces[name]), unit="paths",
        )
    dimensions["identity-freshness"] = _freshness_dimension(
        project_inventory["entries"], reference_inventory["entries"],
    )
    dimensions["project-invariants"] = _invariants_dimension(
        archive, project_files, reference_files,
    )

    result: dict[str, Any] = {
        "dimensions": dimensions,
        "aligned": all(entry["verdict"] == ALIGNED for entry in dimensions.values()),
        "content_copied": False,
        "network_used": False,
    }
    behind_days = dimensions["identity-freshness"].get("behind_days")
    if behind_days is not None and behind_days > _STALE_AFTER_DAYS:
        result["reference_staleness"] = f"stale ({behind_days} days behind)"
    result["accepted"] = _accepted(result)
    if archive is not None:
        floor = adoption_floor(archive, result)
        result["floor"] = {"protected_paths": floor["protected_paths"],
                           "flipped": floor["flipped"]}
    return result


def adoption_floor(archive: Chronicle, matrix: dict[str, Any]) -> dict[str, Any]:
    """E-14: flip any ADOPT that would overwrite a protected local fix to REJECT.

    An invariant record citing a file is a promise that the condition it fixed
    must not recur; adopting reference content over that path would break the
    promise silently. The flip is mechanical and its reason is fixed, so the
    protection cannot be argued away one gap at a time. Mutates the matrix in
    place and returns the report of what was protected and what flipped.
    """
    protected = _protected_invariant_paths(archive)
    flipped: dict[str, list[str]] = {}
    for name, dimension in matrix["dimensions"].items():
        if dimension.get("verdict") != ADOPT:
            continue
        universe = set(dimension.get("project_paths") or [])
        universe |= set(dimension.get("reference_paths") or [])
        overlap = sorted(universe & protected)
        if overlap:
            dimension["verdict"] = REJECT
            dimension["reason"] = _FLOOR_REASON
            dimension["floor_overlap"] = overlap
            flipped[name] = overlap
    matrix["accepted"] = _accepted(matrix)
    return {"protected_paths": sorted(protected), "flipped": flipped,
            "accepted": matrix["accepted"]}


def waive(matrix: dict[str, Any], dimension: str, reason: str) -> dict[str, Any]:
    """Record that a human accepted a dimension's gap, in writing.

    A waiver is the only way an open recommendation (ADOPT, EXTEND, or
    DIVERGE-DELIBERATELY) stops blocking acceptance, and it must carry a
    non-empty reason - a silent waiver is indistinguishable from never having
    looked. Mutates the matrix in place and returns it.
    """
    cleaned = str(reason or "").strip()
    if not cleaned:
        raise ArchiveError("A parity waiver requires a non-empty reason")
    dimensions = matrix.get("dimensions") or {}
    if dimension not in dimensions:
        raise ArchiveError(f"Unknown parity dimension: {dimension}")
    dimensions[dimension]["waived"] = {"reason": cleaned}
    matrix["accepted"] = _accepted(matrix)
    return matrix


def _normalise(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _cites_file(record: dict[str, Any], path: str) -> bool:
    for evidence in record.get("evidence") or []:
        if evidence.startswith("file:") and _normalise(evidence[len("file:"):].split("#")[0]) == path:
            return True
    return False


def absorption_check(archive: Chronicle, path: str) -> dict[str, Any]:
    """Decide whether a synced file has actually been absorbed.

    Absorption needs two independent witnesses: a reader (a non-guard
    attestation or change record citing the file, proving something consumes
    it) and a guard (a `guard:` attestation that ran against it, proving
    something would notice if it rotted). One witness alone is unwired
    absorption and is rejected.
    """
    target = _normalise(path)
    reader: str | None = None
    guard: str | None = None
    for record in archive.select(limit=500):
        if record["kind"] not in ("attestation", "change") or not _cites_file(record, target):
            continue
        if record["subject"].startswith("guard:"):
            if record["kind"] == "attestation" and record["data"].get("status") == "ran":
                guard = f"seq:{record['sequence']}"
        else:
            reader = f"seq:{record['sequence']}"
    missing = [role for role, found in (("reader", reader), ("guard", guard)) if found is None]
    return {
        "path": target,
        "reader": reader,
        "guard": guard,
        "absorbed": not missing,
        "missing": missing,
    }


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    pieces = set()
    for token in re.split(r"[^a-z0-9]+", text.lower()):
        if not token:
            continue
        pieces.add(token)
        # Naive singularisation so "orders" meets "order_items" on equal terms.
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            pieces.add(token[:-1])
    return pieces


def schema_ladder(archive: Chronicle, proposal: dict[str, Any]) -> dict[str, Any]:
    """Walk a schema change down the ladder: column, then table, then review.

    Rung 1 reuses an existing column, rung 2 extends an existing table, and
    only when neither name-matches does rung 3 (a new table) open - and that
    rung stays shut without a non-empty reviewer note. Matching is plain token
    overlap on names, so the outcome is deterministic and arguable in text.
    """
    change = str(proposal.get("change") or "").strip()
    if not change:
        raise ArchiveError("A schema proposal requires a non-empty change description")
    existing_tables = list(proposal.get("existing_tables") or [])
    existing_columns = dict(proposal.get("existing_columns") or {})
    proposed_table = proposal.get("proposed_table")
    proposed_column = proposal.get("proposed_column")
    review = str(proposal.get("review") or "").strip()

    outcome: dict[str, Any] | None = None

    # Rung 1: an existing column already fits the proposed one.
    column_tokens = _tokens(proposed_column)
    if column_tokens:
        for table in sorted(existing_columns):
            for column in existing_columns[table]:
                if _tokens(column) & column_tokens:
                    outcome = {
                        "rung": 1,
                        "decision": f"use existing column {table}.{column}",
                        "requires_review": False,
                        "approved": True,
                        "reason": (
                            f"proposed column '{proposed_column}' name-matches "
                            f"{table}.{column}; store the data there"
                        ),
                    }
                    break
            if outcome:
                break

    # Rung 2: an existing table can take the new column.
    if outcome is None:
        candidates = list(dict.fromkeys(list(existing_tables) + sorted(existing_columns)))
        table_tokens = _tokens(proposed_table) | _tokens(change)
        for table in candidates:
            if _tokens(table) & table_tokens:
                addition = f" with new column '{proposed_column}'" if proposed_column else ""
                outcome = {
                    "rung": 2,
                    "decision": f"extend existing table {table}{addition}",
                    "requires_review": False,
                    "approved": True,
                    "reason": (
                        f"existing table '{table}' name-matches the proposal; "
                        "extend it rather than create a sibling"
                    ),
                }
                break

    # Rung 3: a genuinely new table, and only with a reviewer's written note.
    if outcome is None:
        label = proposed_table or "<unnamed>"
        approved = bool(review)
        outcome = {
            "rung": 3,
            "decision": (
                f"create new table {label}" if approved
                else f"refused new table {label}"
            ),
            "requires_review": True,
            "approved": approved,
            "reason": (
                f"no existing column or table fits; reviewer note: {review}" if approved
                else "no existing surface fits, but a new table requires a "
                     "non-empty reviewer note in proposal['review']"
            ),
        }

    archive.append(
        "database",
        f"schema-ladder:{change[:100]}",
        {
            "rung": outcome["rung"],
            "decision": outcome["decision"],
            "approved": outcome["approved"],
            "requires_review": outcome["requires_review"],
            "status": "approved" if outcome["approved"] else "refused",
        },
    )
    return outcome
