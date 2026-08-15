"""Resolve a project's authority corpus by role rather than by filename.

Godmode never hardcodes the name of a project's operating guide, lessons ledger or
status document. A project declares `role -> path` bindings; every later stage
addresses documents by role. Renaming a document must not break anything, and no
personal name is ever required in a path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .godmode_anchor import canonical_path, run_git
from .godmode_errors import CorpusError

ROLES_FILENAME = ".godmode-roles.json"

# Weights order the corpus when the budget cannot hold all of it. Higher wins.
DEFAULT_WEIGHTS: dict[str, float] = {
    "operating-guide": 1.0,
    "operator-profile": 1.0,
    "invariants": 0.95,
    "state": 0.9,
    "sprint-truth": 0.85,
    "lessons": 0.7,
    "checklist": 0.7,
    "decisions": 0.6,
    "inventory": 0.5,
}

# Zero-config default: patterns a project is likely to already use. A project that
# declares its own bindings replaces this wholesale, never merges with it.
DEFAULT_ROLES: dict[str, list[str]] = {
    "operating-guide": ["GODMODE.md", "OPERATING-GUIDE.md", "AGENTS.md", "CLAUDE.md"],
    "operator-profile": ["OPERATOR.md"],
    "invariants": ["docs/FIXED-REGISTRY.md", "docs/INVARIANTS.md"],
    "state": ["docs/STATE.md"],
    "sprint-truth": ["docs/SPRINT-SSOT.md"],
    "lessons": ["docs/LESSONS.md"],
    "checklist": ["docs/RELEASE-CHECKLIST.md"],
    "decisions": ["docs/DECISIONS.md"],
    "inventory": ["docs/FEATURE-INVENTORY.md"],
}

UNWEIGHTED_ROLE_WEIGHT = 0.5


@dataclass(frozen=True)
class Binding:
    """One resolved authority document."""

    role: str
    weight: float
    pattern: str
    path: Path

    def view(self, project: Path) -> dict[str, Any]:
        return {
            "role": self.role,
            "weight": self.weight,
            "pattern": self.pattern,
            "path": _relative(self.path, project),
        }


@dataclass(frozen=True)
class Resolution:
    """The corpus as it actually exists on disk, including what is absent."""

    project: Path
    declared: bool
    bindings: tuple[Binding, ...]
    missing: tuple[tuple[str, str], ...]
    collisions: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def healthy(self) -> bool:
        return not self.collisions

    def view(self) -> dict[str, Any]:
        return {
            "declared": self.declared,
            "source": ROLES_FILENAME if self.declared else "defaults",
            "roles": len({binding.role for binding in self.bindings}),
            "bound": len(self.bindings),
            "missing": [{"role": role, "pattern": pattern} for role, pattern in self.missing],
            "collisions": [
                {"path": path, "roles": list(roles)} for path, roles in self.collisions
            ],
            "bindings": [binding.view(self.project) for binding in self.bindings],
        }


def _relative(path: Path, project: Path) -> str:
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        return path.as_posix()


def _read_declaration(project: Path) -> dict[str, Any] | None:
    source = project / ROLES_FILENAME
    if not source.is_file():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusError(f"Cannot read {ROLES_FILENAME}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{ROLES_FILENAME} is not valid JSON (line {exc.lineno}): {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise CorpusError(f"{ROLES_FILENAME} must contain a JSON object")
    return payload


def _declared_roles(payload: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Flatten `roles` and open-ended `custom` entries into one patterns/weights pair."""
    patterns: dict[str, list[str]] = {}
    weights: dict[str, float] = dict(DEFAULT_WEIGHTS)

    declared = payload.get("roles", {})
    if not isinstance(declared, dict):
        raise CorpusError(f"{ROLES_FILENAME}: 'roles' must be an object")
    for role, value in declared.items():
        patterns[role] = [value] if isinstance(value, str) else list(value)

    custom = payload.get("custom", {})
    if not isinstance(custom, dict):
        raise CorpusError(f"{ROLES_FILENAME}: 'custom' must be an object")
    for role, spec in custom.items():
        if not isinstance(spec, dict):
            raise CorpusError(f"{ROLES_FILENAME}: custom role '{role}' must be an object")
        raw = spec.get("paths", [])
        patterns[role] = [raw] if isinstance(raw, str) else list(raw)
        if "weight" in spec:
            weights[role] = float(spec["weight"])

    overrides = payload.get("weights", {})
    if not isinstance(overrides, dict):
        raise CorpusError(f"{ROLES_FILENAME}: 'weights' must be an object")
    for role, weight in overrides.items():
        weights[role] = float(weight)

    return patterns, weights


