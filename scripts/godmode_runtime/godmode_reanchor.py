"""B5-B: finding citations that stopped meaning what they meant.

A claim graded `verified` because `file:src/api.py` resolved keeps that
grade for the life of the archive. The grade was true about the file as it
stood that day, and nothing re-reads it when the file changes - so a later
session inherits full confidence about a state that no longer exists.

Two ways a citation comes loose:

* **The file moved on.** A commit touching the cited path that landed
  after the record was written means the evidence readable now is not the
  evidence that was graded then.
* **The commit vanished.** A rebase, squash or history scrub leaves a
  `commit:` citation pointing at an unreachable object. Not hypothetical
  here: this project has a history scrub planned, and it will orphan every
  commit citation in the archive unless they are re-anchored first.

**Detected, never regraded.** A stale citation means "look at this again",
which is a different fact from "the evidence never supported it". Silently
downgrading on staleness would cry wolf over every file legitimately
edited later; silently keeping the grade hides the drift. So this module
only ever reports, and `regraded` is a constant False the report states
out loud rather than a behaviour a reader has to infer.

No new field and no schema change: `recorded_at` is already on every
record, so this works retroactively across an archive written long before
the check existed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# Kinds whose citations are load-bearing enough to be worth re-anchoring.
# A `refusal` cites the command it stopped, which does not decay the same
# way, so the default stays on the record kinds that assert something.
DEFAULT_KINDS = ("claim", "verdict", "attestation", "invariant")

# Kinds that assert something still true, as against kinds that record an
# act. A claim or verdict is either right or wrong today; an attestation
# says "at this time I performed this step citing this file", and a later
# edit to that file does not falsify the act - the evidence simply moved.
# The split exists because of the proportions: on this project 85 stale
# citations included 80 attestations, and the five standing assertions that
# could actually be wrong were buried in them. One of those five WAS wrong.
STANDING_KINDS = frozenset({"claim", "verdict", "invariant"})

_GIT_TIMEOUT = 30


def _git(project: Path, *arguments: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ("git",) + arguments, cwd=str(project),
            capture_output=True, text=True, timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # No git binary, or a repository that will not answer. Reported as
        # "cannot tell" by the caller rather than as an all-clear.
        return 1, ""
    return result.returncode, result.stdout


def is_git_project(project: Path) -> bool:
    code, _ = _git(project, "rev-parse", "--git-dir")
    return code == 0


def _citation_path(citation: str) -> str | None:
    """`file:src/api.py` -> `src/api.py`; a trailing line number is dropped.

    Citations are written by hand as often as by tooling, so both
    separators appear; normalising here keeps the comparison against git's
    always-forward-slash output honest on Windows.
    """
    if not citation.startswith("file:"):
        return None
    remainder = citation[len("file:"):].strip()
    # A trailing `:12` is a line anchor, not part of the path.
    head, separator, tail = remainder.rpartition(":")
    if separator and tail.isdigit():
        remainder = head
    return remainder.replace("\\", "/").lstrip("./") or None


def _last_touched(project: Path) -> dict[str, datetime]:
    """path -> when its newest commit landed, in ONE git pass.

    One subprocess per citation would be hundreds of process spawns on a
    real archive; git already walks history once and can name the paths
    each commit touched. Log order is newest-first, so the first sighting
    of a path is its most recent change and later sightings are ignored.
    """
    code, output = _git(
        project, "log", "--format=@@%cI", "--name-only", "--no-renames")
    if code != 0:
        return {}
    touched: dict[str, datetime] = {}
    current: datetime | None = None
    for line in output.splitlines():
        if line.startswith("@@"):
            try:
                current = datetime.fromisoformat(line[2:].strip())
            except ValueError:
                current = None
            continue
        name = line.strip()
        if not name or current is None:
            continue
        touched.setdefault(name.replace("\\", "/"), current)
    return touched


def _recorded_at(record: dict[str, Any]) -> datetime | None:
    raw = record.get("recorded_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _records(archive: Chronicle, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return []
    return [r for r in events if r.get("kind") in kinds]


def stale_records(archive: Chronicle, project: Path, *,
                  kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Records whose cited files were committed after the record was written."""
    project = Path(project)
    touched = _last_touched(project)
    if not touched:
        return []
    findings: list[dict[str, Any]] = []
    for record in _records(archive, kinds or DEFAULT_KINDS):
        written = _recorded_at(record)
        if written is None:
            continue
        for citation in record.get("evidence") or []:
            path = _citation_path(str(citation))
            if path is None:
                continue
            changed = touched.get(path)
            # Git stamps a commit in whole seconds; `recorded_at` carries
            # microseconds. Comparing them raw makes a commit that landed
            # later in the same second look earlier than the record. Both
            # sides are truncated so the comparison comes from one clock
            # resolution, and a tie stays quiet: within a single second the
            # order is genuinely unknown, and this is an advisory read over
            # hundreds of citations, where a false alarm on every record
            # written next to a commit costs more than a one-second blind
            # spot.
            if changed is None or changed.replace(microsecond=0) <= written.replace(
                    microsecond=0):
                continue
            findings.append({
                "sequence": record.get("sequence"),
                "kind": record.get("kind"),
                "subject": record.get("subject"),
                "citation": str(citation),
                "recorded_at": record.get("recorded_at"),
                "changed_at": changed.isoformat(),
                "standing": record.get("kind") in STANDING_KINDS,
                "reason": ("the cited file was committed after this record "
                           "was written, so the evidence readable now is not "
                           "the evidence that was graded then"),
            })
    return findings


