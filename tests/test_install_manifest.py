"""An install writes down what it created.

Host artifact writers put files into a project - a hooks manifest here, a
plugin shim there - and nothing recorded which files were ours. "Which files on
this host belong to us" was answerable only by matching a glob against paths we
happened to remember, which is a guess that gets worse every release.

The manifest is deliberately per-plugin and schema-versioned: two plugins
installing into one project must not be able to read, migrate, or remove each
other's artifacts.

Paths are stored relative and POSIX-shaped so a manifest written on one
platform is readable on another. That is not a style preference - a manifest
carrying `C:\\Users\\...` is unusable on macOS, and one carrying a backslash
separator is unreadable there too.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_installmanifest as M  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def touch(self, rel: str) -> Path:
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("x\n")
        return path


class RecordingWhatWasCreated(Base):
    def test_a_recorded_install_is_readable_back(self) -> None:
        self.touch(".codex/hooks.json")
        M.record(self.project, "godmode", "codex-hooks", [self.project / ".codex" / "hooks.json"])

        manifest = M.read(self.project, "godmode")
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["version"], M.SCHEMA)
        self.assertEqual(manifest["pluginName"], "godmode")
        self.assertEqual(manifest["groups"]["codex-hooks"], [".codex/hooks.json"])

    def test_paths_are_stored_relative_and_posix_shaped(self) -> None:
        """A manifest with an absolute or backslash path is unusable on another host."""
        self.touch(".opencode/plugins/godmode.js")
        M.record(self.project, "godmode", "opencode",
                 [self.project / ".opencode" / "plugins" / "godmode.js"])

        raw = M.manifest_path(self.project, "godmode").read_text(encoding="utf-8")
        stored = json.loads(raw)["groups"]["opencode"]
        self.assertEqual(stored, [".opencode/plugins/godmode.js"])
        for entry in stored:
            self.assertNotIn("\\", entry)
            self.assertFalse(Path(entry).is_absolute())

    def test_recording_the_same_path_twice_does_not_duplicate_it(self) -> None:
        self.touch(".codex/hooks.json")
        target = self.project / ".codex" / "hooks.json"
        M.record(self.project, "godmode", "codex-hooks", [target])
        M.record(self.project, "godmode", "codex-hooks", [target])
        self.assertEqual(M.read(self.project, "godmode")["groups"]["codex-hooks"],
                         [".codex/hooks.json"])

    def test_groups_accumulate_independently(self) -> None:
        self.touch(".codex/hooks.json")
        self.touch(".opencode/plugins/godmode.js")
        M.record(self.project, "godmode", "codex-hooks", [self.project / ".codex" / "hooks.json"])
        M.record(self.project, "godmode", "opencode",
                 [self.project / ".opencode" / "plugins" / "godmode.js"])

        groups = M.read(self.project, "godmode")["groups"]
        self.assertEqual(sorted(groups), ["codex-hooks", "opencode"])

    def test_a_path_outside_the_project_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            M.record(self.project, "godmode", "bad", [Path(tempfile.gettempdir()) / "elsewhere.json"])

    def test_reading_an_absent_manifest_returns_none_rather_than_raising(self) -> None:
        self.assertIsNone(M.read(self.project, "godmode"))


class TwoPluginsOneProject(Base):
    def test_neither_plugin_sees_the_other(self) -> None:
        self.touch(".codex/hooks.json")
        self.touch(".codex/other.json")
        M.record(self.project, "godmode", "codex-hooks", [self.project / ".codex" / "hooks.json"])
        M.record(self.project, "other-plugin", "codex-hooks", [self.project / ".codex" / "other.json"])

        ours = M.read(self.project, "godmode")
        theirs = M.read(self.project, "other-plugin")
        self.assertEqual(ours["groups"]["codex-hooks"], [".codex/hooks.json"])
        self.assertEqual(theirs["groups"]["codex-hooks"], [".codex/other.json"])
        self.assertNotEqual(M.manifest_path(self.project, "godmode"),
                            M.manifest_path(self.project, "other-plugin"))

    def test_a_manifest_is_not_returned_to_the_wrong_plugin(self) -> None:
        """Ownership is checked on read, not assumed from the path."""
        self.touch(".codex/hooks.json")
        M.record(self.project, "godmode", "codex-hooks", [self.project / ".codex" / "hooks.json"])

        path = M.manifest_path(self.project, "godmode")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pluginName"] = "someone-else"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            json.dump(data, handle, indent=2)

        self.assertIsNone(M.read(self.project, "godmode"))


class PluginNameSanitising(Base):
    def test_a_name_with_a_separator_cannot_escape_its_directory(self) -> None:
        self.touch("a.json")
        M.record(self.project, "../evil", "g", [self.project / "a.json"])
        written = M.manifest_path(self.project, "../evil")
        self.assertTrue(written.is_relative_to(self.project), written)


if __name__ == "__main__":
    unittest.main()