def _expand(project: Path, pattern: str) -> list[Path]:
    """Resolve one pattern to concrete files. Globs are sorted for determinism."""
    if any(character in pattern for character in "*?["):
        return sorted(path for path in project.glob(pattern) if path.is_file())
    candidate = project / pattern
    return [candidate] if candidate.is_file() else []


def resolve_roles(project: Path) -> Resolution:
    """Bind every declared role to the files that actually exist.

    A pattern that matches nothing is reported as missing, never silently dropped:
    an authority document the project believes it has is a finding.
    """
    root = canonical_path(project)
    payload = _read_declaration(root)
    if payload is None:
        patterns, weights = dict(DEFAULT_ROLES), dict(DEFAULT_WEIGHTS)
    else:
        patterns, weights = _declared_roles(payload)

    bindings: list[Binding] = []
    missing: list[tuple[str, str]] = []
    claimed: dict[str, list[str]] = {}

    for role in sorted(patterns):
        weight = weights.get(role, UNWEIGHTED_ROLE_WEIGHT)
        for pattern in patterns[role]:
            matches = _expand(root, pattern)
            if not matches:
                missing.append((role, pattern))
                continue
            for path in matches:
                key = _relative(path, root)
                roles_for_path = claimed.setdefault(key, [])
                if role not in roles_for_path:
                    roles_for_path.append(role)
                bindings.append(Binding(role=role, weight=weight, pattern=pattern, path=path))

    collisions = tuple(
        (path, tuple(roles)) for path, roles in sorted(claimed.items()) if len(roles) > 1
    )

    # Deterministic order: weight descending, then role, then path. Ranking depends on
    # this being stable across hosts, so never rely on dict or glob iteration order.
    ordered = tuple(
        sorted(bindings, key=lambda binding: (-binding.weight, binding.role, str(binding.path)))
    )
    return Resolution(
        project=root,
        declared=payload is not None,
        bindings=ordered,
        missing=tuple(missing),
        collisions=collisions,
    )


