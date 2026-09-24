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

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
import time

# 3600, not 1800: this repo's own designated suite runs ~27 minutes on the
# reference machine, and a kill must never be mistaken for a failure.
SUITE_TIMEOUT_SECONDS = 3600

# The longest one test (or one class fixture) may run before it is taken for a
# hang. 2026-09-23: a shard stalled in its first minutes, sat at zero CPU, and
# the only verdict an hour later was "killed after 3600s" with no test named.
# The runner below re-arms Python's fault handler at every test boundary, so a
# stall dumps every thread's stack and exits after this long instead.
TEST_STALL_SECONDS = 600

# argv: <stall seconds> <module> ... ; re-arms on each start and stop, so class
# and module fixtures between tests are covered as well as the tests.
_WATCHDOG_RUNNER = (
    "import faulthandler, sys, unittest\n"
    "limit = float(sys.argv[1])\n"
    "class Result(unittest.TextTestResult):\n"
    "    def startTest(self, test):\n"
    "        faulthandler.dump_traceback_later(limit, exit=True)\n"
    "        super().startTest(test)\n"
    "    def stopTest(self, test):\n"
    "        super().stopTest(test)\n"
    "        faulthandler.dump_traceback_later(limit, exit=True)\n"
    "faulthandler.dump_traceback_later(limit, exit=True)\n"
    "unittest.main(module=None, argv=['unittest', *sys.argv[2:]],\n"
    "              testRunner=unittest.TextTestRunner(resultclass=Result))\n"
)


def watchdog_command(modules: list[str], stall_seconds: float = TEST_STALL_SECONDS) -> list[str]:
    """The shard command: unittest over `modules`, under the per-test watchdog."""
    import sys as _sys
    return [_sys.executable, "-c", _WATCHDOG_RUNNER, str(stall_seconds), *modules]


def stall_summary(stderr_text: str) -> str | None:
    """The stuck frames from a watchdog dump, innermost last; None when no
    stall fired. faulthandler writes `Timeout (h:mm:ss)!` then the stacks."""
    if "Timeout (" not in stderr_text:
        return None
    dump = stderr_text[stderr_text.rindex("Timeout ("):]
    frames = [line.strip() for line in dump.splitlines() if line.strip().startswith("File ")]
    tests = [f for f in frames if "tests" in f and ("/test_" in f.replace("\\", "/"))]
    return " <- ".join((tests or frames)[:4])
# 30 minutes: long enough that a concurrent run's half-built worktree is
# never mistaken for an abandoned one, short enough that a genuinely dead
# scratch dir does not sit beside the repo for a whole day.
STALE_SCRATCH_SECONDS = 30 * 60
from pathlib import Path
from typing import Any

from .godmode_errors import ArchiveError


def swallow_ratchet_finding(project: Path | str) -> dict[str, str] | None:
    """A file whose silent-handler count rose above its committed ceiling
    (obligation 10273). None when the tree holds the ratchet."""
    from .godmode_swallow import BASELINE_FILENAME, scan_project

    try:
        report = scan_project(Path(project))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unscannable tree is reported by the scanner's own verb, never as a gate crash
        return None
    regressions = report.get("regressions") or []
    if not regressions:
        return None
    named = "; ".join(f"{r['path']} {r['current']} > {r['baseline']}" for r in regressions[:4])
    more = f" (+{len(regressions) - 4} more)" if len(regressions) > 4 else ""
    return {
        "check": "swallow-ratchet",
        "detail": (f"{len(regressions)} file(s) above the committed swallow ceiling "
                   f"in {BASELINE_FILENAME}: {named}{more}. Handle the exception, "
                   "or mark a deliberate one `# godmode: swallow-ok: <reason>`; "
                   "the ceiling only ever falls"),
    }


