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

# 3600, not 1800: this repo's own designated suite runs ~27 minutes on the
# reference machine, and a kill must never be mistaken for a failure.
SUITE_TIMEOUT_SECONDS = 3600
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

    # The worktree lives BESIDE the repo - the only location with a green
    # experiment behind it (3206 tests, 2026-09-04). The two special zones
    # both failed live: under the system temp dir the sentinel's scratch
    # allowance let protective assertions pass what they exist to block
    # (incident 8892), and under the repo's .git the same suite's
    # plain-file fixtures correctly classified as git-internals mutations.
    # A sibling directory is ordinary filesystem to every classifier.
    # Unwritable parent falls back to temp, with the reduced fidelity
    # named instead of hidden.
    try:
        scratch = Path(tempfile.mkdtemp(prefix=".godmode-preflight-",
                                        dir=str(repo.parent)))
    except OSError:
        scratch = Path(tempfile.mkdtemp(prefix="godmode-preflight-"))
        skipped.append(
            "worktree: repo parent unwritable, fell back to the system "
            "temp dir - scratch-allowance-sensitive suite assertions may "
            "read soft there")
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
        # THE RATCHET RULE, applied to this gate's own miss: three releases
        # went red in CI on stale pins because "run the full suite first"
        # lived as a lesson, and the suite hook here waited on a per-call
        # flag nobody passed. A designation recorded once
        # (`precheck --designate-suite "<cmd>"`) now runs on every
        # preflight of this project - the control survives forgetting.
        if not suite and archive is not None:
            try:
                for record in archive.select(kind="criterion", limit=200):
                    if record.get("subject") == "preflight-suite":
                        stored = (record.get("data") or {}).get("command")
                        if stored:
                            import shlex
                            suite = shlex.split(str(stored))
            except Exception:  # noqa: BLE001
                pass
        if suite:
            # 3600, not 1800: this repo's own designated suite runs ~27
            # minutes on the reference machine, and a timeout kill is
            # indistinguishable from a failure in the finding.
            try:
                run = subprocess.run(suite, cwd=worktree, capture_output=True,
                                     check=False, timeout=SUITE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as expired:
                # A timeout kill is a verdict, not a crash: round 7 of the
                # 0.3.18 gate died here as a bare traceback and the hour of
                # suite output behind it was lost with the process. The
                # partial output rides the exception; its tail is the only
                # witness to where the suite was when the clock ran out.
                partial = (expired.stderr or expired.stdout or b"")
                if isinstance(partial, str):
                    partial = partial.encode("utf-8", errors="replace")
                tail = partial[-600:].decode("utf-8", errors="replace").strip()
                judgment.append({
                    "check": "suite",
                    "detail": f"designated suite killed after "
                              f"{SUITE_TIMEOUT_SECONDS}s without a verdict - "
                              "a hang or a slow machine, and a person decides "
                              "which; run the suite with -v to name the test "
                              "it stopped in"
                              + (f"; last output: {tail[-300:]!r}" if tail else ""),
                })
                run = None
            if run is not None and run.returncode != 0:
                # The finding names its catch: "exit 1" alone trains a
                # 20-minute re-run to learn which test failed (first live
                # run of the ratchet, 2026-09-04). unittest writes verdicts
                # to stderr; the tail is where the summary lives.
                tail = (run.stderr or run.stdout or b"")[-20000:].decode(
                    "utf-8", errors="replace")
                lines = [ln for ln in tail.splitlines()
                         if ln.startswith(("FAIL", "ERROR", "Ran "))
                         or "Error" in ln][-8:]
                judgment.append({
                    "check": "suite",
                    "detail": f"designated suite exited exit {run.returncode}; "
                              "a person decides whether this state ships"
                              + (": " + " | ".join(lines) if lines else ""),
                })
        else:
            skipped.append(
                "suite: no command designated - pass --suite once, or record "
                "it durably: precheck --designate-suite \"<cmd>\"")
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
        # History-scope scan (field miss, 2026-09-02): a scrub that reads
        # the tree misses every deletion diff and old commit message - the
        # exposure surface is `log -p --all`, so that is what gets scanned.
        # Counts and commit ids only, never the term.
        if terms_path is not None:
            try:
                history = _git(repo, "log", "-p", "--all").stdout.decode(
                    "utf-8", errors="replace").lower()
                history_hits = sum(
                    1 for pattern in patterns if pattern.search(history))
                if history_hits:
                    mechanical.append({
                        "check": "history-terms",
                        "detail": f"{history_hits} private term(s) appear in "
                                  "commit HISTORY (diffs or messages) - the "
                                  "tree is not the exposure surface; a "
                                  "history rewrite is the only removal",
                    })
            except Exception:  # noqa: BLE001
                skipped.append("history-terms scan: unavailable")
    finally:
        _git(repo, "worktree", "remove", "--force", str(worktree))
        _git(repo, "worktree", "prune")

    # A cut over open operator asks is the goal-misread class as machinery
    # (recorded incident, 2026-09-03: an operator-named set was parked
    # inside a spec and the cut staged anyway). Every OPEN stated request
    # is a judgment finding: close it, or park it EXPLICITLY with the
    # operator's own words.
    if archive is not None:
        try:
            # Closure honouring lives in one place (open_stated_requests):
            # this gate's own latest-per-digest rebuild was blind to a
            # closure written from the command line, so the exact command
            # the finding prescribed closed nothing it could see
            # (field-caught at the 0.3.17 gate, 2026-09-04).
            from .godmode_requests import open_stated_requests
            open_asks = []
            for record in open_stated_requests(
                    archive.select(kind="request", limit=200)):
                data = record.get("data") or {}
                keywords = [str(w) for w in (data.get("keywords") or [])]
                open_asks.append(" ".join(keywords[:6]) or
                                 str(record.get("subject", "")))
            if open_asks:
                judgment.append({
                    "check": "open-operator-asks",
                    "detail": (f"{len(open_asks)} stated operator ask(s) "
                               "still open at the gate - a cut over an "
                               "operator-named set is the goal-misread "
                               "class; close each, or park it explicitly: "
                               + "; ".join(f"'{a}'" for a in open_asks[:3])),
                })
        except Exception:  # noqa: BLE001
            skipped.append("open-asks scan: unavailable")
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