def unreachable_commit_citations(archive: Chronicle, project: Path, *,
                                 kinds: tuple[str, ...] | None = None,
                                 ) -> list[dict[str, Any]]:
    """`commit:` citations naming an object this repository no longer has."""
    project = Path(project)
    if not is_git_project(project):
        return []
    findings: list[dict[str, Any]] = []
    # Read once: reachability is a property of the whole ref graph, and
    # asking per citation would re-walk it for every one of them.
    known = reachable_commits(project)
    resolved: dict[str, bool] = {}
    for record in _records(archive, kinds or DEFAULT_KINDS):
        for citation in record.get("evidence") or []:
            text = str(citation)
            if not text.startswith("commit:"):
                continue
            sha = text[len("commit:"):].strip()
            if not sha:
                continue
            if sha not in resolved:
                resolved[sha] = _reachable_commit(project, sha, known)
            if resolved[sha]:
                continue
            findings.append({
                "sequence": record.get("sequence"),
                "kind": record.get("kind"),
                "subject": record.get("subject"),
                "commit": sha,
                "reason": ("the cited commit is not reachable in this "
                           "repository; a rebase, squash or history rewrite "
                           "replaced it"),
            })
    return findings


# A scrub rewrites shas and keeps what a commit *is*: the tree it produced,
# its subject, and when its author wrote it. That triple is the durable
# identity, so it is what gets snapshotted before a rewrite and matched
# against afterwards. The committer date is deliberately NOT part of it -
# a rewrite is exactly what changes it.
_SNAPSHOT_PREFIX = "anchor:commit:"
_REMAP_PREFIX = "anchor:remap:"


def commit_fingerprint(project: Path, commit: str) -> dict[str, str] | None:
    """What a commit is, independent of its sha. None when unreachable."""
    code, output = _git(
        Path(project), "show", "--no-patch",
        "--format=%T%n%s%n%aI", f"{commit}^{{commit}}")
    if code != 0:
        return None
    parts = output.splitlines()
    if len(parts) < 3:
        return None
    return {"tree": parts[0].strip(), "subject": parts[1].strip(),
            "author_date": parts[2].strip()}


def _cited_commits(archive: Chronicle,
                   kinds: tuple[str, ...] | None = None) -> list[str]:
    """Every `commit:` citation, across EVERY record kind by default.

    Deliberately not `DEFAULT_KINDS`. That set scopes *staleness*, where
    only a record asserting something can decay. Preservation is a
    different question: a rewrite orphans a citation wherever it sits. On
    this project all 34 commit citations live on `checkpoint`, `sprint`,
    `lesson` and `decision` records and none on the asserting kinds, so
    reusing the staleness scope here snapshotted nothing at all.
    """
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return []
    if kinds is not None:
        events = [r for r in events if r.get("kind") in kinds]
    seen: list[str] = []
    for record in events:
        for citation in record.get("evidence") or []:
            text = str(citation)
            if not text.startswith("commit:"):
                continue
            # `commit:<sha> some words` is a real shape here - citations
            # are hand-written as often as generated, and sequence 83
            # carries `commit:c5fa933 CI green`. Taking the whole remainder
            # as a sha reported a reachable commit as unrecoverable, a
            # false alarm in the one report that must not cry wolf before
            # a scrub.
            sha = text[len("commit:"):].strip().split()[0] if text[
                len("commit:"):].strip() else ""
            if sha and sha not in seen:
                seen.append(sha)
    return seen


