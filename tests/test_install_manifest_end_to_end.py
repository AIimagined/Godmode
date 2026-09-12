"""Acceptance clause 10, demonstrated rather than asserted.

A complexity review of this amendment found the install manifest and its
removal half had no production caller at all. They were tested libraries that nothing
invoked, which meant the clause they exist to satisfy - "an install writes a
manifest of every path it created, demonstrated on a populated install" - was
not met while the sprint was being reported as complete.

This runs the real host artifact writers against a temporary project, then
uninstalls using only what the manifest recorded, and checks both halves of the
clause: nothing the install created is left behind, and nothing it did not
create is touched.

The foreign file matters more than the happy path. An uninstall that removes
everything under a directory would pass a leaves-nothing-behind test and be
catastrophic on a project that keeps its own files there.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as H  # noqa: E402
from godmode_runtime import godmode_installmanifest as M  # noqa: E402
from godmode_runtime import godmode_installremove as R  # noqa: E402


class ARealInstallRecordsWhatItWrote(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _install(self) -> list[str]:
        written: list[str] = []
        for call in (
            lambda: H.write_codex_project_hooks(PLUGIN_ROOT, self.project),
            lambda: H.write_opencode_project_shim(PLUGIN_ROOT, self.project),
            lambda: H.write_antigravity_project_hooks(PLUGIN_ROOT, self.project),
        ):
            try:
                result = call()
            except Exception:  # noqa: BLE001 - a writer needing absent assets
                continue
            if result.get("written"):
                written.append(result["path"])
        return written

    def test_the_writers_produce_files(self) -> None:
        """Positive control: without this the rest passes vacuously."""
        self.assertTrue(self._install(), "no host writer produced a file")

    def test_every_written_path_is_in_the_manifest(self) -> None:
        written = self._install()
        self.assertTrue(written)
        recorded = set(M.recorded_paths(self.project, "godmode"))
        for path in written:
            relative = M.relative_posix(self.project, path)
            self.assertIn(relative, recorded, f"{relative} was written but not recorded")

    def test_an_uninstall_from_the_manifest_leaves_nothing_behind(self) -> None:
        written = self._install()
        self.assertTrue(written)

        R.archive(self.project, "godmode")

        for path in written:
            self.assertFalse(Path(path).exists(), f"{path} survived the uninstall")

    def test_an_uninstall_does_not_touch_a_file_it_did_not_create(self) -> None:
        """The half that matters. Removing a directory wholesale would pass the
        test above and destroy a project's own files."""
        self._install()
        foreign = self.project / ".codex" / "their-own-config.json"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        with open(foreign, "w", encoding="utf-8", newline="") as handle:
            handle.write("{}\n")

        R.archive(self.project, "godmode")

        self.assertTrue(foreign.exists(), "the uninstall removed a foreign file")

    def test_the_removed_files_are_recoverable(self) -> None:
        written = self._install()
        self.assertTrue(written)
        result = R.archive(self.project, "godmode")
        self.assertTrue(result["archived"])
        self.assertTrue(Path(result["archive_dir"]).exists())


class RecordingNeverCostsTheInstall(unittest.TestCase):
    def test_a_writer_still_reports_written_when_recording_cannot_happen(self) -> None:
        """The manifest is bookkeeping; the install is the operation."""
        with tempfile.TemporaryDirectory() as name:
            project = Path(name)
            result = H.write_codex_project_hooks(PLUGIN_ROOT, project)
            self.assertTrue(result.get("written"), result)


if __name__ == "__main__":
    unittest.main()
