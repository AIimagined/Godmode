"""On-demand repository observation and context reconstruction for Godmode."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
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
    RUNTIME_VERSION,
    SETTLED_STATUSES,
)
from .godmode_errors import IdentityError

# A write lock is held for milliseconds; one that survives ten minutes marks a
# writer that died mid-write, and every later append will queue behind it.
STALE_LOCK_SECONDS = 600


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


def _resolve_git_dir(project: Path) -> Path | None:
    """The directory git actually keeps this checkout's state in.

    `.git` is usually a directory, but in a linked worktree it is a FILE whose
    single line points at the real per-worktree git dir. Reading the wrong one
    would miss every in-progress-operation marker, which is exactly the state
    this resolution exists to expose.
    """
    pointer = Path(project) / ".git"
    if pointer.is_dir():
        return pointer
    if pointer.is_file():
        try:
            text = pointer.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for line in text.splitlines():
            if line.startswith("gitdir:"):
                candidate = Path(line[len("gitdir:"):].strip())
                if not candidate.is_absolute():
                    candidate = (pointer.parent / candidate).resolve()
                return candidate if candidate.is_dir() else None
    return None


# Marker files git leaves in its state dir while an operation is unfinished.
# Presence, not content, is the signal: each exists only between the start of
# the operation and its --continue or --abort.
_OPERATION_MARKERS: tuple[tuple[str, str, bool], ...] = (
    ("MERGE_HEAD", "merging", False),
    ("rebase-merge", "rebasing", True),
    ("rebase-apply", "rebasing", True),
    ("CHERRY_PICK_HEAD", "cherry-picking", False),
    ("BISECT_LOG", "bisecting", False),
    ("REVERT_HEAD", "reverting", False),
)


def repo_state(project: Path) -> dict[str, Any]:
    """Whether the repository is mid-operation, because "dirty" hides a crisis.

    A mid-rebase or mid-merge tree shows up in porcelain status as ordinary
    dirty files, so a resuming agent would happily start substantive work on
    top of an unfinished operation and turn a recoverable state into a mess.
    The markers are read from git's own metadata rather than parsed from
    status output: the files either exist or they do not, and no localization
    or porcelain-format drift can change that.
    """
    in_progress: list[str] = []
    detached = False
    git_dir = _resolve_git_dir(Path(project))
    if git_dir is not None:
        for name, operation, wants_dir in _OPERATION_MARKERS:
            marker = git_dir / name
            present = marker.is_dir() if wants_dir else marker.is_file()
            if present and operation not in in_progress:
                in_progress.append(operation)
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            head = ""
        # A symbolic HEAD starts "ref: "; raw bytes mean a detached checkout.
        detached = bool(head) and not head.startswith("ref:")
    stash_raw = run_git(Path(project), "stash", "list")
    stash_depth = len(stash_raw.splitlines()) if stash_raw else 0
    return {
        "in_progress": in_progress,
        "detached": detached,
        "stash_depth": stash_depth,
        "crisis": bool(in_progress) or detached,
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
        "state": repo_state(root),
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
    """Read a stored instant, always as an aware UTC one.

    Every write here is `datetime.now(timezone.utc).isoformat()`, so values
    carry an offset - except the ones that do not: a record hand-written, or one
    migrated from a schema that stored a bare clock. `fromisoformat` returns a
    NAIVE datetime for those, and subtracting a naive from an aware one raises
    TypeError, which `except ValueError` does not catch. One unlabelled
    timestamp anywhere in the archive therefore crashed the health check rather
    than ageing a single baseline wrongly.

    An unlabelled value is read as UTC, because UTC is the only clock this
    project writes. That is a stated assumption rather than a guess, and it
    belongs here rather than at each call site that would otherwise have to make
    it separately - and differently.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def detect_context_issues(
    anchor: ProjectAnchor,
    records: list[dict[str, Any]],
    current_inventory: dict[str, Any] | None = None,
    *,
    archive: Chronicle | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if anchor.is_git:
        # An unfinished git operation masquerades as ordinary dirty files, so
        # it is surfaced by name before any freshness reasoning is attempted.
        state = repo_state(Path(anchor.project_root))
        if state["crisis"]:
            operations = state["in_progress"] or ["detached-head"]
            issues.append(
                {
                    "code": "repo-in-progress-operation",
                    "severity": "warning",
                    "detail": f"Repository is {', '.join(operations)}; finish or abort "
                              "the operation before substantive work.",
                }
            )
    if archive is not None and archive.root.is_dir():
        now = time.time()
        for lock_path in sorted(archive.root.glob("*.lock")):
            try:
                age_seconds = now - lock_path.stat().st_mtime
            except OSError:
                continue
            if age_seconds > STALE_LOCK_SECONDS:
                issues.append(
                    {
                        "code": "stale-lock",
                        "severity": "warning",
                        "detail": f"{lock_path.name} has held the archive for "
                                  f"{int(age_seconds // 60)} minutes; a writer likely died mid-write.",
                    }
                )
    inventory_records = [record for record in records if record["kind"] == "inventory"]
    latest_inventory = inventory_records[-1] if inventory_records else None
    if latest_inventory is None:
        issues.append({"code": "no-baseline", "severity": "warning", "detail": "Run inspect."})
    else:
        # Decay, not a binary flag: confidence fades with the records written
        # since the baseline, and the age is reported alongside so 24h1m does
        # not read identically to a month.
        from .godmode_compress import confidence as record_confidence

        latest_sequence = records[-1]["sequence"] if records else 0
        baseline_confidence = record_confidence(latest_inventory["sequence"], latest_sequence)
        captured = _parse_time(latest_inventory["data"].get("captured_at"))
        if captured and (datetime.now(timezone.utc) - captured).total_seconds() > 86_400:
            age_hours = int((datetime.now(timezone.utc) - captured).total_seconds() // 3600)
            issues.append(
                {"code": "stale-baseline", "severity": "warning",
                 "detail": f"Inventory is {age_hours}h old; confidence {baseline_confidence}.",
                 "confidence": baseline_confidence}
            )
        elif baseline_confidence < 0.5:
            issues.append(
                {"code": "fading-baseline", "severity": "warning",
                 "detail": f"{latest_sequence - latest_inventory['sequence']} records written "
                           f"since the last inventory; confidence {baseline_confidence}. Run inspect.",
                 "confidence": baseline_confidence}
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
            # An mtime can only move forward on an untouched tree; one that
            # moved backward means a restore or a clock change rewrote reality
            # underneath the baseline, so freshness reasoning cannot be trusted.
            recorded_entries = {
                entry["path"]: entry
                for entry in latest_inventory["data"].get("entries", [])
            }
            regressed = sorted(
                entry["path"]
                for entry in current_inventory.get("entries", [])
                if entry["path"] in recorded_entries
                and isinstance(entry.get("mtime_ns"), int)
                and isinstance(recorded_entries[entry["path"]].get("mtime_ns"), int)
                and entry["mtime_ns"] < recorded_entries[entry["path"]]["mtime_ns"]
            )
            if regressed:
                issues.append(
                    {
                        "code": "clock-or-restore-anomaly",
                        "severity": "warning",
                        "detail": f"{len(regressed)} files' mtimes moved backward since the "
                                  f"baseline (e.g. {regressed[0]}); a restore or clock change happened.",
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
        if record["kind"] != "invariant":
            continue
        # Retiring an invariant is the lifecycle, not a conflict. Retiring one
        # means writing a new record with a new value and a retired status, so
        # comparing every record ever written for a subject made the documented
        # act of retirement produce an error by construction - and `doctor`
        # reported the archive unhealthy for doing the right thing.
        #
        # A missing status still counts as live: records written before status
        # was recorded must keep being checked, or the exemption retires the
        # detector rather than the record.
        if str(record["data"].get("status", "")).lower() in SETTLED_STATUSES:
            continue
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
        # Which build is enforcing, as opposed to which one is being written.
        # Every other version surface here reads the tree - eight of them, the
        # latest tag, the tree a tag points at - and none reads the copy that
        # is installed and actually refusing tool calls. Those are different
        # facts, and only the first had checks: an installed plugin leaves no
        # trace in the repository it guards, so a gap between them is silent by
        # construction and there is no warning to miss. The root is included
        # because a version cannot distinguish two installs of the same number,
        # and the question is which copy this is.
        "enforcing": {
            "version": RUNTIME_VERSION,
            "root": str(Path(__file__).resolve().parent),
        },
        "identity": anchor.public_view(),
        "issues": detect_context_issues(anchor, records, current_inventory, archive=archive),
        "records": [_record_summary(record) for record in selected],
        "limits": {
            "perfect_memory": False,
            "source_code_stored": False,
            "raw_prompts_stored": False,
            "background_monitoring": False,
        },
    }
    def estimated() -> int:
        return max(1, len(json.dumps(brief, ensure_ascii=False)) // 4)

    # Degradation ladder: full records, then typed-compressed views (each
    # declaring its mask and reconstruction handle), then dropped-but-counted.
    if estimated() > token_budget:
        from .godmode_compress import compress_brief

        brief["records"] = compress_brief(archive, selected)
        brief["compression"] = "typed; every view lists removed fields and its seq: handle"
    dropped = 0
    while brief["records"] and estimated() > token_budget:
        brief["records"].pop(0)
        dropped += 1
    if dropped:
        brief["records_dropped"] = dropped
    brief["estimated_tokens"] = estimated()
    brief["token_budget"] = token_budget
    return brief


def capacity_checkpoint_due(
    archive: Chronicle, token_budget: int = DEFAULT_CONTEXT_BUDGET
) -> dict[str, Any]:
    """Deterministic pre-compaction signal: is the context brief near capacity?

    A host hook calls this to decide whether to write an atomic checkpoint
    before compaction; the decision must live here, not in the hook, so every
    host applies the same threshold. The signal fires at 80% rather than 100%
    because by the time the brief overflows, the degradation ladder has already
    discarded detail a checkpoint should have preserved. The checkpoint itself
    is deliberately not written here: writing is a policy action that belongs
    to the caller, while this function stays a pure measurement.
    """
    brief = build_context_brief(archive.anchor, archive, token_budget=token_budget)
    estimated = brief["estimated_tokens"]
    threshold = int(token_budget * 0.8)
    due = estimated > threshold
    return {
        "due": due,
        "estimated_tokens": estimated,
        "budget": token_budget,
        "detail": (
            f"Brief estimate {estimated} tokens vs threshold {threshold} (80% of {token_budget}); "
            + ("write an atomic checkpoint before compaction." if due
               else "capacity is comfortable.")
        ),
    }


def claim_worktree(archive: Chronicle, anchor: ProjectAnchor) -> dict[str, Any]:
    """Declare this agent active in this worktree, so a collision is visible
    before two agents mutate the same tree, not after."""
    from .godmode_chronicle import writer_fingerprint

    record = archive.append(
        "branch",
        f"worktree-claim:{anchor.project_key}",
        {"worktree": "<project-root>", "branch": anchor.branch,
         "agent": writer_fingerprint(), "state": "claimed"},
    )
    return {"claimed": True, "sequence": record["sequence"],
            "collisions": worktree_collisions(archive, anchor)}


def worktree_collisions(archive: Chronicle, anchor: ProjectAnchor) -> list[dict[str, Any]]:
    """Live claims by a different agent on this same worktree."""
    from .godmode_chronicle import writer_fingerprint

    me = writer_fingerprint()
    latest_by_agent: dict[str, dict[str, Any]] = {}
    for record in archive.select(kind="branch", limit=200):
        data = record["data"]
        if record["subject"] != f"worktree-claim:{anchor.project_key}":
            continue
        agent = data.get("agent", {})
        key = f"{agent.get('host')}/{agent.get('model')}"
        latest_by_agent[key] = {"agent": key, "state": data.get("state"),
                                "branch": data.get("branch"), "sequence": record["sequence"]}
    mine = f"{me.get('host')}/{me.get('model')}"
    return [entry for key, entry in sorted(latest_by_agent.items())
            if key != mine and entry["state"] == "claimed"]


def release_worktree(archive: Chronicle, anchor: ProjectAnchor) -> dict[str, Any]:
    from .godmode_chronicle import writer_fingerprint

    record = archive.append(
        "branch",
        f"worktree-claim:{anchor.project_key}",
        {"worktree": "<project-root>", "branch": anchor.branch,
         "agent": writer_fingerprint(), "state": "released"},
    )
    return {"released": True, "sequence": record["sequence"]}


def explain_context(anchor: ProjectAnchor, archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events() if archive.initialized() else []
    counts = Counter(record["kind"] for record in records)
    # What loading this context would cost, shown before anything loads.
    brief = build_context_brief(anchor, archive)
    return {
        "cost": {
            "estimated_tokens": brief["estimated_tokens"],
            "token_budget": brief["token_budget"],
            "records_included": len(brief.get("records", brief.get("selected", []))) or None,
            "records_total": len(records),
        },
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


def why(anchor: ProjectAnchor, archive: Chronicle, about: str) -> dict[str, Any]:
    """Answer "why is this the way it is?" for a named path or topic.

    The answer is built from actual archive records, never inference: a claim
    with no sequence number behind it is a guess wearing a badge. Categories
    are always present even when empty, because "no recorded decision touches
    this file" is itself an answer a caller must be able to distinguish from
    "the question was not asked". Matching is a case-insensitive substring
    over subject, data values, and evidence — cheap and predictable beats
    clever here, since the caller can always widen or narrow `about`. Atlas
    `affected` edges are deliberately not consulted: dependencies reported
    here are ones a change record actually named, so every entry stays
    evidence-linked.
    """
    needle = about.strip().lower()
    records = archive.read_events() if archive.initialized() else []

    def mentions(record: dict[str, Any]) -> bool:
        if needle in record["subject"].lower():
            return True
        if needle in json.dumps(record["data"], ensure_ascii=False, default=str).lower():
            return True
        return any(needle in str(item).lower() for item in record.get("evidence", []))

    def entry(record: dict[str, Any]) -> dict[str, Any]:
        evidence = record.get("evidence") or []
        return {
            "subject": record["subject"],
            "sequence": record["sequence"],
            "recorded_at": record["recorded_at"],
            "evidence": evidence[0] if evidence else f"seq:{record['sequence']}",
        }

    answer: dict[str, Any] = {
        "about": about,
        "decisions": [],
        "fixes": [],
        "dependencies": [],
        "invariants": [],
    }
    for record in records:
        if not needle or not mentions(record):
            continue
        kind = record["kind"]
        data = record["data"]
        if kind == "decision":
            answer["decisions"].append(entry(record))
        elif kind == "invariant":
            answer["invariants"].append(entry(record))
        elif kind == "lesson":
            answer["fixes"].append(entry(record))
        elif kind == "checkpoint" and str(data.get("status", "")).lower() in {"green", "fixed"}:
            answer["fixes"].append(entry(record))
        elif kind == "change" and any(
            needle in str(name).lower() for name in data.get("files", [])
        ):
            answer["dependencies"].append(entry(record))
    return answer


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
