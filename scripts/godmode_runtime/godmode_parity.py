"""Parity governance: turn "how do we compare" into decisions, not feelings.

A category-count diff answers whether two trees differ; it never answers what to
do about it, so every gap becomes a debate. The eleven-dimension matrix here
attaches a verdict and an action to each named surface - the pair IS the
decision, made once in code instead of per-gap in conversation. The same
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

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError, IdentityError
from .godmode_lens import collect_inventory

_STALE_AFTER_DAYS = 30
_PATH_SAMPLE = 20

# Mismatches on these surfaces are never silently adopted or ignored: a licence,
# a security posture, or a stated version that disagrees needs a human eye.
_SENSITIVE_DIMENSIONS = frozenset({"licence", "security-docs", "version-surfaces"})

_ENTRY_NAMES = frozenset({
    "main.py", "__main__.py", "cli.py", "app.py", "manage.py", "run.py", "setup.py",
})
_ENTRY_SUFFIXES = frozenset({".sh", ".bat", ".ps1", ".cmd"})
_CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"})
_DEPENDENCY_NAMES = frozenset({
    "package.json", "package-lock.json", "pyproject.toml", "pipfile", "pipfile.lock",
    "setup.cfg", "environment.yml", "cargo.toml", "go.mod", "gemfile", "gemfile.lock",
})
_CI_NAMES = frozenset({
    ".gitlab-ci.yml", "azure-pipelines.yml", ".travis.yml", "jenkinsfile", "appveyor.yml",
})
_VERSION_NAMES = frozenset({
    "version", "version.txt", "version.py", "_version.py", "__about__.py",
    "pyproject.toml", "package.json",
})


def _is_entry_point(path: str, name: str) -> bool:
    first = path.split("/", 1)[0]
    return (name in _ENTRY_NAMES or first in ("bin", "scripts")
            or Path(name).suffix in _ENTRY_SUFFIXES)


def _is_test(path: str, name: str) -> bool:
    first = path.split("/", 1)[0]
    return "test" in name or "spec" in name or first in ("test", "tests")


def _is_ci(path: str, name: str) -> bool:
    return (path.startswith(".github/workflows/") or path.startswith(".circleci/")
            or name in _CI_NAMES)


def _is_licence(name: str) -> bool:
    stem = name.split(".", 1)[0]
    return stem in ("license", "licence", "copying", "notice")


def _is_guidance(name: str, original_name: str) -> bool:
    original = Path(original_name)
    return (name.startswith("readme") or name.startswith("contributing")
            or name.startswith("code_of_conduct")
            or (original.suffix.lower() == ".md" and original.stem.isupper()))


def _dimension_paths(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    surfaces: dict[str, list[str]] = {name: [] for name in (
        "entry-points", "test-surface", "documentation-surface", "configuration",
        "dependency-declarations", "ci-surface", "licence", "security-docs",
        "version-surfaces", "guidance-surfaces",
    )}
    for entry in entries:
        path = entry["path"]
        lowered = path.lower()
        name = Path(lowered).name
        suffix = Path(name).suffix
        if _is_entry_point(lowered, name):
            surfaces["entry-points"].append(path)
        if _is_test(lowered, name):
            surfaces["test-surface"].append(path)
        if suffix in (".md", ".rst"):
            surfaces["documentation-surface"].append(path)
        if suffix in _CONFIG_SUFFIXES:
            surfaces["configuration"].append(path)
        if name in _DEPENDENCY_NAMES or name.startswith("requirements"):
            surfaces["dependency-declarations"].append(path)
        if _is_ci(lowered, name):
            surfaces["ci-surface"].append(path)
        if _is_licence(name):
            surfaces["licence"].append(path)
        if name.startswith("security") or name.startswith("threat"):
            surfaces["security-docs"].append(path)
        if name in _VERSION_NAMES or name.startswith("changelog"):
            surfaces["version-surfaces"].append(path)
        if _is_guidance(name, Path(path).name):
            surfaces["guidance-surfaces"].append(path)
    return surfaces


def _verdict(in_project: int, in_reference: int) -> str:
    if in_project == 0 and in_reference == 0:
        return "both-empty"
    if in_project == in_reference:
        return "aligned"
    return "project-ahead" if in_project > in_reference else "reference-ahead"


def _action(dimension: str, verdict: str) -> str:
    # This mapping is the decision matrix: verdict in, obligation out.
    if verdict in ("aligned", "both-empty"):
        return "none"
    if dimension in _SENSITIVE_DIMENSIONS:
        return "investigate"
    return "adopt" if verdict == "reference-ahead" else "ignore"


def _dimension(name: str, project_paths: list[str], reference_paths: list[str],
               **detail: Any) -> dict[str, Any]:
    in_project = len(project_paths)
    in_reference = len(reference_paths)
    verdict = _verdict(in_project, in_reference)
    return {
        "present_in_project": in_project,
        "present_in_reference": in_reference,
        "delta": in_project - in_reference,
        "verdict": verdict,
        "action": _action(name, verdict),
        "project_paths": sorted(project_paths)[:_PATH_SAMPLE],
        "reference_paths": sorted(reference_paths)[:_PATH_SAMPLE],
        **detail,
    }


def _newest_mtime_ns(entries: list[dict[str, Any]]) -> int | None:
    stamps = [entry["mtime_ns"] for entry in entries if entry.get("mtime_ns")]
    return max(stamps) if stamps else None


def parity_matrix(project: str | Path, reference: str | Path) -> dict[str, Any]:
    """Compare two local trees across eleven named dimensions.

    Returns the full matrix and an overall "aligned" flag; the caller decides
    what exit status that deserves. Nothing is copied and nothing is fetched.
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

    dimensions: dict[str, dict[str, Any]] = {}
    dimensions["file-categories"] = _dimension(
        "file-categories",
        [entry["path"] for entry in project_inventory["entries"]],
        [entry["path"] for entry in reference_inventory["entries"]],
        project_categories=project_inventory["categories"],
        reference_categories=reference_inventory["categories"],
    )
    project_surfaces = _dimension_paths(project_inventory["entries"])
    reference_surfaces = _dimension_paths(reference_inventory["entries"])
    for name in project_surfaces:
        dimensions[name] = _dimension(name, project_surfaces[name], reference_surfaces[name])

    result: dict[str, Any] = {
        "dimensions": dimensions,
        "aligned": all(
            entry["verdict"] in ("aligned", "both-empty") for entry in dimensions.values()
        ),
        "content_copied": False,
        "network_used": False,
    }
    # A reference that stopped moving long before the project did will make the
    # project look ahead on every surface; label the whole comparison instead of
    # letting each verdict quietly flatter the project.
    project_newest = _newest_mtime_ns(project_inventory["entries"])
    reference_newest = _newest_mtime_ns(reference_inventory["entries"])
    if project_newest is not None and reference_newest is not None:
        behind_days = (project_newest - reference_newest) // (86_400 * 1_000_000_000)
        if behind_days > _STALE_AFTER_DAYS:
            result["reference_staleness"] = f"stale ({behind_days} days behind)"
    return result


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
