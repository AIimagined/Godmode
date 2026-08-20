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
    # Cached across records: a rewritten commit is usually cited more than
    # once, and `cat-file` is a process spawn each time.
    reachable: dict[str, bool] = {}
    for record in _records(archive, kinds or DEFAULT_KINDS):
        for citation in record.get("evidence") or []:
            text = str(citation)
            if not text.startswith("commit:"):
                continue
            sha = text[len("commit:"):].strip()
            if not sha:
                continue
            if sha not in reachable:
                code, _ = _git(project, "cat-file", "-e", f"{sha}^{{commit}}")
                reachable[sha] = code == 0
            if reachable[sha]:
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
        "unreachable": unreachable,
        # Stated, not implied: this module never rewrites a grade. A stale
        # citation is a prompt to look again, not a verdict that the claim
        # was wrong, and only a person can tell those apart.
        "regraded": False,
        "note": ("detected, never regraded - re-read the evidence and record "
                 "a fresh claim or verdict where it no longer holds"),
    }
