"""A disposable, non-git copy of this repository for tests that drive the
real CLI or eval harness against "the repo".

Why a copy and not `GODMODE_STATE_HOME`: for a git project the archive lives
at `<git-common-dir>/godmode-state`, and the state-home variable does NOT
redirect it. A test that ran `init` or an eval probe (`planmode specify`,
`guard`, ...) against the checkout with `--project .` therefore wrote to the
developer's live archive while its comment said it did not (0.3.28 release
preflight, shard 3). The copy below is not a git repository, so the archive
resolves under the state home the test names, and every probe's write lands
there and is thrown away with the directory.

What is copied: the TRACKED tree, as it stands on disk, minus the top-level
directories no probe reads (`tests/`, `assets/`, `benchmarks/`). Tracked
rather than "everything on disk" for two reasons: the checkout also holds
ignored working directories (tool state, session notes, archived reports)
that the shipped product does not contain and whose nested paths overrun
the Windows path limit under a temp directory; and what a probe proves
should be proved against what ships. An uncommitted edit to a tracked file
is copied as edited; a new file is copied only once it is added.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# Tracked top-level directories that are never copied: weight no probe reads.
SKIPPED_TOP_LEVEL = frozenset({"tests", "assets", "benchmarks"})


def tracked_files() -> list[str]:
    """Every tracked path, repository-relative with forward slashes."""
    listing = subprocess.run(
        ["git", "-C", str(PLUGIN_ROOT), "ls-files", "-z", "--cached"],
        capture_output=True, timeout=60)
    assert listing.returncode == 0, (
        "git ls-files failed; the copy needs the checkout's tracked list: "
        + listing.stderr.decode("utf-8", "replace"))
    return [path for path in listing.stdout.decode("utf-8").split("\0") if path]


def copy_repo_without_git(destination: Path) -> Path:
    """Copy the tracked tree into `destination / "project"` (created, must
    not exist) and return that path. The result is a plain directory, not
    a git repository: `git rev-parse` fails inside it, so the archive
    resolves under `GODMODE_STATE_HOME`."""
    project = Path(destination) / "project"
    project.mkdir()
    for relative in tracked_files():
        if relative.split("/", 1)[0] in SKIPPED_TOP_LEVEL:
            continue
        source = PLUGIN_ROOT / relative
        if not source.is_file():
            # Tracked but deleted or replaced by a directory in this
            # working tree: nothing on disk to copy.
            continue
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    assert not (project / ".git").exists(), "the copy must not be a git repository"
    return project


def initialise(project: Path) -> None:
    """Run the real CLI's `init` and `session open` inside the copy, with
    whatever `os.environ` the caller has patched in (build it with
    `tests/_host_env.scrubbed_environment`, state home included).

    The session is opened because the shipped behaviour probes run in a
    live session in real use (the session hook opens one before any
    skill runs); a probe such as `planmode specify` checks for an open
    session before it can refuse on anything else, so a copy with no
    session would fail it for a reason the probe is not about. Raises
    AssertionError with the command's stderr when either step fails."""
    for verb in (("init",), ("session", "open", "--label", "eval-probes")):
        done = subprocess.run(
            [sys.executable, "scripts/godmode.py", "--project", ".", *verb],
            cwd=project, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, f"{' '.join(verb)}: {done.stderr or done.stdout}"