def malformed_findings(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    """A finding whose `class` field is present-and-blank, or names
    something outside `FAILURE_CLASSES`, is itself a mechanical finding
    (N-12): a class that does not name a real class looks classified and
    is not - worse than carrying none. A finding with no `class` key at
    all is untouched; `class` stays optional."""
    from .godmode_mistakes import FAILURE_CLASSES

    malformed: list[dict[str, str]] = []
    for finding in findings:
        if "class" not in finding:
            continue
        value = finding.get("class")
        if value and value in FAILURE_CLASSES:
            continue
        malformed.append({
            "check": "malformed-finding",
            "detail": (f"{finding.get('check')} carries class {value!r}; "
                       f"allowed: {', '.join(FAILURE_CLASSES)}"),
        })
    return malformed


def pattern_workaround_findings(findings: list[dict[str, Any]], archive: Any) -> None:
    """NS-12e: a finding whose `class` names a recorded pattern's `subject`
    gets that pattern's workaround folded into its detail, in place.

    The vocabulary a preflight finding's `class` is drawn from
    (`FAILURE_CLASSES`) is the same one `godmode_mistakes.record_pattern`
    validates a pattern's own `class` against - but the MATCH here is
    against a pattern's `subject`, not its `class` field: a pattern
    recorded under `--subject "malformed-invocation"` is naming the whole
    bucket, and a later preflight finding of that class does not
    rediscover the workaround from scratch. Silent on no match, an
    unreadable archive, or a pattern with no workaround recorded - this is
    an enrichment, never a new failure mode of its own.
    """
    from .godmode_mistakes import list_patterns

    try:
        workarounds = {
            row["subject"]: row["workaround"]
            for row in list_patterns(archive) if row.get("workaround")
        }
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable pattern index leaves findings exactly as the caller built them
        return
    for finding in findings:
        cls = finding.get("class")
        workaround = workarounds.get(cls) if cls else None
        if not workaround:
            continue
        detail = str(finding.get("detail", ""))
        if workaround in detail:
            continue
        finding["detail"] = f"{detail} - known workaround (pattern '{cls}'): {workaround}"


def flake_findings(archive: Any) -> list[dict[str, str]]:
    """NS-8o: a registered flake retried three or more times with no lesson
    naming it is a judgment finding - the registry entry must then either
    gain a lesson cite or be removed. `retries < 3` or a matching lesson is
    silent: a lesson-or-leave rule, not a quota on retries themselves."""
    from .godmode_trends import flakes

    findings: list[dict[str, str]] = []
    for row in flakes(archive):
        if row["retries"] >= 3 and not row["has_lesson"]:
            findings.append({
                "check": "flake-without-lesson",
                "class": "environment-failure",
                "detail": (f"{row['test_id']} retried {row['retries']} time(s) isolated with no "
                           "lesson naming it - add a lesson cite to the registry entry, or "
                           "remove the entry"),
            })
    return findings


def _classes_tally(findings: list[dict[str, Any]]) -> dict[str, int]:
    """A count per class over the given findings - only entries whose
    `class` names a real `FAILURE_CLASSES` member; a malformed class is
    already reported as its own finding, not tallied here."""
    from .godmode_mistakes import FAILURE_CLASSES

    tally: dict[str, int] = {}
    for finding in findings:
        value = finding.get("class")
        if value in FAILURE_CLASSES:
            tally[value] = tally.get(value, 0) + 1
    return tally


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


WORKFLOW_FILE = Path(".github") / "workflows" / "godmode-verify.yml"
_RUN_LINE = re.compile(r"^\s*(?:-\s*)?run:\s*(?P<cmd>python\s.+?)\s*$")
_SKIP_GATE = re.compile(r"unittest discover|--version\b")
PUSH_SHAPED = re.compile(r"(?i)^\s*(?:git\s+push\b|gh\s+release\s+create\b)")


def workflow_gate_commands(repo: Path) -> list[str]:
    """Every single-line `run: python ...` step of the verify job, in order,
    except the suite (designated separately) and the version smoke. Read
    from the workflow file itself so a gate added there is a gate here
    (Codex audit of 37 red runs, 2026-09-10: most were steps only CI ran)."""
    path = Path(repo) / WORKFLOW_FILE
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[str] = []
    in_verify = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^[A-Za-z0-9_-]+:\s*$", stripped) and not line.startswith(" " * 4):
            in_verify = stripped == "verify:"
        if not in_verify:
            continue
        match = _RUN_LINE.match(line)
        if match and not _SKIP_GATE.search(match.group("cmd")):
            out.append(match.group("cmd"))
    # The composite action's job diffs HEAD~1 on every push (assertion diff,
    # skip quarantine, changelog fragment, release note); a commit it would
    # refuse is refused here first. Its default gates, in its order.
    if (Path(repo) / "action.yml").is_file():
        out.extend([
            "python scripts/godmode.py --project . integrity --base HEAD~1",
            "python scripts/godmode.py --project . changelog check --base HEAD~1",
            "python scripts/godmode.py --project . release-notes check",
        ])
    return out


def aliased_temp_environment() -> dict[str, str] | None:
    """The environment a CI runner gives a test: the temp directory under
    another spelling - its 8.3 short name (RUNNER~1 on Windows runners) or
    a symlinked root (/var -> /private/var on macOS). Four tests green on
    the reference machine went red on both runners for exactly this
    (2026-09-11), and that machine's volume keeps no short names, so the
    alias is a junction or symlink beside the temp directory when no short
    name exists. None only when no alias can be made; the shards then run
    as before, and the gate says nothing it cannot show."""
    import subprocess
    import tempfile
    long_form = tempfile.gettempdir()
    alias: str | None = None
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetShortPathNameW(long_form, buffer, 260) != 0:
            short = buffer.value
            if short and short.lower() != long_form.lower():
                alias = short
    if alias is None:
        link = Path(long_form) / "godmode-temp-alias"
        if not link.exists():
            try:
                os.symlink(long_form, str(link), target_is_directory=True)
            except (OSError, NotImplementedError):
                if os.name == "nt":
                    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), long_form],
                                   capture_output=True, check=False, timeout=30)
        if link.is_dir():
            alias = str(link)
    if alias is None:
        return None
    env = dict(os.environ)
    for key in ("TEMP", "TMP", "TMPDIR"):
        env[key] = alias
    return env


