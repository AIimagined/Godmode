"""C-6: ownership map and gate-table freshness (0.3.28 Plan 4, Task 2).

The 0.3.27 miss this closes: `hooks/gate_table.json` can drift from the
classifier that generated it (`scripts/dev/build_decision_table.py`) with
nothing catching it until `tests.test_gate_parity` happens to run. This
module gives a caller two things standing alone did not: a map of which
gate rule owns a given path or command (`ownership_map`/`owner_of`), and a
cheap digest-only freshness check (`table_is_stale`) cheap enough to run on
every commit (`godmode_githooks._evaluate_pre_commit`), not only in CI.

**Ownership map: a divergence, stated once here.** The live classifier
(`godmode_sentinel.classify_action`) is FIRST-match-wins over `_ACTION_
PATTERNS` and a short, hand-ordered if/elif chain for a path's write
verdict (`_write_verdict`). `ownership_map()` is deliberately a LAST-match-
wins list instead - the shape a reader expects from a CODEOWNERS-style
file, where a later, more specific line overrides an earlier, general one.
To reproduce the same
WINNER as the live classifier for a subject that matches more than one
entry, this module's list is built in the REVERSE of the classifier's own
priority order (lowest-priority entry first, highest last) - verified by
this file's own module docstring reasoning, not by re-deriving the
classifier here. Two things this map does NOT attempt, on purpose:

- **Pinned-evaluator ownership.** `_write_verdict`'s FIRST check
  (`_pinned_evaluator_hit`) needs a live archive and a project root to
  resolve which paths are currently pinned - there is no static pattern to
  put in a map. A pinned path still resolves through whichever OTHER rule
  matches it (usually `worktree-file-mutation`'s catch-all shape via
  `_SENSITIVE_EDIT`, or nothing) - this map reports a lower tier than
  `classify_action` would for that one path, and that gap is this
  paragraph, not a silent one.
- **The containment/default branch.** `_write_verdict`'s fall-through
  (outside the tree, or "just a file in the working tree") depends on
  `project_root` and `archive` the same way. A path this map does not
  otherwise own is reported as unowned (`owner_of` returns `None`), never
  guessed at as `worktree-file-mutation` by a synthetic catch-all pattern -
  a wrong-but-confident answer is worse than an honest gap here, and the
  three-path/three-command acceptance test only exercises subjects this
  map actually owns.
- **Command ownership beyond `_ACTION_PATTERNS`.** The full classifier also
  reads read-heads, PowerShell verb tables, DB client heads, and the `mv`/
  `cp` destination branch - none of those are a bare regex-over-the-whole-
  command the way `_ACTION_PATTERNS` is, so none of them are represented
  here. `ownership_map()` answers "which MUTATION rule owns this", not "is
  this read-only" - a read command is reported unowned, which is correct
  (nothing in `_ACTION_PATTERNS` claims it), never misreported as a
  mutation.

**Freshness: lighter than `tests.test_gate_parity`'s, on purpose.**
`tests.test_gate_parity.ParityFloor.test_table_is_fresh` regenerates the
WHOLE table and diffs it byte-for-byte - the strong, slow proof, run in
CI. `table_is_stale` only compares `hooks/gate_table.json`'s own recorded
`generated_from` against this module's own `_generated_from()` - cheap
enough for a pre-commit hook to run on every commit, catching the shape of
miss 0.3.27 shipped (the table's digest field silently stale) without
paying for a full regeneration on every `git commit`.

**Digest ownership, stated once here.** `_generated_from()` lives in THIS
runtime module, not in `scripts/dev/build_decision_table.py`: the runtime
must never import a `scripts/dev/*` tool (that dev script imports the full
sentinel vocabulary and asserts floor entries at module load - real work a
runtime import has no business triggering, and a fix-round-1 finding on
this task's first cut, where the reverse direction made `godmode sbom`
count `build_decision_table` as a phantom runtime dependency - nothing
under `scripts/godmode_runtime/` may import from `scripts/dev/`).
`scripts/dev/build_decision_table.py` imports this function FROM the
runtime instead, so the two call sites can never independently drift on
what they hash.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_sentinel import _ACTION_PATTERNS, _FREEZE_FILE, _HOOK_AS_CODE, _SENSITIVE_EDIT, _TIER_BY_CATEGORY

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TABLE_PATH_PARTS = ("hooks", "gate_table.json")
# Fix round 1 (reviewer finding on 97a2efe): whether `project_root` itself is
# a checkout of the godmode SOURCE - detected by the presence of the sentinel
# module this task's own digest is computed from, never by identity against
# this file's own `_REPO_ROOT`. `_REPO_ROOT` is one specific directory (the
# checkout `godmode_ownership.py` happens to be imported from); this
# project's own workflow runs commits from inside many OTHER directories at
# once (`.claude/worktrees/agent-*`, each a full separate checkout), and a
# check gated on `_REPO_ROOT` would silently miss a missing table in every
# one of them. A path-based presence check answers "is this directory a
# godmode-source checkout" regardless of which one it is.
_SENTINEL_RELATIVE_PARTS = ("scripts", "godmode_runtime", "godmode_sentinel.py")

# Path-owning rules, in the sentinel's own precedence for `_write_verdict`
# REVERSED (see module docstring): hook-as-code is checked FIRST there and
# wins on first match, so it is placed LAST here to still win under
# last-match-wins.
_PATH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_SENSITIVE_EDIT, "worktree-file-mutation"),
    (_FREEZE_FILE, "release-freeze-mutation"),
    (_HOOK_AS_CODE, "hook-as-code-write"),
)


_SENTINEL_PATH = Path(_REPO_ROOT, *_SENTINEL_RELATIVE_PARTS)


def _generated_from() -> str:
    """sha256 digest (first 12 hex chars) of THIS checkout's own
    `godmode_sentinel.py`, line-ending-normalized to LF - a checkout under
    autocrlf carries CRLF where CI's carries LF, and hashing raw bytes made
    a committed table stale on every platform but the one that built it
    (matrix run, 2026-08-31); the vocabulary this digest protects is text,
    so the text is what gets hashed. This is the canonical digest -
    `scripts/dev/build_decision_table.py`'s own `_generated_from()` imports
    THIS function (see module docstring) rather than the runtime importing
    that dev script."""
    return hashlib.sha256(
        _SENTINEL_PATH.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()[:12]


def ownership_map() -> list[dict[str, str]]:
    """`[{"pattern", "rule", "tier"}]`, last-match-wins (see module
    docstring for the ordering rationale). `pattern` is the exact regex
    source of the sentinel rule it came from - matched with `re.search`,
    the same operation the sentinel itself uses.

    Command rules (`_ACTION_PATTERNS`, reversed - see above) come FIRST;
    the three static path rules come LAST. `_ACTION_PATTERNS`' own
    `release-or-external-write` entry matches the bare word "release"
    anywhere (`\\brelease\\b`, case-insensitive) - which a path like
    `RELEASE-FREEZE.md` also contains - so a path-shaped rule has to
    out-rank a word-anchored command rule for a subject that happens to
    satisfy both, not the other way round: `_write_verdict` (the live
    classifier) never even consults `_ACTION_PATTERNS` for a path, so a
    file being caught by a command regex at all is already this map's own
    approximation, not something the real classifier would do - putting
    path rules last means a subject shaped like a real path always resolves
    the way `_write_verdict` actually would.
    """
    entries: list[dict[str, str]] = []
    for category, pattern, _impact in reversed(_ACTION_PATTERNS):
        entries.append({
            "pattern": pattern.pattern,
            "rule": category,
            "tier": _TIER_BY_CATEGORY.get(category, "R3"),
        })
    for pattern, rule in _PATH_RULES:
        entries.append({
            "pattern": pattern.pattern,
            "rule": rule,
            "tier": _TIER_BY_CATEGORY.get(rule, "R3"),
        })
    return entries


def owner_of(subject: str, table: list[dict[str, str]] | None = None) -> dict[str, str] | None:
    """The last entry of `table` (default a fresh `ownership_map()`) whose
    pattern matches `subject` - `None` when nothing in the map owns it."""
    if table is None:
        table = ownership_map()
    winner: dict[str, str] | None = None
    for entry in table:
        if re.search(entry["pattern"], subject):
            winner = entry
    return winner


def table_generated_from(project_root: Path) -> str | None:
    """`hooks/gate_table.json`'s own recorded `generated_from` field, or
    `None` for an absent, unreadable, or malformed file - never a stale
    guess."""
    path = Path(project_root, *_TABLE_PATH_PARTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("generated_from") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def table_is_stale(project_root: Path) -> dict[str, Any]:
    """`{"present", "stale", "recorded", "current"}` - whether the checked-
    in decision table's `generated_from` still matches the sentinel's live
    digest.

    Two absence cases are told apart (fix round 1 - a reviewer finding on
    the first cut of this function, which collapsed both to "not stale"):

    - A project with no `hooks/gate_table.json` AND no
      `scripts/godmode_runtime/godmode_sentinel.py` either (a synthetic
      project, or the `isolated_project()` test fixture) is not a godmode-
      source checkout at all - it has nothing to be stale about, and
      `stale` stays `False`.
    - A project that DOES carry the sentinel module (a real godmode-source
      checkout - this repository itself, or any of its worktree checkouts)
      but is MISSING `hooks/gate_table.json` is exactly the drift this task
      exists to catch: the table this checkout ships must exist, so its
      absence - a bad merge, an accidental delete - is stale, not silently
      "nothing to check."

    When the table IS present, staleness is the ordinary digest comparison:
    `True` when its own recorded `generated_from` disagrees with the
    sentinel's current digest.
    """
    recorded = table_generated_from(project_root)
    present = Path(project_root, *_TABLE_PATH_PARTS).is_file()
    current = _generated_from()
    sentinel_present = Path(project_root, *_SENTINEL_RELATIVE_PARTS).is_file()
    stale = (present and recorded != current) or (not present and sentinel_present)
    return {
        "present": present,
        "stale": stale,
        "recorded": recorded,
        "current": current,
    }


def _diff_only_paths(project_root: Path) -> list[str]:
    raw = run_git(project_root, "status", "--porcelain", "--untracked-files=all") or ""
    paths: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) > 3 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.strip().strip('"').replace("\\", "/"))
    return paths


def _tracked_paths(project_root: Path) -> list[str]:
    raw = run_git(project_root, "ls-files") or ""
    return [line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip()]


def check(project_root: Path, *, diff_only: bool = False) -> dict[str, Any]:
    """`godmode ownership --check`'s own report.

    Walks every git-tracked path (or, `diff_only`, only the working tree's
    own changes - staged, unstaged, and untracked) and names each one's
    owning rule from `ownership_map()`. `table_fresh` is `False` exactly
    when `table_is_stale` is - the CLI exits 1 on that alone, independent
    of how many paths this call happened to walk.
    """
    table = ownership_map()
    paths = _diff_only_paths(project_root) if diff_only else _tracked_paths(project_root)
    entries = []
    for path in paths:
        owner = owner_of(path, table)
        entries.append({
            "path": path,
            "rule": owner["rule"] if owner else None,
            "tier": owner["tier"] if owner else None,
        })
    freshness = table_is_stale(project_root)
    return {
        "project": str(project_root),
        "diff_only": diff_only,
        "entries": entries,
        "owned": sum(1 for e in entries if e["rule"]),
        "unowned": sum(1 for e in entries if not e["rule"]),
        "table_fresh": not freshness["stale"],
        "table_generated_from": freshness["recorded"],
        "sentinel_digest": freshness["current"],
    }
