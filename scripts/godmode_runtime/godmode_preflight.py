"""Push preflight: validate the exact committed state in a disposable copy.

Runs BEFORE the password prompt and feeds it, never bypasses it. The
checks run in a throwaway git worktree of HEAD so the working directory
is untouched and what is validated is exactly what a push would ship.
Two checks, two buckets:

- banned-term scan (mechanical): tracked text files against the private
  term list, resolved exactly the way the repo privacy test resolves it
  (env override, then an upward walk); the list living outside the repo
  is the design, so an absent list reports the scan as skipped rather
  than silently passing. Hits are mechanical findings - a scrub fixes
  them - and the finding names the file and count, never the term: a red
  report must not be the second place a term leaks.
- suite command (judgment): any command the caller designates, run inside
  the worktree; a non-zero exit is a judgment finding - a person decides.

The worktree is removed on every exit path. A dirty tree is refused
before anything runs: preflight validates a state, and a dirty tree is
not a state anyone can push.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .godmode_errors import ArchiveError


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def _term_list(repo: Path) -> Path | None:
    override = os.environ.get("GODMODE_COVERAGE_TERMS")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    candidate = repo
    for _ in range(8):
        found = candidate / ".godmode-private" / "coverage-banned-terms.txt"
        if found.is_file():
            return found
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return None


def push_preflight(project: Path | str,
                   suite: list[str] | None = None,
                   archive: Any = None) -> dict[str, Any]:
    repo = Path(project)
    status = _git(repo, "status", "--porcelain=v1")
    if status.returncode != 0:
        raise ArchiveError("preflight needs a git repository")
    if status.stdout.strip():
        raise ArchiveError(
            "preflight refuses a dirty tree: it validates a committed state, "
            "and a dirty tree is not a state anyone can push - commit or "
            "stash first"
        )

    mechanical: list[dict[str, Any]] = []
    judgment: list[dict[str, Any]] = []
    skipped: list[str] = []

    scratch = Path(tempfile.mkdtemp(prefix="godmode-preflight-"))
    worktree = scratch / "head"
    added = _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
    if added.returncode != 0:
        raise ArchiveError(
            "preflight could not create its disposable worktree: "
            + added.stderr.decode("utf-8", errors="replace")[:200]
        )
    try:
        terms_path = _term_list(repo)
        if terms_path is None:
            skipped.append(
                "banned-term scan: no private list found (GODMODE_COVERAGE_TERMS "
                "unset, no .godmode-private/coverage-banned-terms.txt above the "
                "repo) - expected on a fresh clone")
        else:
            terms = [line.strip() for line in
                     terms_path.read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.strip().startswith("#")
                     and len(line.strip()) >= 2]
            patterns = [re.compile(r"\b" + re.escape(t.lower()) + r"\b")
                        for t in terms]
            tracked = _git(worktree, "ls-files", "-z").stdout
            for name in tracked.decode("utf-8").split("\0"):
                if not name:
                    continue
                file = worktree / name
                if not file.is_file():
                    continue
                data = file.read_bytes()
                if b"\0" in data[:8192]:
                    continue
                text = data.decode("utf-8", errors="replace").lower()
                hits = sum(1 for p in patterns if p.search(text))
                if hits:
                    # File and count only - never the term; a red report
                    # must not be the second place a term leaks.
                    mechanical.append({
                        "check": "banned-term",
                        "detail": f"{name}: {hits} distinct term(s) from the "
                                  "private list; run the scrub before staging "
                                  "the push",
                    })
        if suite:
            run = subprocess.run(suite, cwd=worktree, capture_output=True,
                                 check=False, timeout=1800)
            if run.returncode != 0:
                judgment.append({
                    "check": "suite",
                    "detail": f"designated suite exited exit {run.returncode}; "
                              "a person decides whether this state ships",
                })
        else:
            skipped.append("suite: no command designated (--suite)")
        # Standing process debt rides the preflight as judgment findings:
        # a push that never saw the dormant census is how commit stacks
        # queue over unstated criteria and assumptions (operator finding,
        # 2026-09-01). A person decides; nothing here blocks.
        if archive is not None:
            try:
                from .godmode_metrics import utilization

                census = utilization(archive, Path(project))
                for name, fam in sorted(census["families"].items()):
                    if fam["verdict"] == "dormant-with-demand":
                        judgment.append({
                            "check": "census",
                            "detail": f"family '{name}' is dormant-with-demand "
                                      f"(demand {fam['demand']}, fired "
                                      f"{fam['fired']}); pushing anyway is a "
                                      "decision - make it knowingly",
                        })
            except Exception:  # noqa: BLE001 - census failing never blocks a push
                skipped.append("census: unavailable")
            # The reasoning probe at the one genuinely high-stakes moment:
            # a push resting on zero recorded assumptions gets asked what
            # it rests on. One real assumption on record silences it -
            # this is a probe, not a quota.
            try:
                has_assumption = any(
                    r.get("kind") == "assumption"
                    for r in archive.read_events(verify=False))
                if not has_assumption:
                    judgment.append({
                        "check": "assumptions",
                        "detail": "no assumption is on record - what does "
                                  "this push rest on that is not written "
                                  "down? `godmode remember --kind "
                                  "assumption` if there is one; push "
                                  "knowingly if there is not",
                    })
            except Exception:  # noqa: BLE001
                skipped.append("assumption probe: unavailable")
    finally:
        _git(repo, "worktree", "remove", "--force", str(worktree))
        _git(repo, "worktree", "prune")

    return {
        "mechanical": mechanical,
        "judgment": judgment,
        "skipped": skipped,
        "verdict": ("findings" if mechanical or judgment else "clean"),
        # The effect of a control action is confirmed, never assumed: the
        # cleanup claim is checked against the filesystem, and an
        # unconfirmed removal is stated rather than silently believed.
        "cleanup": "confirmed" if not worktree.exists() else "unconfirmed",
        "feeds": "the password gate; preflight never bypasses it",
    }