@dataclass(frozen=True)
class Segment:
    """One addressable chunk of an authority document."""

    role: str
    weight: float
    path: str
    heading: str
    start_line: int
    end_line: int
    body: str

    @property
    def tokens(self) -> int:
        # Deliberately crude. A tokenizer is a dependency; this only has to rank
        # and budget, and it is consistent across hosts, which is what matters.
        return max(1, len(self.body) // 4)

    def view(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "heading": self.heading,
            "lines": [self.start_line, self.end_line],
            "tokens": self.tokens,
        }


def _heading_of(line: str) -> str | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    marker, _, text = stripped.partition(" ")
    if set(marker) != {"#"} or len(marker) > 6:
        return None
    return text.strip() or marker


def segment_document(binding: Binding, project: Path, max_lines: int = 120) -> list[Segment]:
    """Split a document on headings, then cap runaway sections.

    A section longer than `max_lines` is split so one enormous chapter cannot
    consume the whole budget and crowd out every other role.
    """
    try:
        text = binding.path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise CorpusError(f"Cannot read {binding.path}: {exc}") from exc

    relative = _relative(binding.path, project)
    lines = text.splitlines()
    segments: list[Segment] = []
    heading = "(preamble)"
    start = 1
    buffer: list[str] = []

    def flush(end_line: int) -> None:
        if not any(line.strip() for line in buffer):
            return
        for offset in range(0, len(buffer), max_lines):
            chunk = buffer[offset : offset + max_lines]
            segments.append(
                Segment(
                    role=binding.role,
                    weight=binding.weight,
                    path=relative,
                    heading=heading if offset == 0 else f"{heading} (cont.)",
                    start_line=start + offset,
                    end_line=min(start + offset + len(chunk) - 1, end_line),
                    body="\n".join(chunk).strip(),
                )
            )

    for index, line in enumerate(lines, start=1):
        found = _heading_of(line)
        if found is None:
            buffer.append(line)
            continue
        flush(index - 1)
        heading, start, buffer = found, index, [line]
    flush(len(lines))
    return segments


_WORD = re.compile(r"[A-Za-z0-9_]{2,}")


def _terms(task: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in _WORD.findall(task.lower()):
        seen.setdefault(match, None)
    return list(seen)


def fts5_available() -> bool:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        return True
    except Exception:
        return False
    finally:
        connection.close()


def _relevance_fts5(segments: list[Segment], terms: list[str]) -> dict[int, float]:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE seg_fts USING fts5(body, tokenize='unicode61')")
        connection.executemany(
            "INSERT INTO seg_fts(rowid, body) VALUES (?, ?)",
            [(index, segment.body) for index, segment in enumerate(segments)],
        )
        query = " OR ".join(f'"{term}"' for term in terms)
        rows = connection.execute(
            "SELECT rowid, bm25(seg_fts) FROM seg_fts WHERE seg_fts MATCH ?", (query,)
        ).fetchall()
    except Exception as exc:  # pragma: no cover - corrupt build only
        raise CorpusError(f"FTS5 ranking failed: {exc}") from exc
    finally:
        connection.close()
    # bm25() is negative, lower is better. Flip so higher is better.
    return {int(rowid): -float(score) for rowid, score in rows}


def _relevance_fallback(segments: list[Segment], terms: list[str]) -> dict[int, float]:
    """Hand-rolled BM25, used only when SQLite was built without FTS5."""
    import math
    from collections import Counter

    k1, b = 1.5, 0.75
    docs = [_WORD.findall(segment.body.lower()) for segment in segments]
    lengths = [len(doc) or 1 for doc in docs]
    average = sum(lengths) / len(lengths)
    counts = [Counter(doc) for doc in docs]
    frequency = {
        term: sum(1 for count in counts if term in count) for term in terms
    }
    scores: dict[int, float] = {}
    for index, count in enumerate(counts):
        total = 0.0
        for term in terms:
            occurrences = count.get(term, 0)
            if not occurrences:
                continue
            idf = math.log(1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            norm = occurrences * (k1 + 1)
            denominator = occurrences + k1 * (1 - b + b * lengths[index] / average)
            total += idf * norm / denominator
        if total:
            scores[index] = total
    return scores


def _mtime_stamp(project: Path, path: str) -> int:
    try:
        return (project / path).stat().st_mtime_ns
    except OSError:
        return 0


def _freshness_stamp(project: Path, path: str, is_git: bool) -> int:
    """A file's edit recency, from a source that agrees across checkouts.

    Filesystem mtime records when THIS checkout wrote the byte to disk, not
    when its content last meaningfully changed - `git clone`/`git checkout`
    do not preserve historical mtimes, so two clones of the identical commit
    can disagree on file order even though project state is identical (the
    concrete failure: `evals/fixtures/ranking.json` drifted between two
    clones of the same commit). A commit's own timestamp is part of the
    object the clone already received, so every clone of that commit agrees
    on it regardless of checkout order - reading `git log` instead of
    `stat()` fixes the instability at its source rather than papering over
    one symptom of it. Non-git projects have no such record and no separate
    checkout step to reorder against, so mtime remains the right (and only)
    instrument there.

    An untracked file, or one staged but never committed, has no `git log`
    entry - that is not the same absence as "this project has no git
    history for anything," and stamping it 0 (the oldest possible value)
    would rank a file edited a minute ago behind a six-year-old committed
    sibling, the freshness feature working backwards. Falling back to mtime
    for exactly that case is the pre-existing behaviour and carries none of
    the checkout-order risk: an uncommitted file's mtime is this session's
    real edit time, not a byte a checkout wrote from history. Determinism
    across checkouts is guaranteed for committed files only.

    A non-git project (or an untracked file inside a git one) has no commit
    object to anchor on, so this function still returns raw mtime as the
    freshness *value* for it - that fallback is unchanged. What callers must
    not do is compare that value's magnitude *across* files to order a
    non-git project, because mtime there is assigned by whatever copied or
    checked the files out, not by their content: two copies of an identical
    non-git project can disagree on which file's mtime is newer purely from
    copy timing, the exact instability the git-log fix above already fixed
    for tracked files (`rank` degrades non-git ordering to a path sort for
    this reason - see there).
    """
    if is_git:
        stamp = run_git(project, "log", "-1", "--format=%ct", "--", path)
        if stamp and stamp.isdigit():
            return int(stamp) * 1_000_000_000
        return _mtime_stamp(project, path)
    return _mtime_stamp(project, path)


def rank(
    segments: list[Segment], task: str, project: Path | None = None
) -> list[tuple[Segment, float]]:
    """Score every segment: role weight x relevance x freshness.

    A segment matching nothing still ranks by role, so a high-authority document is
    never invisible merely because the task wording missed it. Freshness breaks
    ties toward recently-edited sources: same project state gives the same
    ordering, but a stale document cannot outrank a fresh sibling on weight alone.

    Rank fusion was prototyped here and rejected on measurement (C-73): fusing
    positions needs long ranked lists to separate candidates, and this corpus is
    tens of segments across three signals, where it collapsed into ties broken
    alphabetically. It also contradicts a deliberate property - role authority is
    *meant* to dominate - which fusion exists to prevent.
    """
    terms = _terms(task)
    raw: dict[int, float] = {}
    if terms and segments:
        raw = _relevance_fts5(segments, terms) if fts5_available() else _relevance_fallback(segments, terms)
    top = max(raw.values(), default=0.0) or 1.0

    freshness: dict[str, float] = {}
    if project is not None:
        is_git = (project / ".git").exists()
        stamps: dict[str, int] = {
            path: _freshness_stamp(project, path, is_git)
            for path in {segment.path for segment in segments}
        }
        if is_git:
            newest_first = sorted(stamps, key=lambda p: (-stamps[p], p))
        else:
            # A non-git project has no commit-object timestamp for any file,
            # so every stamp here came from the mtime fallback - a value
            # copy timing controls, not content. Ordering by that magnitude
            # across files is exactly the checkout-order instability the
            # git-log fix above exists to prevent, just with no deterministic
            # substitute value available; the tie-break degrades to path,
            # the same deterministic instrument the git branch already uses
            # as ITS secondary key, so identical non-git copies always agree
            # regardless of which file the copy happened to timestamp newest.
            newest_first = sorted(stamps)
        # A small, bounded factor: freshness reorders equals, never outvotes weight.
        for position, path in enumerate(newest_first):
            freshness[path] = 1.0 + 0.05 / (1 + position)

    scored: list[tuple[Segment, float]] = []
    for index, segment in enumerate(segments):
        relevance = raw.get(index, 0.0) / top
        # Rounded so float noise cannot reorder identical corpora across hosts.
        score = round(
            segment.weight * (1.0 + relevance) * freshness.get(segment.path, 1.0), 6
        )
        scored.append((segment, score))

    scored.sort(key=lambda pair: (-pair[1], pair[0].path, pair[0].start_line))
    return scored


def build_brief(project: Path, task: str, budget: int) -> dict[str, Any]:
    """Assemble the bounded, deterministic context brief.

    The contract other stages depend on: identical project state plus identical task
    yields an identical brief, whichever model asks for it.
    """
    resolution = resolve_roles(project)
    segments: list[Segment] = []
    for binding in resolution.bindings:
        segments.extend(segment_document(binding, resolution.project))

    scored = rank(segments, task, project=resolution.project)
    included: list[dict[str, Any]] = []
    used = 0
    for segment, score in scored:
        if used + segment.tokens > budget:
            continue
        used += segment.tokens
        entry = segment.view()
        entry["score"] = score
        entry["body"] = segment.body
        included.append(entry)

    chosen = {(entry["path"], entry["lines"][0]) for entry in included}
    unread: dict[str, int] = {}
    for segment, _ in scored:
        if (segment.path, segment.start_line) not in chosen:
            unread[segment.role] = unread.get(segment.role, 0) + 1

    return {
        "task": task,
        "scorer": "fts5-bm25" if fts5_available() else "fallback-bm25",
        "budget": {"limit": budget, "used": used},
        "sources": {
            "roles": len({binding.role for binding in resolution.bindings}),
            "documents": len(resolution.bindings),
            "documents_read": len({entry["path"] for entry in included}),
            "segments": len(segments),
            "segments_read": len(included),
            "statement": (
                f"read {len({entry['path'] for entry in included})} of "
                f"{len(resolution.bindings)} required sources"
            ),
        },
        "required_but_unread": [
            {"role": role, "segments": count} for role, count in sorted(unread.items())
        ],
        "required_but_missing": [
            {"role": role, "pattern": pattern} for role, pattern in resolution.missing
        ],
        "collisions": [{"path": path, "roles": list(roles)} for path, roles in resolution.collisions],
        "context": included,
    }


def _self_check() -> None:
    """Smallest check that fails if role resolution breaks."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "docs").mkdir()
        (project / "GODMODE.md").write_text("guide", encoding="utf-8")
        (project / "docs" / "LESSONS.md").write_text("lessons", encoding="utf-8")

        # Zero-config: defaults bind what exists and report what does not.
        default = resolve_roles(project)
        assert not default.declared
        assert default.healthy
        bound = {binding.role for binding in default.bindings}
        assert bound == {"operating-guide", "lessons"}, bound
        assert any(role == "state" for role, _ in default.missing)

        # Ordering is weight-descending, so the guide outranks the lessons ledger.
        assert default.bindings[0].role == "operating-guide"

        # A declaration replaces the defaults and supports open-ended custom roles.
        (project / ROLES_FILENAME).write_text(
            json.dumps(
                {
                    "roles": {"operating-guide": "GODMODE.md"},
                    "custom": {"engine-parity": {"paths": ["docs/LESSONS.md"], "weight": 0.8}},
                }
            ),
            encoding="utf-8",
        )
        declared = resolve_roles(project)
        assert declared.declared
        assert {binding.role for binding in declared.bindings} == {
            "operating-guide",
            "engine-parity",
        }

        # Two roles claiming one path is a config error, not a silent resolution.
        (project / ROLES_FILENAME).write_text(
            json.dumps({"roles": {"operating-guide": "GODMODE.md", "state": "GODMODE.md"}}),
            encoding="utf-8",
        )
        clashing = resolve_roles(project)
        assert not clashing.healthy
        assert clashing.collisions[0][0] == "GODMODE.md"
        assert set(clashing.collisions[0][1]) == {"operating-guide", "state"}

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "docs").mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\nNever push without an explicit ask.\n\n"
            "# Tokens\nRefresh token rotation must happen exactly once.\n",
            encoding="utf-8",
        )
        (project / "docs" / "LESSONS.md").write_text(
            "# L-001\nA status label is not evidence.\n", encoding="utf-8"
        )

        brief = build_brief(project, "refresh token rotation", budget=2000)
        assert brief["sources"]["documents"] == 2
        assert brief["sources"]["segments"] == 3
        assert brief["context"], "budget was ample; context must not be empty"
        # The token section must outrank the unrelated gates section.
        assert brief["context"][0]["heading"] == "Tokens", brief["context"][0]

        # Determinism is the contract every later stage depends on.
        again = build_brief(project, "refresh token rotation", budget=2000)
        assert brief == again

        # A budget too small to hold everything reports the remainder honestly.
        tight = build_brief(project, "refresh token rotation", budget=12)
        assert tight["sources"]["segments_read"] < tight["sources"]["segments"]
        assert tight["required_but_unread"], "unread segments must be reported, never silent"

    print("godmode_corpus self-check OK")


if __name__ == "__main__":
    _self_check()