def shard_modules(tests_dir: Path, shards: int) -> list[list[str]]:
    names = sorted(f"tests.{p.stem}" for p in Path(tests_dir).glob("test_*.py"))
    return [names[i::shards] for i in range(max(1, shards))]


def _remote_ref(repo: Path) -> str:
    """The remote ref the current branch is measured against: its configured
    upstream, else `origin/<branch>` when that ref exists (this repository
    pushes with an explicit `git push origin main` and never set an
    upstream), else nothing - which means everything is unpushed."""
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream.returncode == 0 and upstream.stdout.strip():
        return upstream.stdout.decode("utf-8", errors="replace").strip()
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode("utf-8", errors="replace").strip()
    if branch and branch != "HEAD":
        candidate = f"origin/{branch}"
        if _git(repo, "rev-parse", "--verify", "--quiet", candidate).returncode == 0:
            return candidate
    return ""


def _head_sha(repo: Path) -> str:
    done = _git(repo, "rev-parse", "HEAD")
    return done.stdout.decode("utf-8", errors="replace").strip() if done.returncode == 0 else ""


def _head_tree(repo: Path) -> str:
    """The tree HEAD points at: a message-only rewrite keeps it, any file change moves it."""
    done = _git(repo, "rev-parse", "HEAD^{tree}")
    return done.stdout.decode("utf-8", errors="replace").strip() if done.returncode == 0 else ""


def _registered_worktrees(repo: Path) -> set[Path]:
    """Every worktree path `git worktree list` knows about for `repo`,
    resolved. A candidate's `head` matching one of these is registered
    to THIS repo - the strongest ownership signal there is."""
    listing = _git(repo, "worktree", "list", "--porcelain")
    if listing.returncode != 0:
        return set()
    out: set[Path] = set()
    for line in listing.stdout.decode("utf-8", errors="replace").splitlines():
        if line.startswith("worktree "):
            try:
                out.add(Path(line[len("worktree "):]).resolve())
            except OSError:
                continue
    return out


def _gitdir_target(pointer: Path) -> Path | None:
    """The path a worktree's `.git` gitdir-pointer file names, resolved.
    None when `pointer` is not such a file."""
    try:
        text = pointer.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.match(r"gitdir:\s*(.+?)\s*$", text.strip())
    if not match:
        return None
    target = Path(match.group(1))
    if not target.is_absolute():
        target = pointer.parent / target
    try:
        return target.resolve()
    except OSError:
        return None


def _owns_scratch_candidate(repo: Path, candidate: Path, registered: set[Path]) -> bool:
    """True when `candidate` is THIS repo's own preflight scratch, never
    a sibling repository's or a concurrent run's the sweep cannot
    identify.

    `candidate/head/.git` absent entirely means there is no ownership
    signal either way (an unregistered leftover, e.g. a `mkdtemp` that
    never reached `git worktree add`) - the caller decides ownership by
    age in that case, not this function. Otherwise ownership requires
    `head` to be a worktree registered to `repo` (`git worktree list`),
    or a gitdir pointer whose target resolves inside `repo`'s own
    `git rev-parse --git-common-dir` - a sibling repo's worktree has a
    `.git` pointer too, but it resolves into that OTHER repo's git dir.
    """
    head = candidate / "head"
    try:
        head_resolved = head.resolve()
    except OSError:
        head_resolved = head
    if head_resolved in registered:
        return True
    pointer = head / ".git"
    target = _gitdir_target(pointer)
    if target is None:
        return False
    common = _git(repo, "rev-parse", "--git-common-dir")
    if common.returncode != 0:
        return False
    common_dir = (repo / common.stdout.decode("utf-8", errors="replace").strip()).resolve()
    try:
        target.relative_to(common_dir)
        return True
    except ValueError:
        return False


