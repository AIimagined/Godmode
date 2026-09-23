"""A commit that stages one version surface out of step with the others is refused.

NS-8g's brief fixture assumed `version_surfaces()` returns `{"path": ...,
"render": ...}` entries. The real function (`godmode_reconcile.py:82`)
originally returned only `{"surface": <what it means>, "version": <value>}`
- most surfaces are not files at all (a git tag, a tagged tree read via `git
show`), and the file-backed ones were named by what they mean
("packaging/hosts.json identity.version"), not by a literal repo-relative
path. A fix round added a `"path"` field to each surface (`None` for the
two non-file ones) so the pre-commit check below reads it instead of
hand-maintaining a second surface-to-path registry; `"render"` still does
not exist, so this test still writes the two smallest FILE-backed surfaces
by hand: `plugin.json` (`{"version": ...}`) and `packaging/hosts.json`
(`{"identity": {"version": ...}}`).
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_githooks  # noqa: E402
from godmode_runtime.godmode_reconcile import version_surfaces  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class VersionDriftPreCommitTests(unittest.TestCase):
    def _repo_with_surfaces(self, project: Path, drift: bool) -> None:
        _git(project, "init", "-q")
        _git(project, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "--allow-empty", "-m", "root")
        plugin_version = "9.9.9" if drift else "1.2.3"
        (project / "plugin.json").write_text(
            json.dumps({"version": plugin_version}), encoding="utf-8")
        hosts = project / "packaging" / "hosts.json"
        hosts.parent.mkdir(parents=True, exist_ok=True)
        hosts.write_text(
            json.dumps({"identity": {"version": "1.2.3"}}), encoding="utf-8")
        _git(project, "add", "-A")

    def test_drifting_surface_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._repo_with_surfaces(project, drift=True)
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertIn("version --reconcile", json.dumps(decision))

    def test_agreed_surfaces_pass(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._repo_with_surfaces(project, drift=False)
            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "allow", decision)


class VersionSurfacePathTests(unittest.TestCase):
    """`version_surfaces()`'s own `"path"` field is what the pre-commit check
    reads; this proves that field is trustworthy against this repository's
    real tree, not just against the synthetic fixture above."""

    def test_every_file_backed_surface_path_resolves(self) -> None:
        surfaces = version_surfaces(PLUGIN_ROOT)
        file_backed = [s for s in surfaces if s.get("path")]
        self.assertTrue(file_backed, "expected at least one file-backed surface")
        for surface in file_backed:
            resolved = PLUGIN_ROOT / surface["path"]
            self.assertTrue(
                resolved.is_file(),
                f"{surface['surface']!r} claims path {surface['path']!r}, "
                "which does not exist",
            )

    def test_non_file_surfaces_declare_no_path(self) -> None:
        surfaces = version_surfaces(PLUGIN_ROOT)
        non_file = [s for s in surfaces
                   if s["surface"] == "latest git tag" or s["surface"].startswith("plugin.json at tag")]
        for surface in non_file:
            self.assertIsNone(surface["path"], surface)


if __name__ == "__main__":
    unittest.main()
