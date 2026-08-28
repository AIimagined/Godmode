"""C-10: a source-freshness preflight with honest partial reporting.

A record cites its sources - `file:`, `commit:`, `url:`. Two of those
classes can be checked locally: a cited file committed after the record was
written is stale, and a cited commit no longer reachable is gone. The
third cannot: godmode never touches the network, so a `url:` citation is
reported as *unverifiable*, never as fresh. The report names every class
it could not check; a preflight that stays quiet about what it skipped is
the thing this capability exists to replace.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_freshness import freshness_report  # noqa: E402


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})
    return done.stdout.strip()


# `stale_records` compares at whole-second resolution and stays quiet on a
# tie (its docstring says why). A test that commits in the same second the
# record was written would sit inside that blind spot, so the "later"
# commit is stamped a minute ahead - git's committer date is the clock the
# comparison reads.
_LATER = {"GIT_COMMITTER_DATE": "2099-01-01T00:00:00+00:00",
          "GIT_AUTHOR_DATE": "2099-01-01T00:00:00+00:00"}


@contextmanager
def _git_project():
    with tempfile.TemporaryDirectory(prefix="godmode-fresh-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                        ["config", "user.name", "d"]):
            _git(root, *command)
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize() if hasattr(archive, "initialize") else None
            yield root, archive


class FreshnessTests(unittest.TestCase):
    def test_each_citation_class_is_checked_or_declared_unverifiable(self) -> None:
        with _git_project() as (root, archive):
            head = _git(root, "rev-parse", "HEAD")
            archive.append("claim", "cites three classes", {"grade": "verified"},
                           evidence=[f"commit:{head}", "file:src.py",
                                     "url:https://example.invalid/spec"])
            # A later commit to the cited file makes the file citation stale.
            (root / "src.py").write_text("x = 2\n", encoding="utf-8")
            _git(root, "commit", "-q", "-am", "change", env=_LATER)
            report = freshness_report(archive, root)
        self.assertEqual(report["checked"]["file"], 1)
        self.assertEqual(report["checked"]["commit"], 1)
        self.assertEqual(report["unverifiable"]["url"], 1)
        self.assertTrue(report["partial"])
        self.assertIn("url", " ".join(report["not_checked"]))
        self.assertEqual(len(report["stale_files"]), 1)
        self.assertEqual(report["unreachable_commits"], [])
        self.assertEqual(report["verdict"], "stale")

    def test_nothing_unverifiable_means_not_partial(self) -> None:
        with _git_project() as (root, archive):
            head = _git(root, "rev-parse", "HEAD")
            archive.append("claim", "local only", {"grade": "verified"},
                           evidence=[f"commit:{head}", "file:src.py"])
            report = freshness_report(archive, root)
        self.assertFalse(report["partial"])
        self.assertEqual(report["not_checked"], [])
        self.assertEqual(report["verdict"], "fresh")

    def test_stale_reaches_the_exit_but_partial_alone_does_not(self) -> None:
        with _git_project() as (root, archive):
            archive.append("claim", "remote only", {"grade": "verified"},
                           evidence=["url:https://example.invalid/x"])
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "freshness"])
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["partial"])
        # Nothing local was reachable, so this run says nothing about
        # staleness - it must not answer in the reassuring direction.
        self.assertEqual(payload["verdict"], "unchecked")
        self.assertEqual(code, 0)

    def test_a_run_that_checked_nothing_says_so_instead_of_fresh(self) -> None:
        """Field report 2026-08-28: `freshness` on a project whose records
        carry no local citations returned `{"verdict": "fresh", "checked":
        {"commit": 0, "file": 0}}` and was nearly quoted as evidence that
        nothing had gone stale. A probe that reached nothing cannot
        distinguish clean from unchecked, so it says `unchecked` and names
        the reach it had."""
        with _git_project() as (root, archive):
            archive.append("lesson", "no citations here", {"status": "active"})
            report = freshness_report(archive, root)
        self.assertEqual(report["checked"], {"file": 0, "commit": 0})
        self.assertEqual(report["verdict"], "unchecked")
        self.assertIn("nothing locally checkable", " ".join(report["not_checked"]).lower())

    def test_one_reachable_citation_is_enough_to_answer_fresh(self) -> None:
        with _git_project() as (root, archive):
            archive.append("claim", "one local", {"grade": "verified"},
                           evidence=["file:src.py", "url:https://example.invalid/x"])
            report = freshness_report(archive, root)
        self.assertEqual(report["verdict"], "fresh")
        self.assertTrue(report["partial"])


if __name__ == "__main__":
    unittest.main()
