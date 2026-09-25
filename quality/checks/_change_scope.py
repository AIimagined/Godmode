"""Shared "what changed" scope for every check under `quality/checks/` (and
the push preflight, `scripts/godmode_runtime/godmode_preflight.py`), so scope
is computed once, the same way everywhere (spec R10, 2026-09-23).

A checker's findings answer two independent questions:

- **filter** - which findings even count: `added` (default while developing
  - only a finding on a line this change added), `file` (a finding anywhere
  in a file this change touched), or `all` (every finding, tree-wide -
  today's behaviour, unchanged; the release check and CI ask for this).
- **fail level** - which of the counted findings fail the run: `harm`
  (default - secrets, private names leaving the machine, release/publish
  safety), `error`, or `warning`; a finding below the chosen level is still
  printed, never dropped - it is reported as information.

A finding on a line the change did not touch is labelled pre-existing and
never blocks that change, whatever its severity - but only at `added` or
`file` scope. At `all` scope nothing is exempted this way, so CI keeps
failing on exactly what it fails on today (no check here classifies a kind
as anything below `warning`, so a `warning`-or-above fail level at `all`
scope reproduces "fail on any finding" losslessly).

Added lines come from `git diff` against the merge base with the default
branch, falling back to the staged diff when no such comparison can be made
(a pre-commit hook has no merge base of its own, only what is staged). When
neither diff can be produced, the effective filter falls back to `all`:
an unmeasurable scope must never silently narrow what gets reported.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

FILTERS = ("added", "file", "all")
LEVELS = ("harm", "error", "warning")

#: Severity order, most severe first. `information` is the residual class:
#: nothing a check classifies falls there today, so it exists for a future
#: check that wants a kind that is reported but never fails, at any level.
_ORDER = {"harm": 3, "error": 2, "warning": 1, "information": 0}


def add_scope_args(parser: argparse.ArgumentParser, *, default_filter: str = "added",
                    default_level: str = "harm") -> None:
    """The three flags every check shares. A check's own `main()` still owns
    its other arguments; this only adds these three, once, the same way."""
    parser.add_argument("--filter", choices=FILTERS, default=default_filter,
                        help=f"which findings count (default: {default_filter})")
    parser.add_argument("--fail-level", choices=LEVELS, default=default_level,
                        dest="fail_level",
                        help=f"the lowest severity that fails the run (default: {default_level})")
    parser.add_argument("--base", default=None,
                        help="the ref to diff against for --filter added/file "
                             "(default: the merge base with the default branch, "
                             "or the staged diff when neither is available)")


def blocks(level: str, fail_level: str) -> bool:
    """Whether a finding at `level` fails a run set to `fail_level`."""
    return _ORDER.get(level, _ORDER["information"]) >= _ORDER.get(fail_level, _ORDER["harm"])


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                          text=True, timeout=60, encoding="utf-8", errors="replace")


def default_branch(root: Path) -> str | None:
    """The remote's default branch, read from its HEAD symref; a plain
    `main`/`master` fallback when the symref is not set (a fresh clone with
    no `origin/HEAD` yet); None when neither can be resolved."""
    out = _git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip().rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        check = _git(root, "rev-parse", "--verify", "--quiet", f"origin/{candidate}")
        if check.returncode == 0:
            return candidate
    return None


def _merge_base(root: Path, ref: str) -> str | None:
    out = _git(root, "merge-base", "HEAD", ref)
    text = out.stdout.strip()
    return text if out.returncode == 0 and text else None


def added_lines(root: Path, base: str | None = None) -> dict[str, set[int]] | None:
    """Added-line numbers per repo-relative path, from `git diff` against the
    merge base with `base` (default: the default branch), falling back to
    the staged diff when no such comparison can be made. None when neither
    diff could be produced at all (no repository, no git, no staged
    change either) - callers decide what an unmeasurable scope means to
    them; `resolve` below falls back to `all`.
    """
    root = Path(root)
    ref = base or default_branch(root)
    diff_text = None
    if ref:
        merge_point = _merge_base(root, ref) or ref
        out = _git(root, "diff", "--unified=0", "--no-color", f"{merge_point}...HEAD")
        if out.returncode == 0:
            diff_text = out.stdout
    if not diff_text:
        out = _git(root, "diff", "--unified=0", "--no-color", "--cached")
        if out.returncode == 0 and out.stdout.strip():
            diff_text = out.stdout
    if diff_text is None:
        return None
    return _parse_unified_added_lines(diff_text)


def _parse_unified_added_lines(diff_text: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    current: str | None = None
    next_line = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = None if path == "/dev/null" else (
                path[2:] if path.startswith(("a/", "b/")) else path)
            continue
        if line.startswith("@@"):
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
                next_line = int(plus.split(",")[0])
            except (IndexError, ValueError):
                next_line = 1
            continue
        if current is None:
            continue
        if line.startswith("+"):
            out.setdefault(current, set()).add(next_line)
            next_line += 1
        elif line.startswith("-"):
            continue
        else:
            next_line += 1
    return out


def resolve(root: Path, filt: str, base: str | None = None) -> tuple[str, dict[str, set[int]]]:
    """The effective filter and its added-line map. Falls back to `all` when
    `filt` asks for a diff that cannot be produced - correctness over
    convenience: an unmeasurable scope must not silently narrow what is
    reported."""
    if filt == "all":
        return "all", {}
    added = added_lines(root, base)
    if added is None:
        return "all", {}
    return filt, added


def in_scope(path: str, line: int | None, filt: str, added: dict[str, set[int]]) -> bool:
    """Whether a finding at `path` (and, when known, `line`) counts under
    filter `filt`. A finding with no line of its own (a whole-file or
    whole-tree verdict) is scoped by file even under `added` - there is no
    finer location to ask "was this line touched"."""
    if filt == "all":
        return True
    if filt == "file" or line is None:
        return path in added
    return line in added.get(path, set())


def pre_existing(path: str, line: int | None, added: dict[str, set[int]]) -> bool:
    """Line-level: True when this path (or path:line) is not one the diff
    touched. Independent of `filt` - a caller decides whether that matters
    (it does not, at `all` scope)."""
    if line is None:
        return path not in added
    return line not in added.get(path, set())
