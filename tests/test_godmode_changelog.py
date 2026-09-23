"""Regression coverage for `skills/godmode-changelog`'s Deterministic
Execution Flow: every preflight command the SKILL.md names, run in order
against a disposable fixture project.

Flow under test (SKILL.md steps 1-6):
  1. `changelog check --base ...`             - the fragment gate
  2. (fallback) add a `changelog.d/*.md` fragment, re-check
  3. `precheck --about ...`                   - no other missing artifact
  4. `changelog merge --set-version ...`      - spend the fragments
  5. `release-notes build ...`                - draft the notes
  6. `release-notes check ...`                - hold them to shape
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, capture_output=True, text=True)


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


@contextmanager
def _fixture_project():
    with tempfile.TemporaryDirectory(prefix="godmode-changelog-") as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        _git(project, "init", "-q")
        _git(project, "config", "user.email", "d@e.invalid")
        _git(project, "config", "user.name", "fixture")
        (project / "README.md").write_text("# fixture\n", encoding="utf-8")
        (project / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        _git(project, "add", "-A")
        _git(project, "commit", "-q", "-m", "base")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            _run(project, "session", "open", "--label", "changelog-fixture")
            yield project


class ChangelogFlowTests(unittest.TestCase):
    def test_missing_fragment_is_refused_then_satisfied(self) -> None:
        with _fixture_project() as project:
            (project / "widget.py").write_text("def widget():\n    return 1\n", encoding="utf-8")

            # Step 1: a new user-visible file with no fragment is refused.
            code, report = _run(project, "changelog", "check", "--base", "HEAD")
            self.assertEqual(code, 1, report)
            self.assertEqual(report["verdict"], "missing-fragment")
            self.assertIn("widget.py", report["changes_needing_note"])

            # Step 2 (fallback): add the one-line fragment the gate named.
            fragments = project / "changelog.d"
            fragments.mkdir()
            (fragments / "widget.added.md").write_text(
                "- Add the widget helper.\n", encoding="utf-8",
            )
            code, report = _run(project, "changelog", "check", "--base", "HEAD")
            self.assertEqual(code, 0, report)
            self.assertEqual(report["verdict"], "satisfied")
            self.assertEqual(report["satisfied_by"], "fragment")

    def test_merge_then_build_then_check_release_notes(self) -> None:
        with _fixture_project() as project:
            (project / "widget.py").write_text("def widget():\n    return 1\n", encoding="utf-8")
            fragments = project / "changelog.d"
            fragments.mkdir()
            (fragments / "widget.added.md").write_text(
                "- Add the widget helper.\n", encoding="utf-8",
            )
            code, report = _run(project, "changelog", "check", "--base", "HEAD")
            self.assertEqual(code, 0, report)

            # Step 3: no other missing paired artifact before cutting.
            code, precheck = _run(project, "precheck", "--about", "cut release 0.1.0")
            self.assertIn(code, (0, 1))
            self.assertIn("verdict", precheck)

            # Step 4: spend the fragment into the changelog.
            code, merged = _run(
                project, "changelog", "merge", "--set-version", "0.1.0",
                "--date", "2026-01-01",
            )
            self.assertEqual(code, 0, merged)
            self.assertFalse((fragments / "widget.added.md").exists())
            changelog_text = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## [0.1.0]", changelog_text)
            self.assertIn("Add the widget helper.", changelog_text)

            # A fragment arriving after the first merge folds into the SAME
            # version section rather than opening a second heading for it.
            fragments.mkdir(exist_ok=True)
            (fragments / "widget-two.fixed.md").write_text(
                "- Fix the widget helper's edge case.\n", encoding="utf-8",
            )
            code, merged_again = _run(
                project, "changelog", "merge", "--set-version", "0.1.0",
                "--date", "2026-01-01",
            )
            self.assertEqual(code, 0, merged_again)
            changelog_text = (project / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertEqual(changelog_text.count("## [0.1.0]"), 1)
            self.assertIn("Fix the widget helper's edge case.", changelog_text)

            # Must-not (SKILL.md:74): running merge again with nothing left
            # under changelog.d/ has nothing to spend and refuses, rather
            # than silently succeeding a second time for the same version.
            code, merged_empty = _run(
                project, "changelog", "merge", "--set-version", "0.1.0",
                "--date", "2026-01-01",
            )
            self.assertNotEqual(code, 0, merged_empty)

            # Step 5: build the notes from that merged section.
            code, built = _run(project, "release-notes", "build", "0.1.0")
            self.assertEqual(code, 0, built)
            self.assertTrue(built["written"])
            notes_path = project / built["path"]
            self.assertTrue(notes_path.is_file())

            # Step 6: hold the built notes to the required shape.
            code, checked = _run(project, "release-notes", "check", "0.1.0")
            self.assertEqual(code, 0, checked)
            self.assertTrue(checked["ok"], checked)

    def test_build_before_merge_is_refused(self) -> None:
        """Must-not: never build notes while the changelog has no section
        for the version yet."""
        with _fixture_project() as project:
            # CHANGELOG.md exists (the fixture seeds it) but carries no
            # section for a version nothing has merged yet.
            code, built = _run(project, "release-notes", "build", "9.9.9")
            self.assertEqual(code, 1, built)
            self.assertFalse(built["written"])
            self.assertIn("refused", built)
            self.assertIn("changelog merge --set-version", built["refused"])


if __name__ == "__main__":
    unittest.main()