def _candidate_mtime(candidate: Path) -> float | None:
    """The newest mtime of `candidate` or its `head` subdirectory - the
    signal liveness reads. None only when neither can be stat'd."""
    newest = None
    for probe in (candidate, candidate / "head"):
        try:
            mtime = probe.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def sweep_stale_scratch(repo: Path, keep: Path | None = None,
                        ) -> tuple[list[Path], list[Path], list[Path]]:
    """Remove every `.godmode-preflight-*` sibling of `repo` that this
    repo OWNS and that is NOT LIVE. `keep` is always skipped.

    Ownership: see `_owns_scratch_candidate`; a candidate with no
    `head/.git` at all has no ownership signal, so it counts as ours only
    once it also reads as old below - age is what a genuinely abandoned
    leftover has and a concurrent run's half-built scratch does not.

    Liveness: a candidate whose newest mtime (`_candidate_mtime`) is
    younger than `STALE_SCRATCH_SECONDS` is skipped outright, even one
    this repo owns - a concurrent run of the SAME repo is never swept
    out from under itself.

    A registered worktree under a swept dir is removed through git so
    the worktree list stays consistent; an unregistered leftover is
    deleted directly. Returns `(removed, unswept, skipped)`: `skipped` is
    every foreign or live candidate left untouched on purpose; a
    candidate is only ever reported removed once it is confirmed gone
    from disk - a plain file, or a locked or read-only directory
    `rmtree(ignore_errors=True)` could not touch, lands in `unswept`
    instead, the same way `cleanup` states an unconfirmed removal rather
    than assuming it.
    """
    removed: list[Path] = []
    unswept: list[Path] = []
    skipped: list[Path] = []
    parent = repo.resolve().parent
    registered = _registered_worktrees(repo)
    now = time.time()
    for candidate in sorted(parent.glob(".godmode-preflight-*")):
        if keep is not None and candidate.resolve() == keep.resolve():
            continue
        mtime = _candidate_mtime(candidate)
        if mtime is not None and (now - mtime) < STALE_SCRATCH_SECONDS:
            skipped.append(candidate)
            continue
        has_ownership_signal = (candidate / "head" / ".git").exists()
        owned = True if not has_ownership_signal else _owns_scratch_candidate(repo, candidate, registered)
        if not owned:
            skipped.append(candidate)
            continue
        head = candidate / "head"
        if head.exists():
            _git(repo, "worktree", "remove", "--force", str(head))
        shutil.rmtree(candidate, ignore_errors=True)
        if candidate.exists():
            unswept.append(candidate)
        else:
            removed.append(candidate)
    _git(repo, "worktree", "prune")
    return removed, unswept, skipped


def _ci_push_branches(repo: Path) -> list[str]:
    """The `on: push: branches:` globs of the committed verify workflow, main excluded."""
    path = repo / ".github" / "workflows" / "godmode-verify.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    found = re.search(r"^  push:\s*\n\s+branches:\s*\[([^\]]*)\]", text, re.M)
    names = [n.strip().strip("'\"") for n in found.group(1).split(",")] if found else []
    return [n for n in names if n and n not in ("main", "master")]


def ci_verified_branch_push(repo: Path, operation: str) -> bool:
    """A plain push to a work branch CI runs on: CI is its check, so no local
    preflight is required before staging it. main, tags, forced pushes, deletes
    and chained commands keep the preflight."""
    if re.search(r"[;&|<>`$()\n]", operation):
        return False
    tokens = operation.split()
    if tokens[:2] != ["git", "push"] or len(tokens) < 4:
        return False
    if any(t.startswith("-") for t in tokens[2:]):
        return False
    globs = _ci_push_branches(repo)
    for spec in tokens[3:]:
        if spec.startswith("+") or spec.startswith(":"):
            return False
        dest = spec.split(":")[-1].removeprefix("refs/heads/")
        if dest.startswith("refs/") or not any(fnmatch.fnmatchcase(dest, g) for g in globs):
            return False
    return True


def preflight_gate(archive: Any, project: Path, operation: str) -> str | None:
    """The reason a push-shaped operation may not be staged: no green
    preflight attestation at the current HEAD. None when one exists or
    the operation is not push-shaped."""
    if archive is None or not PUSH_SHAPED.match(str(operation or "")):
        return None
    if ci_verified_branch_push(Path(project), str(operation)):
        return None
    head = _head_sha(Path(project))
    tree = _head_tree(Path(project))
    newest = None
    for record in archive.select(kind="attestation", limit=1000):
        if str(record.get("subject", "")) == "preflight":
            newest = record
    data = (newest or {}).get("data") or {}
    # R2: the verdict is keyed on the tree, so a reworded or squashed commit with
    # the same files reuses it. Records written before the tree was kept match on HEAD.
    same = (str(data.get("tree", "")) == tree) if data.get("tree") else (str(data.get("head", "")) == head)
    if newest is not None and data.get("status") == "ran" and same:
        return None
    seen = (f"newest preflight is {data.get('status')} at {str(data.get('head', ''))[:7]}" if newest
            else "no preflight attestation on record")
    return (f"{seen}; HEAD is {head[:7]}. Run `godmode precheck --preflight --suite-shards 4` and stage "
            "again, or `authorize stage --without-preflight \"<reason>\"` (recorded)")


