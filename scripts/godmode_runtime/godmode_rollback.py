"""B6-A: rollback to the last commit something actually proved green.

The archive already holds checkpoints carrying a `head` commit, but their
`status` is prose - "865 tests OK on the frozen tagged tree" is a sentence,
not a fact a machine may act on. Reading a restore point out of prose is
the inference this project refuses everywhere else, so green is attested
instead: the command that ran, the exit code it returned, and the commit it
ran against.

**A failing run cannot be marked green.** A restore point nobody proved
anything about is worse than no restore point at all, because it carries
the authority of a green without the evidence of one.

**Nothing here executes.** Restoring is `git reset --hard` territory: it
destroys uncommitted work, and the archive cannot see the working tree.
Godmode names the commit, says what proved it, lists what changed since,
and hands over the command. A person runs it. The report says
`executed: False` in its own output rather than leaving that to trust.

The command it hands back is the **non-destructive** one - a new branch at
the green commit, which loses nothing. The destructive alternative is
offered separately and labelled, so choosing it is a decision rather than
a default someone pasted.

Like the fleet layer, this stores nothing of its own: greens are
`decision` records under a `green:` subject, folded on read.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

_GREEN_PREFIX = "green:"
_GIT_TIMEOUT = 30


def _git(project: Path, *arguments: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ("git",) + arguments, cwd=str(project),
            capture_output=True, text=True, timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return result.returncode, result.stdout.strip()


def _head(project: Path) -> str | None:
    code, output = _git(project, "rev-parse", "HEAD")
    return output if code == 0 and output else None


def _reachable(project: Path, commit: str) -> bool:
    code, _ = _git(project, "cat-file", "-e", f"{commit}^{{commit}}")
    return code == 0


def mark_green(archive: Chronicle, project: Path, *, command: str,
               exit_code: int, commit: str | None = None) -> dict[str, Any]:
    """Attest that `command` passed at `commit`, refusing a failing run."""
    project = Path(project)
    command = command.strip()
    if not command:
        raise ArchiveError("A green needs the command that proved it")
    if exit_code != 0:
        # The whole value of a restore point is that something passed there.
        raise ArchiveError(
            f"'{command}' exited {exit_code}; a failing run cannot mark a "
            f"commit green")
    target = commit or _head(project)
    if not target:
        raise ArchiveError(
            "No commit to mark green: this project is not a git repository "
            "or has no commits yet")
    return archive.append(
        "decision", f"{_GREEN_PREFIX}{target}",
        {"commit": target, "command": command, "exit_code": exit_code},
        evidence=[f"cmd:{command}", f"commit:{target}"],
    )


def _greens(archive: Chronicle) -> list[dict[str, Any]]:
    try:
        events = archive.read_events(verify=False)
    except ArchiveError:
        return []
    return [
        record for record in events
        if record.get("kind") == "decision"
        and str(record.get("subject", "")).startswith(_GREEN_PREFIX)
    ]


def last_green(archive: Chronicle, project: Path) -> dict[str, Any] | None:
    """The newest attested green whose commit this repository still has.

    An unreachable commit is skipped rather than reported: a history
    rewrite can strand a restore point, and offering one that `git` would
    reject is a promise the repository cannot keep.
    """
    project = Path(project)
    for record in reversed(_greens(archive)):
        data = record.get("data") or {}
        commit = str(data.get("commit", ""))
        if not commit or not _reachable(project, commit):
            continue
        return {
            "commit": commit,
            "command": data.get("command"),
            "sequence": record.get("sequence"),
            "recorded_at": record.get("recorded_at"),
        }
    return None


def rollback_plan(archive: Chronicle, project: Path) -> dict[str, Any]:
    """What it would take to get back to the last proven-green commit.

    Reports; never acts. `executed` is always False and is stated in the
    payload so a caller reads it rather than assuming it.
    """
    project = Path(project)
    green = last_green(archive, project)
    if green is None:
        return {
            "green": None,
            "at_green": False,
            "changed_files": [],
            "restore_command": None,
            "discard_command": None,
            "uncommitted": [],
            "executed": False,
            "note": ("no attested green in this archive; run the suite and "
                     "record the result with `godmode rollback mark` so there "
                     "is a proven point to return to"),
        }
    head = _head(project)
    commit = green["commit"]
    at_green = head == commit
    code, output = _git(project, "diff", "--name-only", f"{commit}..HEAD")
    changed = [line for line in output.splitlines() if line] if code == 0 else []
    # Uncommitted work is the thing a hard reset silently destroys, so it is
    # surfaced next to the destructive command rather than left to be
    # discovered afterwards.
    _dirty_code, dirty = _git(project, "status", "--porcelain")
    uncommitted = [line for line in dirty.splitlines() if line]
    short = commit[:12]
    return {
        "green": green,
        "at_green": at_green,
        "changed_files": changed,
        # Non-destructive by default: a branch at the green commit loses
        # nothing and can be thrown away.
        "restore_command": f"git switch -c rollback-to-{short} {commit}",
        # Offered, labelled, never recommended by omission.
        "discard_command": f"git reset --hard {commit}",
        "uncommitted": uncommitted,
        "executed": False,
        "note": ("reported, never executed - `restore_command` is safe and "
                 "reversible; `discard_command` destroys uncommitted work"
                 + (f" including {len(uncommitted)} uncommitted change(s)"
                    if uncommitted else "")),
    }
