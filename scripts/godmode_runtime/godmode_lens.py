"""On-demand repository observation and context reconstruction for Godmode."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .godmode_anchor import ProjectAnchor, anchor_fingerprint, canonical_path, run_git
from .godmode_chronicle import Chronicle
from .godmode_constants import (
    CODE_SUFFIXES,
    DATABASE_SUFFIXES,
    DEFAULT_CONTEXT_BUDGET,
    DEFAULT_RECORD_LIMIT,
    DOCUMENT_SUFFIXES,
    IGNORED_DIRECTORY_NAMES,
    MANIFEST_NAMES,
    MAX_HASH_BYTES,
)
from .godmode_errors import IdentityError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(128 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _category(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in MANIFEST_NAMES:
        return "manifest"
    if suffix in DATABASE_SUFFIXES:
        return "database"
    if "test" in name or "spec" in name:
        return "test"
    if suffix in CODE_SUFFIXES:
        return "code"
    if suffix in DOCUMENT_SUFFIXES:
        return "documentation"
    if name.startswith("dockerfile") or name.endswith((".yaml", ".yml", ".toml")):
        return "configuration"
    return "other"


def collect_inventory(project: str | Path) -> dict[str, Any]:
    root = canonical_path(Path(project))
    entries: list[dict[str, Any]] = []
    skipped = Counter()
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORY_NAMES
            and not (current_path / directory).is_symlink()
        )
        for filename in sorted(files):
            path = current_path / filename
            if path.is_symlink():
                skipped["symlink"] += 1
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
                stat = resolved.stat()
            except (OSError, ValueError):
                skipped["unreadable-or-outside-root"] += 1
                continue
            if stat.st_size > MAX_HASH_BYTES:
                skipped["oversize"] += 1
                digest = None
            else:
                try:
                    digest = _file_digest(resolved)
                except OSError:
                    skipped["unreadable"] += 1
                    continue
            entries.append(
                {
                    "path": resolved.relative_to(root).as_posix(),
                    "category": _category(resolved),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": digest,
                }
            )
    entries.sort(key=lambda item: item["path"])
    category_counts = Counter(entry["category"] for entry in entries)
    return {
        "captured_at": _utc_now(),
        "entries": entries,
        "files": len(entries),
        "categories": dict(sorted(category_counts.items())),
        "skipped": dict(sorted(skipped.items())),
    }


def observe_git(anchor: ProjectAnchor) -> dict[str, Any]:
    if not anchor.is_git:
        return {"is_git": False, "branches": [], "worktrees": [], "changes": []}
    root = Path(anchor.project_root)
    status = run_git(root, "status", "--porcelain=v1", "--untracked-files=all") or ""
    branches_raw = run_git(
        root,
        "for-each-ref",
        "--format=%(refname:short)|%(objectname)|%(upstream:short)|%(upstream:track)",
        "refs/heads",
    ) or ""
    worktrees_raw = run_git(root, "worktree", "list", "--porcelain") or ""
    branches = []
    for line in branches_raw.splitlines():
        name, commit, upstream, track = (line.split("|", 3) + ["", "", "", ""])[:4]
        branches.append(
            {"name": name, "head": commit, "upstream": upstream or None, "track": track or None}
        )
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in worktrees_raw.splitlines() + [""]:
        if not line:
            if current:
                if "worktree" in current:
                    current["worktree"] = hashlib.sha256(
                        current["worktree"].encode("utf-8")
                    ).hexdigest()[:16]
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value or True
    changes = []
    for line in status.splitlines():
        if len(line) >= 3:
            changes.append({"status": line[:2], "path": line[3:]})
    return {
        "is_git": True,
        "branch": anchor.branch,
        "head": anchor.head,
        "branches": branches,
        "worktrees": worktrees,
        "changes": changes,
    }


def make_snapshot(anchor: ProjectAnchor) -> dict[str, Any]:
    inventory = collect_inventory(anchor.project_root)
    return {
        **inventory,
        "project_key": anchor.project_key,
        "anchor_fingerprint": anchor_fingerprint(anchor),
        "branch": anchor.branch,
        "head": anchor.head,
        "git": observe_git(anchor),
    }


def inventory_diff(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    before = {entry["path"]: entry for entry in (previous or {}).get("entries", [])}
    after = {entry["path"]: entry for entry in current.get("entries", [])}
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    changed = sorted(
        path
        for path in after.keys() & before.keys()
        if after[path].get("sha256") != before[path].get("sha256")
        or after[path].get("size") != before[path].get("size")
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "clean": not (added or removed or changed),
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_context_issues(
    anchor: ProjectAnchor,
    records: list[dict[str, Any]],
    current_inventory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    inventory_records = [record for record in records if record["kind"] == "inventory"]
    latest_inventory = inventory_records[-1] if inventory_records else None
    if latest_inventory is None:
        issues.append({"code": "no-baseline", "severity": "warning", "detail": "Run inspect."})
    else:
        captured = _parse_time(latest_inventory["data"].get("captured_at"))
        if captured and (datetime.now(timezone.utc) - captured).total_seconds() > 86_400:
            issues.append(
                {"code": "stale-baseline", "severity": "warning", "detail": "Inventory is over 24 hours old."}
            )
        if latest_inventory.get("anchor_fingerprint") != anchor_fingerprint(anchor):
            issues.append(
                {"code": "identity-drift", "severity": "warning", "detail": "Branch, HEAD, worktree, or remote identity changed."}
            )
        if current_inventory is not None:
            drift = inventory_diff(latest_inventory["data"], current_inventory)
            if not drift["clean"]:
                issues.append(
                    {
                        "code": "undocumented-drift",
                        "severity": "warning",
                        "detail": f"{len(drift['added'])} added, {len(drift['changed'])} changed, {len(drift['removed'])} removed.",
                    }
                )

    existing_paths = {
        entry["path"] for entry in (current_inventory or {}).get("entries", [])
    }
    if existing_paths:
        referenced = set()
        for record in records:
            if record["kind"] == "change":
                referenced.update(record["data"].get("files", []))
        missing = sorted(path for path in referenced if path not in existing_paths)
        if missing:
            issues.append(
                {
                    "code": "phantom-reference",
                    "severity": "warning",
                    "detail": f"{len(missing)} recorded changed files no longer exist.",
                }
            )

    invariant_values: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record["kind"] == "invariant":
            invariant_values[record["subject"]].add(
                json.dumps(record["data"].get("value"), sort_keys=True)
            )
    contradictions = sorted(subject for subject, values in invariant_values.items() if len(values) > 1)
    if contradictions:
        issues.append(
            {
                "code": "contradictory-invariants",
                "severity": "error",
                "detail": f"Conflicting values for: {', '.join(contradictions[:5])}.",
            }
        )

    unproven = [
        record
        for record in records
        if record["kind"] in {"checkpoint", "checklist", "change"}
        and str(record["data"].get("status", "")).lower() in {"complete", "completed", "fixed", "done"}
        and not record.get("evidence")
    ]
    if unproven:
        issues.append(
            {
                "code": "unproven-completion",
                "severity": "error",
                "detail": f"{len(unproven)} completion claims have no evidence reference.",
            }
        )

    failed_hypotheses: Counter[str] = Counter()
    for record in records:
        outcome = str(record["data"].get("outcome", record["data"].get("status", ""))).lower()
        hypothesis = str(record["data"].get("hypothesis", "")).strip().lower()
        if hypothesis and outcome in {"failed", "failure", "did-not-work", "blocked"}:
            failed_hypotheses[hashlib.sha256(hypothesis.encode()).hexdigest()[:16]] += 1
    loops = [count for count in failed_hypotheses.values() if count >= 3]
    if loops:
        issues.append(
            {
                "code": "repeat-loop",
                "severity": "error",
                "detail": "A failed hypothesis was repeated at least three times; revisit the architecture or evidence boundary.",
            }
        )

    latest_sprint = next((record for record in reversed(records) if record["kind"] == "sprint"), None)
    if latest_sprint:
        capacity = latest_sprint["data"].get("capacity")
        obligations = latest_sprint["data"].get("obligations", [])
        if isinstance(capacity, int) and len(obligations) > capacity:
            issues.append(
                {
                    "code": "capacity-overflow",
                    "severity": "warning",
                    "detail": f"Sprint has {len(obligations)} obligations for capacity {capacity}.",
                }
            )
    return issues


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    data = record["data"]
    if record["kind"] == "inventory":
        data = {
            "captured_at": data.get("captured_at"),
            "files": data.get("files"),
            "categories": data.get("categories", {}),
        }
    return {
        "sequence": record["sequence"],
        "recorded_at": record["recorded_at"],
        "kind": record["kind"],
        "subject": record["subject"],
        "data": data,
        "evidence": record.get("evidence", []),
    }


def build_context_brief(
    anchor: ProjectAnchor,
    archive: Chronicle,
    *,
    current_inventory: dict[str, Any] | None = None,
    token_budget: int = DEFAULT_CONTEXT_BUDGET,
) -> dict[str, Any]:
    records = archive.read_events() if archive.initialized() else []
    selected: list[dict[str, Any]] = []
    priorities = (
        "invariant", "decision", "obligation", "checklist", "incident", "change",
        "checkpoint", "plan", "branch", "version", "database", "sprint", "documentation",
    )
    for kind in priorities:
        matches = [record for record in records if record["kind"] == kind]
        selected.extend(matches[-4:])
    selected = sorted({r["record_id"]: r for r in selected}.values(), key=lambda r: r["sequence"])
    selected = selected[-DEFAULT_RECORD_LIMIT:]
    brief = {
        "generated_at": _utc_now(),
        "identity": anchor.public_view(),
        "issues": detect_context_issues(anchor, records, current_inventory),
        "records": [_record_summary(record) for record in selected],
        "limits": {
            "perfect_memory": False,
            "source_code_stored": False,
            "raw_prompts_stored": False,
            "background_monitoring": False,
        },
    }
    while brief["records"]:
        estimated = max(1, len(json.dumps(brief, ensure_ascii=False)) // 4)
        if estimated <= token_budget:
            break
        brief["records"].pop(0)
    brief["estimated_tokens"] = max(1, len(json.dumps(brief, ensure_ascii=False)) // 4)
    brief["token_budget"] = token_budget
    return brief


def explain_context(anchor: ProjectAnchor, archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events() if archive.initialized() else []
    counts = Counter(record["kind"] for record in records)
    return {
        "included": {
            "current_identity": "branch, HEAD, worktree identity, and hashed remotes",
            "structured_records": dict(sorted(counts.items())),
            "priority": ["invariants", "decisions", "obligations", "open checks", "incidents", "recent changes"],
        },
        "excluded": [
            "raw prompts and conversations",
            "tool transcripts and environment dumps",
            "source-code bodies",
            "credentials and secret-shaped values",
            "network or cloud memory",
        ],
        "identity": anchor.public_view(),
    }


def compare_local_reference(project: str | Path, reference: str | Path) -> dict[str, Any]:
    if "://" in str(reference):
        raise IdentityError("Parity accepts an explicit local directory only; network retrieval is disabled")
    project_inventory = collect_inventory(project)
    reference_path = canonical_path(Path(reference))
    if not reference_path.exists() or not reference_path.is_dir():
        raise IdentityError("Local parity reference does not exist")
    reference_inventory = collect_inventory(reference_path)
    local_counts = Counter(project_inventory["categories"])
    reference_counts = Counter(reference_inventory["categories"])
    categories = sorted(set(local_counts) | set(reference_counts))
    gaps = [
        {
            "category": category,
            "project": local_counts[category],
            "reference": reference_counts[category],
            "delta": local_counts[category] - reference_counts[category],
        }
        for category in categories
        if local_counts[category] != reference_counts[category]
    ]
    local_manifests = sorted(
        Path(entry["path"]).name.lower()
        for entry in project_inventory["entries"]
        if entry["category"] == "manifest"
    )
    reference_manifests = sorted(
        Path(entry["path"]).name.lower()
        for entry in reference_inventory["entries"]
        if entry["category"] == "manifest"
    )
    return {
        "reference_digest": hashlib.sha256(str(reference_path).encode()).hexdigest(),
        "category_gaps": gaps,
        "project_manifests": local_manifests,
        "reference_manifests": reference_manifests,
        "content_copied": False,
        "network_used": False,
    }