def _subjects_with_prefix(archive: Chronicle, prefix: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return found
    for record in events:
        subject = str(record.get("subject", ""))
        if record.get("kind") == "decision" and subject.startswith(prefix):
            found[subject[len(prefix):]] = record.get("data") or {}
    return found


def snapshot_commit_citations(archive: Chronicle, project: Path, *,
                              kinds: tuple[str, ...] | None = None,
                              ) -> dict[str, Any]:
    """Record what each cited commit IS, before a rewrite takes its sha.

    Run this BEFORE a history scrub. Afterwards the sha is gone and there
    is nothing left to fingerprint, which is the whole reason this is a
    prerequisite rather than a follow-up.
    """
    project = Path(project)
    existing = _subjects_with_prefix(archive, _SNAPSHOT_PREFIX)
    snapshotted = 0
    already = 0
    unreachable: list[str] = []
    for sha in _cited_commits(archive, kinds):
        if sha in existing:
            already += 1
            continue
        fingerprint = commit_fingerprint(project, sha)
        if fingerprint is None:
            # Already gone. Nothing to record, and saying so is the honest
            # answer - a snapshot invented now would describe nothing.
            unreachable.append(sha)
            continue
        archive.append("decision", f"{_SNAPSHOT_PREFIX}{sha}", fingerprint,
                       evidence=[f"commit:{sha}"])
        snapshotted += 1
    return {
        "snapshotted": snapshotted,
        "already": already,
        "unreachable": unreachable,
        "note": ("run before a history rewrite; afterwards the sha is gone "
                 "and there is nothing left to fingerprint"),
    }


def remap_commit_citations(archive: Chronicle, project: Path, *,
                           kinds: tuple[str, ...] | None = None,
                           ) -> dict[str, Any]:
    """After a rewrite, find each snapshotted commit's new sha.

    Searches history for a commit whose tree, subject and author date match
    the snapshot. The mapping is recorded, so a later session reads it back
    instead of re-deriving it against a history that may move again.
    """
    project = Path(project)
    snapshots = _subjects_with_prefix(archive, _SNAPSHOT_PREFIX)
    mapped = _subjects_with_prefix(archive, _REMAP_PREFIX)
    remapped: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []
    already: list[dict[str, str]] = []
    known = reachable_commits(project)
    for sha in _cited_commits(archive, kinds):
        if sha in mapped:
            already.append({"old": sha, "new": str(mapped[sha].get("new", ""))})
            continue
        if _reachable_commit(project, sha, known):
            continue
        fingerprint = snapshots.get(sha)
        if not fingerprint:
            # No snapshot means nothing recorded what this sha pointed at.
            # Unrecoverable, and reported as such rather than guessed at.
            unresolved.append({
                "old": sha,
                "reason": ("no snapshot was taken before the rewrite, so "
                           "nothing records what this commit was"),
            })
            continue
        found = _find_by_fingerprint(project, fingerprint)
        if found is None:
            unresolved.append({
                "old": sha,
                "reason": ("snapshot exists but no commit in this history "
                           "matches its tree, subject and author date"),
            })
            continue
        archive.append("decision", f"{_REMAP_PREFIX}{sha}",
                       {"new": found, **fingerprint},
                       evidence=[f"commit:{found}"])
        remapped.append({"old": sha, "new": found})
    return {
        "remapped": remapped,
        "already_remapped": already,
        "unresolved": unresolved,
    }


def reachable_commits(project: Path) -> set[str]:
    """Every commit reachable from some ref, which is NOT "object exists".

    `cat-file -e` answers whether the object is still in the database, and
    a rewrite leaves the originals there until gc runs - sometimes for
    weeks. Asking it after a scrub returns "all fine" for citations that
    now point at commits no branch or tag can reach, which is the exact
    failure this module exists to catch. Found by a test that amended a
    commit and watched the old sha still answer yes.
    """
    code, output = _git(project, "rev-list", "--all")
    if code != 0:
        return set()
    return {line.strip() for line in output.splitlines() if line.strip()}


def _reachable_commit(project: Path, commit: str,
                      known: set[str] | None = None) -> bool:
    reachable = reachable_commits(project) if known is None else known
    if commit in reachable:
        return True
    # A short sha in a citation is still a legitimate reference to a
    # reachable commit, so fall back to prefix matching rather than
    # calling an abbreviated citation lost.
    return any(full.startswith(commit) for full in reachable) if commit else False


def _find_by_fingerprint(project: Path,
                         fingerprint: dict[str, Any]) -> str | None:
    """The commit in current history matching tree + subject + author date."""
    code, output = _git(
        project, "log", "--all", "--format=%H%x1f%T%x1f%s%x1f%aI")
    if code != 0:
        return None
    for line in output.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        sha, tree, subject, author_date = (p.strip() for p in parts[:4])
        if (tree == str(fingerprint.get("tree"))
                and subject == str(fingerprint.get("subject"))
                and author_date == str(fingerprint.get("author_date"))):
            return sha
    return None


def reanchor_report(archive: Chronicle, project: Path, *,
                    kinds: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Both findings in one read, with the no-regrade stance stated."""
    project = Path(project)
    git = is_git_project(project)
    if not git:
        # Outside git neither question is answerable. Saying so beats an
        # empty result a caller would read as an all-clear.
        return {
            "git": False,
            "stale": [],
            "unreachable": [],
            "regraded": False,
            "note": ("not a git repository, so citation drift cannot be "
                     "determined here"),
        }
    stale = stale_records(archive, project, kinds=kinds)
    unreachable = unreachable_commit_citations(archive, project, kinds=kinds)
    return {
        "git": True,
        "stale": stale,
        # Ranked, not filtered: the flat list stays so nothing is hidden,
        # but the assertions that can actually be wrong are reachable
        # without reading past eighty attestations to find five.
        "standing": [f for f in stale if f.get("standing")],
        "historical": [f for f in stale if not f.get("standing")],
        "unreachable": unreachable,
        # Stated, not implied: this module never rewrites a grade. A stale
        # citation is a prompt to look again, not a verdict that the claim
        # was wrong, and only a person can tell those apart.
        "regraded": False,
        "note": ("detected, never regraded - re-read the evidence and record "
                 "a fresh claim or verdict where it no longer holds"),
    }
