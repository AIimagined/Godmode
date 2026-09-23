"""D-5: installing version N and then N+1 leaves exactly N+1's payload.

For every host Godmode writes a project artifact for, a temporary project
receives an install from a version-N plugin root, then an install from a
version-N+1 root whose payload differs. The proof has three parts, checked
per host:

- the install manifest names exactly the files N+1 wrote,
- the project holds exactly those files (nothing N wrote survives unless N+1
  wrote it again), and
- every file carries N+1's content, not N's.

Two update paths are proved. The in-place one is `hooks wire` run again from
the new version. The clean one is an uninstall from the manifest
(`godmode_installremove.archive`) followed by the new install; that is the
path that has to cope with a file version N shipped and N+1 does not, so
version N here also leaves one such file behind.

Temporary projects are plain directories, never git repositories.
"""
from __future__ import annotations

import inspect
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as H  # noqa: E402
from godmode_runtime import godmode_installmanifest as M  # noqa: E402
from godmode_runtime import godmode_installremove as R  # noqa: E402
from godmode_runtime import godmode_wire as W  # noqa: E402

PLUGIN = "godmode"
OPENCODE_SOURCE = Path("adapters") / "opencode" / "godmode.opencode.js"

# The project-level writers `hooks wire --host <h>` routes to directly; the
# other wire hosts (copilot, kiro) go through `godmode_wire.wire` alone.
LEGACY_WRITERS = {
    "codex": H.write_codex_project_hooks,
    "antigravity": H.write_antigravity_project_hooks,
    "opencode": H.write_opencode_project_shim,
}


def _make_root(base: Path, version: str) -> Path:
    """A plugin root carrying the files the host writers read.

    The root's own path is embedded in every hook command, so two roots
    already render different payloads; N+1 also changes the OpenCode shim
    body, the one artifact copied rather than rendered.
    """
    root = base / f"godmode-{version}"
    (root / "hooks").mkdir(parents=True)
    shutil.copyfile(PLUGIN_ROOT / "hooks" / "hooks.json", root / "hooks" / "hooks.json")
    shim = root / OPENCODE_SOURCE
    shim.parent.mkdir(parents=True)
    body = (PLUGIN_ROOT / OPENCODE_SOURCE).read_text(encoding="utf-8")
    shim.write_text(body + f"// godmode {version}\n", encoding="utf-8")
    return root


def _project_files(project: Path) -> set[str]:
    """Every file in the project outside Godmode's own state directory."""
    state = project / M.STATE_DIRNAME
    return {
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file() and state not in path.parents
    }


class InstallThenUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root_n = _make_root(base, "1.0.0")
        self.root_n1 = _make_root(base, "1.0.1")
        self._base = base
        self._count = 0

    def _project(self) -> Path:
        self._count += 1
        project = self._base / f"project-{self._count}"
        project.mkdir()
        self.assertFalse((project / ".git").exists())
        return project

    def _wire(self, root: Path, project: Path, host: str) -> set[str]:
        """Install `host` from `root` through `hooks wire`; return what it wrote."""
        before = _project_files(project)
        with mock.patch.object(W, "_PLUGIN_ROOT", root):
            report = W.wire(project, [host], dry_run=False, force=False)
        self.assertEqual(report["summary"], "safe to apply", report)
        self.assertEqual(report["changed"], [host], report)
        return _project_files(project) - before

    def _payload(self, root: Path, host: str) -> set[str]:
        """The files `root` writes for `host` into an empty project."""
        return self._wire(root, self._project(), host)

    def _assert_is_payload(self, project: Path, host: str, payload: set[str]) -> None:
        self.assertTrue(payload, f"{host}: the N+1 install wrote nothing")
        self.assertEqual(set(M.recorded_paths(project, PLUGIN)), payload,
                         f"{host}: the manifest does not name exactly N+1's payload")
        self.assertEqual(_project_files(project), payload,
                         f"{host}: the project does not hold exactly N+1's payload")
        for rel in payload:
            text = (project / rel).read_text(encoding="utf-8")
            self.assertNotIn(self.root_n.as_posix(), text,
                             f"{host}: {rel} still carries version N's content")

    def test_every_host_writer_is_proved(self) -> None:
        """A writer added to godmode_host_manifests without a wire host would
        escape this proof; the wire hosts must cover every project writer."""
        writers = {name for name, _ in inspect.getmembers(H, inspect.isfunction)
                   if name.startswith("write_") and "_project_" in name}
        self.assertEqual(writers, {fn.__name__ for fn in LEGACY_WRITERS.values()})
        self.assertLessEqual(set(LEGACY_WRITERS), set(W.WIRE_HOSTS))
        self.assertLessEqual({"copilot", "kiro"}, set(W.WIRE_HOSTS))

    def test_rewiring_from_the_new_version_leaves_exactly_its_payload(self) -> None:
        for host in W.WIRE_HOSTS:
            with self.subTest(host=host):
                payload = self._payload(self.root_n1, host)
                project = self._project()
                self._wire(self.root_n, project, host)
                self._wire(self.root_n1, project, host)
                self._assert_is_payload(project, host, payload)

    def test_uninstall_then_install_drops_a_file_only_version_n_shipped(self) -> None:
        for host in W.WIRE_HOSTS:
            with self.subTest(host=host):
                payload = self._payload(self.root_n1, host)
                project = self._project()
                self._wire(self.root_n, project, host)
                retired = project / f".godmode-{host}-retired.json"
                retired.write_text("{}\n", encoding="utf-8")
                M.record(project, PLUGIN, f"{host}-retired", [retired])
                self.assertIn(retired.name, M.recorded_paths(project, PLUGIN))

                result = R.archive(project, PLUGIN)
                self.assertIn(retired.name, result["archived"])
                self._wire(self.root_n1, project, host)

                self.assertFalse(retired.exists(), f"{host}: the N-only file survived")
                self._assert_is_payload(project, host, payload)

    def test_the_project_writers_update_in_place_when_forced(self) -> None:
        """`hooks wire --host codex|antigravity|opencode` call these writers;
        they refuse a changed file without --force, so the update is forced."""
        for host, writer in LEGACY_WRITERS.items():
            with self.subTest(host=host):
                project = self._project()
                first = writer(self.root_n, project)
                self.assertTrue(first["written"], first)
                refused = writer(self.root_n1, project)
                self.assertFalse(refused["written"], refused)
                second = writer(self.root_n1, project, force=True)
                self.assertTrue(second["written"], second)
                payload = {M.relative_posix(project, second["path"])}
                self._assert_is_payload(project, host, payload)


class UninstallForgetsWhatItRemoved(unittest.TestCase):
    def test_the_manifest_no_longer_names_archived_files(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            project = Path(name)
            target = project / "a.json"
            target.write_text("{}\n", encoding="utf-8")
            gone = project / "b.json"
            M.record(project, PLUGIN, "g", [target, gone])
            R.archive(project, PLUGIN)
            self.assertEqual(M.recorded_paths(project, PLUGIN), [])


if __name__ == "__main__":
    unittest.main()
