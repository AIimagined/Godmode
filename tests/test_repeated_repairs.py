"""A fix that keeps being needed is not a fix.

The loop detectors read checkpoint records, and recording a failure is
voluntary. An agent mid-task has every incentive to record progress and none to
record being stuck, so across this project's entire archive not one checkpoint
carries a non-green status and `hypothesis_reset_required` can never fire.

Inferring the failure from the records was tried first and abandoned: subjects
are outcome summaries, not problem statements, and none of them cluster. The
signal is simply not in the record.

It is in git. A file repaired by a `fix:` commit across three or more releases
is a file whose fixes are not holding — and this repository's own history says
`godmode_sentinel.py`, repaired across four releases while the real cause was
structural. The detector would have fired one release before the structural
question was finally asked.

No agent cooperation, no new record kind, no new discipline.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_loop import repeated_repairs  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


class _Repo:
    """A throwaway repository with a controllable repair history."""

    def __init__(self, holder: tempfile.TemporaryDirectory) -> None:
        self.path = Path(holder.name)
        _git(self.path, "init", "-q")
        _git(self.path, "config", "user.email", "demo@example.invalid")
        _git(self.path, "config", "user.name", "demo")

    def release(self, tag: str, *, fixes: str | None = None,
                version_only: str | None = None) -> None:
        if fixes:
            target = self.path / fixes
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = target.read_text(encoding="utf-8") if target.is_file() else ""
            target.write_text(existing + f"\n# repair for {tag}\n", encoding="utf-8")
            _git(self.path, "add", "-A")
            _git(self.path, "commit", "-q", "-m", f"fix: another attempt at {fixes}")
        if version_only:
            target = self.path / version_only
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f'__version__ = "{tag.lstrip("v")}"\n', encoding="utf-8")
            _git(self.path, "add", "-A")
            _git(self.path, "commit", "-q", "-m", f"fix: bump version for {tag}")
        _git(self.path, "tag", "-a", tag, "-m", tag)


def _fixture(*, releases: int, path: str = "src/thing.py") -> _Repo:
    holder = tempfile.TemporaryDirectory(prefix="godmode-repairs-")
    repo = _Repo(holder)
    repo._holder = holder  # type: ignore[attr-defined]
    for index in range(releases):
        repo.release(f"v0.0.{index + 1}", fixes=path)
    return repo


class ThresholdTests(unittest.TestCase):
    def test_three_releases_of_repair_is_reported(self) -> None:
        repo = _fixture(releases=3)
        with repo._holder:  # type: ignore[attr-defined]
            findings = repeated_repairs(repo.path)
        self.assertTrue(findings, "a fix needed in three releases went unreported")
        self.assertIn("src/thing.py", findings[0]["detail"])

    def test_two_releases_is_not_yet_a_pattern(self) -> None:
        """Twice is a bug that took two goes. The signal is persistence."""
        repo = _fixture(releases=2)
        with repo._holder:  # type: ignore[attr-defined]
            self.assertEqual(repeated_repairs(repo.path), [])

    def test_the_finding_names_the_releases(self) -> None:
        repo = _fixture(releases=4)
        with repo._holder:  # type: ignore[attr-defined]
            detail = repeated_repairs(repo.path)[0]["detail"]
        for tag in ("v0.0.1", "v0.0.4"):
            self.assertIn(tag, detail)


class VersionChoreTests(unittest.TestCase):
    def test_a_version_bump_is_not_a_repair(self) -> None:
        """Otherwise every file carrying a version string scores maximum and
        the real signal is buried under release chores."""
        holder = tempfile.TemporaryDirectory(prefix="godmode-repairs-")
        repo = _Repo(holder)
        with holder:
            for index in range(4):
                repo.release(f"v0.0.{index + 1}", version_only="src/version.py")
            findings = repeated_repairs(repo.path)
        self.assertEqual(findings, [], f"a version chore was read as a repair: {findings}")


class ThisRepositoryTests(unittest.TestCase):
    """The history that produced the detector, asserted without assuming it.

    The first version of this asserted the gate is named, which passed here and
    failed every CI job: a default checkout is shallow and carries no tags, so
    the detector correctly reported nothing and the test called that a fault.
    That is the fourth time in this project a check has been written to pass
    only where it was written.

    So both worlds are asserted, and neither is skipped. Where history exists
    the finding must appear; where it does not, the detector must report
    nothing rather than crash or invent.
    """

    def _has_history(self) -> bool:
        found = subprocess.run(
            ["git", "tag", "--list"], cwd=PLUGIN_ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace")
        return bool(found.stdout.split())

    def test_the_detector_matches_the_history_available_to_it(self) -> None:
        findings = repeated_repairs(PLUGIN_ROOT)
        if self._has_history():
            named = " ".join(f["detail"] for f in findings)
            self.assertIn("godmode_sentinel.py", named,
                          "the file repaired across four releases is not reported")
        else:
            self.assertEqual(
                findings, [],
                "a checkout with no tags cannot know what was repeated, and "
                "must report nothing rather than guess")

    def test_nothing_below_the_threshold_is_reported(self) -> None:
        for finding in repeated_repairs(PLUGIN_ROOT):
            self.assertGreaterEqual(finding["releases"], 3, finding)

    def test_a_project_without_git_reports_nothing_rather_than_failing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(repeated_repairs(Path(raw)), [])


if __name__ == "__main__":
    unittest.main()