def push_preflight(project: Path | str,
                   suite: list[str] | None = None,
                   archive: Any = None,
                   dirty: bool = False,
                   suite_shards: int = 1,
                   shard_index: int | None = None,
                   session: str | None = None) -> dict[str, Any]:
    repo = Path(project)
    # A shard index is a usage error before it is anything else, so it is
    # refused before a worktree exists to clean up. Out of range is named,
    # never clamped: a CI leg asking for shard 4 of 4 has a broken matrix,
    # and silently running shard 3 twice would report a green that skipped
    # a quarter of the suite.
    shards_total = max(1, int(suite_shards or 1))
    if shard_index is not None and not 0 <= int(shard_index) < shards_total:
        raise ArchiveError(
            f"preflight refuses shard index {shard_index}: with --suite-shards "
            f"{shards_total} the only indices are 0 to {shards_total - 1} - "
            "every shard must run for the suite to have run"
        )
    status = _git(repo, "status", "--porcelain=v1")
    if status.returncode != 0:
        raise ArchiveError("preflight needs a git repository")
    # Field report 22 (2026-09-09): "preflight only runs on a committed
    # tree, so here it can only run after the owner's gated commit". With
    # `dirty=True` the gate validates a snapshot of the working tree's
    # tracked changes (`git stash create`, which leaves the tree untouched)
    # instead of HEAD; the report names which one it validated.
    validated = "HEAD"
    ref = "HEAD"
    # Only TRACKED changes make a tree dirty here. The disposable worktree is
    # built from HEAD or a stash snapshot, and untracked files are in neither,
    # so an untracked-only tree validates exactly what a clean one does;
    # refusing it blocked every run behind stray scratch files while
    # protecting nothing. Untracked files are still named in `skipped` below.
    tracked_changes = [
        line for line in status.stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip() and not line.startswith("??")
    ]
    if tracked_changes:
        if not dirty:
            raise ArchiveError(
                "preflight refuses a dirty tree: it validates a committed state, "
                "and a dirty tree is not a state anyone can push - commit or "
                "stash first, or pass --dirty to validate a snapshot of the "
                "working tree's tracked changes"
            )
        snapshot = _git(repo, "stash", "create")
        sha = snapshot.stdout.decode("utf-8", errors="replace").strip()
        if snapshot.returncode == 0 and sha:
            ref = sha
            validated = f"working-tree snapshot {sha[:12]}"
        else:
            validated = "HEAD (the tree had no tracked changes to snapshot)"

    mechanical: list[dict[str, Any]] = []
    judgment: list[dict[str, Any]] = []
    skipped: list[str] = []
    # Which shards this process actually ran, so a report never implies the
    # whole suite when one leg of a fan-out is what happened.
    ran_shards: list[int] = []
    if status.stdout.strip() and any(line.startswith("??") for line in
                                     status.stdout.decode("utf-8", errors="replace").splitlines()):
        skipped.append("untracked files are not in the snapshot: `git add -N` "
                       "them or commit first for full fidelity")

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
    # An aborted earlier run leaves its scratch worktree beside the repo;
    # its own `cleanup: confirmed` only ever checked the dir it made, never
    # its siblings. Sweep them before this run so the report can cite them.
    swept, unswept, skipped_scratch = sweep_stale_scratch(repo, keep=scratch)
    worktree = scratch / "head"
    added = _git(repo, "worktree", "add", "--detach", str(worktree), ref)
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
        # The swallow ratchet (obligation 10273): a file whose count of
        # silent exception handlers rose above its committed ceiling is a
        # mechanical finding. The scanner and its baseline existed; nothing
        # at this gate read them.
        ratchet = swallow_ratchet_finding(worktree)
        if ratchet is not None:
            ratchet.setdefault("class", "blocked-by-guard")
            mechanical.append(ratchet)
        # THE RATCHET RULE, applied to this gate's own miss: three releases
        # went red in CI on stale pins because "run the full suite first"
        # lived as a lesson, and the suite hook here waited on a per-call
        # flag nobody passed. A designation recorded once
        # (`precheck --designate-suite "<cmd>"`) now runs on every
        # preflight of this project - the control survives forgetting.
        if not suite and archive is not None:
            try:
                # The designation is old by design (recorded once); a small
                # newest-N window missed it on 2026-09-10 and the gate ran
                # with no suite, attesting a green it never earned.
                for record in archive.read_events():
                    if record.get("kind") == "criterion" and record.get("subject") == "preflight-suite":
                        stored = (record.get("data") or {}).get("command")
                        if stored:
                            import shlex
                            suite = shlex.split(str(stored))
            except Exception:  # noqa: BLE001  # godmode: swallow-ok: deliberate broad handler: this boundary never raises into the host
                pass
        # One argument carrying the whole command is the shape a designation
        # is stored in (above), and the shape a YAML `run:` line can pass
        # without argparse reading `-m` as an option of its own. Split it the
        # same way, so `--suite "python -m unittest discover"` and
        # `--designate-suite "python -m unittest discover"` mean one thing.
        if suite and len(suite) == 1 and " " in suite[0]:
            import shlex
            suite = shlex.split(suite[0])
        suite_designated = bool(suite)
        if suite and (shards_total > 1 or shard_index is not None) and "discover" in " ".join(suite):
            # One process over 3,400 tests is killed for memory on the
            # reference machine; N sequential shards finish. Each shard's
            # verdict names its own tests.
            import sys as _sys
            for index, modules in enumerate(shard_modules(worktree / "tests", shards_total)):
                # One index means one leg of a fan-out: the caller (a CI
                # matrix) runs the others in parallel, and the aggregate of
                # the legs is the suite. The deal is deterministic for a
                # given tree, so index 2 of 4 is the same modules wherever
                # it runs.
                if shard_index is not None and index != int(shard_index):
                    continue
                if not modules:
                    continue
                ran_shards.append(index)
                try:
                    shard = subprocess.run(watchdog_command(modules), cwd=worktree,
                                           capture_output=True, check=False, timeout=SUITE_TIMEOUT_SECONDS,
                                           env=aliased_temp_environment())
                except subprocess.TimeoutExpired:
                    judgment.append({"check": "suite", "class": "environment-failure",
                                     "detail": f"shard {index} killed after "
                                               f"{SUITE_TIMEOUT_SECONDS}s without a verdict"})
                    break
                if shard.returncode != 0:
                    # Every shard runs: one gate round names every red test
                    # instead of the first shard's, so the next round is
                    # the green one rather than the next discovery.
                    tail = (shard.stderr or shard.stdout or b"")[-40000:].decode("utf-8", errors="replace")
                    stalled = stall_summary(tail)
                    if stalled:
                        judgment.append({"check": "suite", "class": "environment-failure",
                                         "detail": f"suite shard {index} stalled: one test ran past "
                                                   f"{TEST_STALL_SECONDS}s and the watchdog stopped "
                                                   f"it; stuck at {stalled}"})
                        continue
                    lines = [ln for ln in tail.splitlines() if ln.startswith(("FAIL", "ERROR", "Ran "))][-12:]
                    judgment.append({"check": "suite",
                                     "detail": f"suite shard {index} exited {shard.returncode}"
                                               + (": " + " | ".join(lines) if lines else "")})
            run = None
            suite = None  # the sharded run stands in for the single process below
            suite_designated = True
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
                text = partial.decode("utf-8", errors="replace")
                tail = text[-600:].strip()
                # unittest's quiet stream is one mark per test; the count
                # says how far the suite got before the clock did (round 8
                # reported 300 dots and nothing else - a tail with no
                # position in it).
                completed = sum(len(m) for m in re.findall(r"[.FEsx]{5,}", text))
                judgment.append({
                    "check": "suite",
                    "class": "environment-failure",
                    "detail": f"designated suite killed after "
                              f"{SUITE_TIMEOUT_SECONDS}s without a verdict - "
                              "a hang or a slow machine, and a person decides "
                              "which; run the suite with -v to name the test "
                              "it stopped in"
                              + (f"; about {completed} quiet-mode test marks "
                                 "before the kill" if completed else "")
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
        elif not suite_designated:
            skipped.append(
                "suite: no command designated - pass --suite once, or record "
                "it durably: precheck --designate-suite \"<cmd>\"")
        # The workflow's own gates, in the worktree, first red stops. These
        # are the steps only CI ran before 2026-09-10. A history-terms or
        # open-ask finding is about the past or the record; the gates are
        # about the tree, so only a red suite skips them.
        if not any(j.get("check") == "suite" for j in judgment):
            import sys as _sys
            for command in workflow_gate_commands(repo):
                argv = command.split()
                if argv and argv[0] == "python":
                    argv[0] = _sys.executable
                try:
                    gate = subprocess.run(argv, cwd=worktree, capture_output=True, check=False, timeout=900)
                except (OSError, subprocess.SubprocessError) as exc:
                    mechanical.append({"check": "workflow-gate", "detail": f"{command}: {exc.__class__.__name__}"})
                    break
                if gate.returncode != 0:
                    tail = (gate.stdout or gate.stderr or b"")[-400:].decode("utf-8", errors="replace").strip()
                    mechanical.append({"check": "workflow-gate",
                                       "detail": f"{command} exited {gate.returncode}: {tail[-200:]}"})
                    break
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
                # Split by range (2026-09-10): a term in an UNPUSHED commit is
                # mechanical - rewrite before the push. A term only in history
                # that is already on the remote is a standing judgment: the
                # scrub is the operator's, and it must not turn every gate red
                # forever while nothing new leaks.
                remote_ref = _remote_ref(repo)
                history = _git(repo, "log", "-p", "--all").stdout.decode(
                    "utf-8", errors="replace").lower()
                if remote_ref:
                    unpushed = _git(repo, "log", "-p", f"{remote_ref}..HEAD").stdout.decode(
                        "utf-8", errors="replace").lower()
                else:
                    # No upstream: nothing is on any remote, so every hit is
                    # unpushed and mechanical.
                    unpushed = history
                unpushed_hits = sum(1 for pattern in patterns if unpushed and pattern.search(unpushed))
                history_hits = sum(1 for pattern in patterns if pattern.search(history))
                if unpushed_hits:
                    mechanical.append({
                        "check": "history-terms",
                        "detail": f"{unpushed_hits} private term(s) appear in commits not yet on "
                                  f"{remote_ref} (diffs or messages) - rewrite those commits before "
                                  "the push; the tree is not the exposure surface",
                    })
                elif history_hits:
                    judgment.append({
                        "check": "history-terms-pushed",
                        "detail": f"{history_hits} private term(s) appear in history already on the "
                                  "remote and in no unpushed commit - standing; a history rewrite is "
                                  "the only removal and it is the operator's call",
                    })
            except Exception:  # noqa: BLE001
                skipped.append("history-terms scan: unavailable")
    finally:
        _git(repo, "worktree", "remove", "--force", str(worktree))
        _git(repo, "worktree", "prune")
        # The mkdtemp parent outlived the worktree it held (rounds 7 and 8
        # each left an empty `.godmode-preflight-*` beside the repo).
        shutil.rmtree(scratch, ignore_errors=True)

    # A cut over open operator asks is the goal-misread class as machinery
    # (recorded incident, 2026-09-03: an operator-named set was parked
    # inside a spec and the cut staged anyway). Every OPEN stated request
    # is a judgment finding: close it, or park it EXPLICITLY with the
    # operator's own words.
    # R1 "enforce harm, advise on quality": the archive-scan findings below
    # are local bookkeeping (open asks, host reach, stale claims, flake and
    # falsifier aging) that CI never sees - in the default advise mode they
    # report, they do not fail the gate. The slice recorded here is marked
    # advisory right after the scan, once, below.
    _archive_scan_start = len(judgment)
    if archive is not None:
        try:
            # Closure honouring lives in one place (open_stated_requests),
            # read through the one shared window (Task 2, 0.3.28): this
            # gate used to ask for its own, shorter tail of request
            # records than the other readers did, so a busy session could
            # already have this ask fall out of the gate's view while it
            # stayed open everywhere else.
            from .godmode_requests import open_stated_requests, read_request_window
            open_asks = []
            _requests, _window_overflow = read_request_window(archive)
            for record in open_stated_requests(_requests):
                data = record.get("data") or {}
                keywords = [str(w) for w in (data.get("keywords") or [])]
                open_asks.append(" ".join(keywords[:6]) or
                                 str(record.get("subject", "")))
            if open_asks:
                judgment.append({
                    "check": "open-operator-asks",
                    "class": "underspecified-ask",
                    "detail": (f"{len(open_asks)} stated operator ask(s) "
                               "still open at the gate - a cut over an "
                               "operator-named set is the goal-misread "
                               "class; close each, or park it explicitly: "
                               + "; ".join(f"'{a}'" for a in open_asks[:3])),
                    "window_overflow": _window_overflow,
                })
        except Exception:  # noqa: BLE001
            skipped.append("open-asks scan: unavailable")
        # Feature reach (2026-09-09, obligation 10119): a declared hook host
        # with no interception proof on this archive is a finding, not
        # silence - "unverifiable" was green over the host-reach gap for
        # twenty releases.
        try:
            from .godmode_reach import reach_finding
            finding = reach_finding(archive)
            if finding is not None:
                finding.setdefault("class", "capability-gap")
                judgment.append(finding)
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: a scan that cannot run is named in skipped, never a gate crash
            skipped.append("host-reach scan: unavailable")
        # Grounded claims (obligation 10248): a claim whose cited evidence
        # changed or vanished since it was recorded is a judgment finding.
        try:
            from .godmode_attest import stale_claims
            stale = stale_claims(archive, Path(project))
            if stale:
                # Q6 (review): a `tree-changed` entry's `citation` is empty
                # (no single citation is at fault, the whole tree moved) -
                # rendered bare, never with the stray leading space an
                # unconditional `f"{citation} {reason}"` left behind.
                named = "; ".join(
                    f"seq {s['sequence']} ({(s['citation'] + ' ') if s['citation'] else ''}{s['reason']})"
                    for s in stale[:3])
                judgment.append({
                    "check": "stale-claims",
                    "class": "invented-information",
                    "detail": (f"{len(stale)} claim(s) cite evidence that changed or "
                               f"vanished since they were recorded: {named}. "
                               "`godmode claim --stale` lists them; re-record or "
                               "resolve each superseded before the record is trusted"),
                })
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: a scan that cannot run is named in skipped, never a gate crash
            skipped.append("stale-claims scan: unavailable")
        # NS-8o: a registered flake retried three or more times with no
        # lesson naming it - the lesson-or-leave rule for the registry.
        try:
            judgment.extend(flake_findings(archive))
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: a scan that cannot run is named in skipped, never a gate crash
            skipped.append("flake-ranking scan: unavailable")
        # I-3: a hypothesis claim's or an incident's falsifier aged past
        # two days with nothing run behind it - the theory stands on
        # exactly as much today as the day it was written.
        try:
            from .godmode_falsifiers import falsifier_stale_findings
            judgment.extend(falsifier_stale_findings(archive))
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: a scan that cannot run is named in skipped, never a gate crash
            skipped.append("falsifier-aging scan: unavailable")
        # NS-12e: a finding's class matched against a recorded pattern's
        # subject - the workaround named the last time this class fired,
        # so a recurring failure is not rediscovered from scratch.
        try:
            pattern_workaround_findings(mechanical + judgment, archive)
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: a scan that cannot run is named in skipped, never a gate crash
            skipped.append("pattern-workaround scan: unavailable")
        # R1: in advise mode (the default) the archive-scan findings above
        # are quality bookkeeping, not harm - they still get reported, they
        # just never fail the gate on their own. `strict` mode is untouched.
        from .godmode_projectmode import project_mode
        if project_mode(archive) == "advise":
            for _finding in judgment[_archive_scan_start:]:
                _finding.setdefault("severity", "advisory")
    # N-12: a class that does not name a real class (blank, or outside
    # FAILURE_CLASSES) is itself a mechanical finding - checked over both
    # buckets before the fold below, so a malformed class in a judgment
    # finding still turns the verdict.
    mechanical.extend(malformed_findings(mechanical + judgment))
    # An advisory-severity judgment finding (host-reach: a hook host whose
    # path is replicated from a code-level read and pinned by a test, not
    # yet confirmed live) is reported, not failing - it is skipped from the
    # failing set. A finding with no declared severity, or one that is
    # itself "blocking", still turns the verdict.
    failing_judgment = []
    for f in judgment:
        if f.get("severity") == "advisory":
            continue
        failing_judgment.append(f)
    verdict = "findings" if mechanical or failing_judgment else "clean"
    suite_skipped = any(str(item).startswith("suite:") for item in skipped)
    if suite_skipped and verdict == "clean":
        verdict = "incomplete"
    if archive is not None:
        # The attestation `authorize stage` reads before it stages a push.
        # A preflight that ran no suite attests `incomplete`, never `ran`.
        try:
            suite_red = any(j.get("check") == "suite" for j in judgment)
            if suite_skipped:
                status = "incomplete"
            elif shard_index is not None and len(ran_shards) < shards_total:
                # One leg of a fan-out is not the suite. `authorize stage`
                # reads `ran` and nothing else, so a single shard attests
                # `incomplete`: the aggregate of the legs is the operator's
                # to judge, and a quarter of the suite must never stage a
                # push on its own.
                status = "incomplete"
            elif mechanical or suite_red:
                status = "failed"
            else:
                # Judgment findings (open asks, host reach, stale claims, standing
                # history terms) are the operator's to weigh at the password; the
                # attestation records them and does not hide behind them.
                status = "ran"
            archive.append("attestation", "preflight", {
                "status": status,
                "judgment": [str(j.get("check")) for j in judgment][:8],
                "session": session or "",
                "head": _head_sha(repo), "tree": _head_tree(repo), "validated": validated,
                "shards": shards_total, "shards_ran": list(ran_shards),
                "findings": len(mechanical) + len(judgment), "gates": len(workflow_gate_commands(repo)),
                "classes": _classes_tally(mechanical + judgment),
            }, evidence=[])
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: the report still prints; the gate simply finds no attestation
            pass
    return {
        "mechanical": mechanical,
        "judgment": judgment,
        "skipped": skipped,
        "verdict": verdict,
        "suite_ran": not suite_skipped and not any(j.get("check") == "suite" for j in judgment),
        "validated": validated,
        "shards": shards_total,
        "shards_ran": ran_shards,
        # The effect of a control action is confirmed, never assumed: the
        # cleanup claim is checked against the filesystem, and an
        # unconfirmed removal is stated rather than silently believed.
        "cleanup": "confirmed" if not worktree.exists() else "unconfirmed",
        "swept_stale_scratch": [p.name for p in swept],
        "unswept_scratch": [p.name for p in unswept],
        "skipped_scratch": [p.name for p in skipped_scratch],
        "feeds": "the password gate; preflight never bypasses it",
    }
