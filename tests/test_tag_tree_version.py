"""A tag's name is not a claim about the tree it points at.

v0.2.7 was published against the commit before the version bump. Every version
surface agreed — the tag was called `v0.2.7`, and every file in the working
tree said `0.2.7` — so the reconciler returned `agreed` and CI passed on it.
Meanwhile `git checkout v0.2.7` produced a plugin manifest reading `0.2.6`, and
anyone installing the release got a plugin identifying as the previous version.

Nothing was broken in the check. It compared the tag's *name* to the sources,
and the name was never wrong; the question it never asked was what the tagged
commit says about itself. This asks it.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_reconcile import reconcile_versions  # noqa: E402


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments],
                   capture_output=True, check=False)


def _write_version(root: Path, version: str) -> None:
    """Every surface the reconciler reads, set to one version."""
    (root / "plugin.json").write_text(
        json.dumps({"name": "godmode", "version": version}), encoding="utf-8")
    for manifest in (".claude-plugin", ".codex-plugin", ".grok-plugin"):
        directory = root / manifest
        directory.mkdir(exist_ok=True)
        (directory / "plugin.json").write_text(
            json.dumps({"name": "godmode", "version": version}), encoding="utf-8")
    packaging = root / "packaging"
    packaging.mkdir(exist_ok=True)
    (packaging / "hosts.json").write_text(
        json.dumps({"identity": {"version": version}}), encoding="utf-8")
    runtime = root / "scripts" / "godmode_runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "godmode_constants.py").write_text(
        f'RUNTIME_VERSION = "{version}"\n', encoding="utf-8")
    (runtime / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n## [{version}] - 2026-08-09\n",
        encoding="utf-8")


class Repository:
    """A project whose tag can be put on the wrong commit deliberately."""

    def __init__(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-tagtree-")
        self.root = Path(self._holder.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "d@e.invalid")
        _git(self.root, "config", "user.name", "d")

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *_exception: object) -> None:
        self._holder.cleanup()

    def commit(self, version: str, message: str) -> None:
        _write_version(self.root, version)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", message)

    def tag(self, name: str) -> None:
        _git(self.root, "tag", "-a", name, "-m", name)

    def reconcile(self) -> dict:
        return reconcile_versions(self.root)


class TagTreeTests(unittest.TestCase):
    def test_a_tag_on_the_commit_before_the_bump_is_drift(self) -> None:
        """Today's incident, exactly: v0.2.7 tagged against a tree that still
        says 0.2.6, with the bump committed after it. Every other surface
        agrees, which is why nothing caught it."""
        with Repository() as repository:
            repository.commit("0.2.6", "the fix")
            repository.tag("v0.2.7")          # tagged too early
            repository.commit("0.2.7", "the release")
            report = repository.reconcile()

        self.assertEqual(report["verdict"], "version-drift",
                         "a tag pointing at the previous version read as agreed")
        self.assertIn("0.2.6", report["drift"])
        tagged = [s for s in report["surfaces"]
                  if s["surface"].startswith("plugin.json at tag")]
        self.assertEqual(tagged[0]["version"], "0.2.6")

    def test_the_name_alone_would_still_have_agreed(self) -> None:
        """The defect is only visible because the tree is read. Without the
        new surface every remaining one says 0.2.7 and the tag is named
        v0.2.7, so the old check had nothing to disagree with."""
        with Repository() as repository:
            repository.commit("0.2.6", "the fix")
            repository.tag("v0.2.7")
            repository.commit("0.2.7", "the release")
            report = repository.reconcile()

        without_tree = {s["version"] for s in report["surfaces"]
                        if not s["surface"].startswith("plugin.json at tag")}
        self.assertEqual(without_tree, {"0.2.7"})

    def test_a_tag_on_the_release_commit_agrees(self) -> None:
        with Repository() as repository:
            repository.commit("0.2.6", "the fix")
            repository.commit("0.2.7", "the release")
            repository.tag("v0.2.7")
            report = repository.reconcile()

        self.assertEqual(report["verdict"], "agreed", report["surfaces"])
        self.assertTrue(report["tagged_tree_checked"])

    def test_moving_the_tag_forward_resolves_it(self) -> None:
        """The remedy applied today, asserted rather than assumed."""
        with Repository() as repository:
            repository.commit("0.2.6", "the fix")
            repository.tag("v0.2.7")
            repository.commit("0.2.7", "the release")
            self.assertEqual(repository.reconcile()["verdict"], "version-drift")

            _git(repository.root, "tag", "-f", "-a", "v0.2.7", "-m", "moved")
            self.assertEqual(repository.reconcile()["verdict"], "agreed")

    def test_an_untagged_project_reports_that_it_was_not_checked(self) -> None:
        """A shallow clone has the tag without always having its tree, and
        reporting a fetch depth as a release defect is how a gate gets
        switched off. Stated rather than silently skipped."""
        with Repository() as repository:
            repository.commit("0.2.7", "the release")
            report = repository.reconcile()

        self.assertFalse(report["tagged_tree_checked"])
        self.assertEqual(report["verdict"], "agreed")


if __name__ == "__main__":
    unittest.main()
