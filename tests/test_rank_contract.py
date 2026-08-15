"""The ranking contract, pinned as regressions.

Rank fusion was prototyped as a replacement and rejected on measurement, so
what remains here is the set of properties the shipped scorer must keep: role
authority carries a segment the task wording missed, relevance can still lift a
lower-weighted document, and the order never depends on input order.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_corpus import Segment, rank  # noqa: E402


def _segment(path: str, weight: float, body: str, line: int = 1) -> Segment:
    return Segment(role="operating-guide", weight=weight, path=path,
                   heading="section", start_line=line, end_line=line + 1, body=body)


class RankContractTests(unittest.TestCase):
    """The guarantees the previous scorer made, which fusion must keep."""

    def test_a_segment_matching_nothing_still_ranks_by_role(self) -> None:
        segments = [
            _segment("LOW.md", 0.2, "nothing relevant here at all"),
            _segment("HIGH.md", 1.0, "unrelated prose about weather"),
        ]
        ordered = [segment.path for segment, _ in rank(segments, "token rotation")]
        self.assertEqual(ordered[0], "HIGH.md")

    def test_relevance_can_lift_a_lower_weighted_document(self) -> None:
        segments = [
            _segment("HIGH.md", 1.0, "weather and gardening notes"),
            _segment("LOW.md", 0.6, "token rotation replay defence and rotation windows"),
        ]
        ordered = [segment.path for segment, _ in rank(segments, "token rotation replay")]
        self.assertEqual(ordered[0], "LOW.md")

    def test_ranking_is_deterministic(self) -> None:
        segments = [_segment(f"D{i}.md", 1.0 - i / 10, f"body {i} rotation") for i in range(6)]
        first = [(s.path, score) for s, score in rank(segments, "rotation")]
        for _ in range(5):
            self.assertEqual([(s.path, score) for s, score in rank(segments, "rotation")], first)

    def test_ties_break_on_path_then_line_not_on_input_order(self) -> None:
        segments = [
            _segment("b.md", 1.0, "same body", line=1),
            _segment("a.md", 1.0, "same body", line=1),
        ]
        forward = [s.path for s, _ in rank(segments, "unrelated")]
        backward = [s.path for s, _ in rank(list(reversed(segments)), "unrelated")]
        self.assertEqual(forward, backward)
        self.assertEqual(forward[0], "a.md")

    def test_freshness_participates_as_a_vote_not_a_nudge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            for name in ("stale.md", "fresh.md"):
                (project / name).write_text("token rotation notes", encoding="utf-8")
            import os, time
            old = time.time() - 86_400 * 30
            os.utime(project / "stale.md", (old, old))
            segments = [_segment("stale.md", 1.0, "token rotation notes"),
                        _segment("fresh.md", 1.0, "token rotation notes")]
            ordered = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            self.assertEqual(ordered[0], "fresh.md")


def _git(project: Path, *args: str, env: dict[str, str] | None = None) -> None:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    subprocess.run(["git", "-C", str(project), *args], check=True,
                   capture_output=True, text=True, env=full_env)


class GitCheckoutOrderIndependenceTests(unittest.TestCase):
    """Fix round 1 (adjudication a): freshness must not depend on filesystem
    mtime for a git project. `git clone`/`git checkout` do not preserve
    historical mtimes, so two clones of the identical commit disagreed on
    file order purely from checkout timing - the concrete failure was
    `evals/fixtures/ranking.json` drifting between two clones of one
    commit. Freshness now reads `git log`'s commit timestamp, which is part
    of the commit object every clone already has, so it agrees regardless
    of when or in what order the working tree was written to disk.

    This determinism guarantee is scoped to COMMITTED files only. An
    untracked file, or one staged but never committed, has no `git log`
    entry to read at all, so there is no commit object for a clone to
    agree on - mtime is the only signal that exists for it, exactly as for
    a non-git project, and fix round 2 covers that boundary case below.
    """

    def test_ranking_is_identical_regardless_of_on_disk_mtime_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            _git(project, "init", "-q")
            _git(project, "config", "user.email", "test@example.com")
            _git(project, "config", "user.name", "Test")

            (project / "older.md").write_text("token rotation notes", encoding="utf-8")
            _git(project, "add", "older.md")
            _git(project, "commit", "-q", "-m", "older", env={
                "GIT_AUTHOR_DATE": "2020-01-01T00:00:00", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00"})

            (project / "newer.md").write_text("token rotation notes", encoding="utf-8")
            _git(project, "add", "newer.md")
            _git(project, "commit", "-q", "-m", "newer", env={
                "GIT_AUTHOR_DATE": "2024-01-01T00:00:00", "GIT_COMMITTER_DATE": "2024-01-01T00:00:00"})

            segments = [_segment("older.md", 1.0, "token rotation notes"),
                        _segment("newer.md", 1.0, "token rotation notes")]

            baseline = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            # By git history, "newer.md" is the more recently committed file -
            # freshness should favour it regardless of what the filesystem says.
            self.assertEqual(baseline[0], "newer.md")

            # Shuffle on-disk mtimes to the OPPOSITE of commit order - exactly
            # what a real checkout can do (checkout writes files in whatever
            # order the filesystem layer chooses, not commit order). A
            # mtime-driven scorer would flip; a git-log-driven one must not.
            now = 1_700_000_000.0
            os.utime(project / "older.md", (now + 1000, now + 1000))
            os.utime(project / "newer.md", (now, now))

            shuffled = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            self.assertEqual(shuffled, baseline)
            self.assertEqual(shuffled[0], "newer.md")

    def test_an_untracked_file_falls_back_to_mtime_instead_of_stamping_zero(self) -> None:
        """Fix round 2: `git log` has no entry for an untracked (or
        staged-but-uncommitted) file - that must not read as "this project
        has no git history for anything" and stamp the oldest possible
        value. A file written a minute ago has to outrank a six-year-old
        COMMITTED sibling on a freshness tie, or the feature runs backwards
        for every file nobody has committed yet, which in practice is most
        of a session's live edits.
        """
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            _git(project, "init", "-q")
            _git(project, "config", "user.email", "test@example.com")
            _git(project, "config", "user.name", "Test")

            (project / "ancient.md").write_text("token rotation notes", encoding="utf-8")
            _git(project, "add", "ancient.md")
            _git(project, "commit", "-q", "-m", "ancient", env={
                "GIT_AUTHOR_DATE": "2018-01-01T00:00:00", "GIT_COMMITTER_DATE": "2018-01-01T00:00:00"})

            # Written just now, never `git add`-ed: no git log entry exists.
            (project / "just_written.md").write_text("token rotation notes", encoding="utf-8")

            segments = [_segment("ancient.md", 1.0, "token rotation notes"),
                        _segment("just_written.md", 1.0, "token rotation notes")]
            ordered = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            self.assertEqual(
                ordered[0], "just_written.md",
                "an untracked file must not stamp 0 (oldest possible) and lose a "
                "freshness tie to a years-old committed file")

            # Staged but not yet committed hits the same code path (`git log`
            # still has nothing for it) and must resolve the same way.
            _git(project, "add", "just_written.md")
            staged_ordered = [s.path for s, _ in rank(segments, "token rotation", project=project)]
            self.assertEqual(staged_ordered[0], "just_written.md")


class NonGitCopyOrderIndependenceTests(unittest.TestCase):
    """Fix round 3: a NON-git project has no commit object either, so the
    git-log fix above does not reach it - freshness there fell all the way
    back to raw filesystem mtime, and mtime is assigned by whatever copied
    or checked out the files, not by their content. Two copies of the exact
    same project can end up with their files' mtimes in a different
    relative order purely from copy timing (`tests/test_gate_falsifiability`
    copies this very repo with `.git` stripped, exposing it as a real
    `evals --brief` failure: `ranking-changed` even though the copy is
    byte-identical to the tree the fixture was pinned against). Mtime
    remains the freshness *value* `_freshness_stamp` returns for a non-git
    path - that fallback (fix round 2) stays - but a non-git project has no
    signal that agrees across copies the way a commit timestamp does, so
    ordering among its files must not be driven by comparing raw mtime
    magnitudes across copies. It degrades to the same deterministic
    instrument the git path already uses as its secondary key: path.
    """

    def test_ranking_is_identical_across_non_git_copies_with_shuffled_mtimes(self) -> None:
        segments = [_segment("alpha.md", 1.0, "token rotation notes"),
                    _segment("beta.md", 1.0, "token rotation notes"),
                    _segment("gamma.md", 1.0, "token rotation notes")]

        def _make_copy(order: list[str]) -> Path:
            project = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, project, ignore_errors=True)
            for name in ("alpha.md", "beta.md", "gamma.md"):
                (project / name).write_text("token rotation notes", encoding="utf-8")
            # Assign mtimes in a different relative order per copy - exactly
            # what independent copy operations can do despite identical
            # content, with no `.git` present to anchor freshness on.
            base = 1_700_000_000.0
            for position, name in enumerate(order):
                stamp = base + position
                os.utime(project / name, (stamp, stamp))
            return project

        copy_one = _make_copy(["alpha.md", "beta.md", "gamma.md"])
        copy_two = _make_copy(["gamma.md", "alpha.md", "beta.md"])

        ordered_one = [s.path for s, _ in rank(segments, "token rotation", project=copy_one)]
        ordered_two = [s.path for s, _ in rank(segments, "token rotation", project=copy_two)]
        self.assertEqual(
            ordered_one, ordered_two,
            "identical non-git copies must rank identically regardless of "
            "which file the copy operation happened to timestamp newest")


class BriefEquivalenceTests(unittest.TestCase):
    def test_the_brief_stays_byte_identical_across_runs(self) -> None:
        from godmode_runtime.godmode_corpus import build_brief

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "GODMODE.md").write_text(
                "# Guide\n\nAlways verify before claiming.\n", encoding="utf-8")
            first = json.dumps(build_brief(project, "verify claims", 1200), sort_keys=True)
            second = json.dumps(build_brief(project, "verify claims", 1200), sort_keys=True)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
