"""Removal is driven by the manifest, bounded by containment, and reversible.

Three failure modes this guards, in the order they cost most:

1. Removing a file we did not create. The manifest is the only authority, and
   it is treated as untrusted input by the code that wrote it - a corrupted or
   hand-edited manifest naming `../` or an absolute system path must remove
   nothing at all, not "everything except the bad entry".
2. Removing a file irreversibly. Artifacts are archived under a timestamp
   rather than unlinked. A recovery path costs one rename.
3. Migrating another plugin's artifacts. Ownership is re-checked before any
   removal, not assumed because the directory was found.

The archive directory name uses no colon. `%H:%M:%S` is a legal filename on
macOS and illegal on Windows, so a timestamp that round-trips on one platform
and raises OSError on the other is a portability defect, not a formatting
choice.
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
from godmode_runtime import godmode_installremove as R  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def touch(self, rel: str, body: str = "x\n") -> Path:
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        return path


class Containment(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_plain_relative_path_is_safe(self) -> None:
        self.assertTrue(R.is_safe_managed_path(self.root, ".codex/hooks.json"))

    def test_an_absolute_path_is_refused(self) -> None:
        self.assertFalse(R.is_safe_managed_path(self.root, str(self.root / "a.json")))

    def test_a_traversal_segment_is_refused_on_either_separator(self) -> None:
        self.assertFalse(R.is_safe_managed_path(self.root, "../outside.json"))
        self.assertFalse(R.is_safe_managed_path(self.root, "..\\outside.json"))
        self.assertFalse(R.is_safe_managed_path(self.root, "a/../../outside.json"))

    def test_an_empty_or_non_string_candidate_is_refused(self) -> None:
        self.assertFalse(R.is_safe_managed_path(self.root, ""))
        self.assertFalse(R.is_safe_managed_path(self.root, None))

    def test_a_name_merely_starting_with_the_root_name_is_refused(self) -> None:
        """`/tmp/root-evil` must not pass a containment test against `/tmp/root`."""
        sibling = self.root.parent / (self.root.name + "-evil")
        self.assertFalse(R.is_safe_managed_path(self.root, str(sibling)))


class ArchiveRatherThanUnlink(Base):
    def test_recorded_artifacts_are_moved_not_destroyed(self) -> None:
        self.touch(".codex/hooks.json", "hook body\n")
        M.record(self.project, "godmode", "codex", [self.project / ".codex" / "hooks.json"])

        result = R.archive(self.project, "godmode")

        self.assertFalse((self.project / ".codex" / "hooks.json").exists())
        self.assertEqual(result["archived"], [".codex/hooks.json"])
        recovered = Path(result["archive_dir"]) / ".codex" / "hooks.json"
        self.assertTrue(recovered.exists(), result)
        self.assertEqual(recovered.read_text(encoding="utf-8"), "hook body\n")

    def test_the_archive_directory_name_is_a_legal_filename_everywhere(self) -> None:
        self.touch("a.json")
        M.record(self.project, "godmode", "g", [self.project / "a.json"])
        result = R.archive(self.project, "godmode")
        name = Path(result["archive_dir"]).name
        for illegal in ':*?"<>|':
            self.assertNotIn(illegal, name, f"{name!r} is not a legal Windows filename")

    def test_a_file_already_gone_is_reported_not_fatal(self) -> None:
        self.touch("a.json")
        M.record(self.project, "godmode", "g", [self.project / "a.json"])
        (self.project / "a.json").unlink()

        result = R.archive(self.project, "godmode")
        self.assertEqual(result["archived"], [])
        self.assertEqual(result["missing"], ["a.json"])


class ACorruptedManifestRemovesNothing(Base):
    def _corrupt(self, entries: list[str]) -> None:
        self.touch("real.json")
        M.record(self.project, "godmode", "g", [self.project / "real.json"])
        path = M.manifest_path(self.project, "godmode")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["groups"]["g"] = entries
        with open(path, "w", encoding="utf-8", newline="") as handle:
            json.dump(data, handle, indent=2)

    def test_a_traversal_entry_aborts_the_whole_removal(self) -> None:
        """Not 'everything except the bad entry' - nothing at all."""
        self._corrupt(["real.json", "../escape.json"])
        with self.assertRaises(R.UnsafeManifest):
            R.archive(self.project, "godmode")
        self.assertTrue((self.project / "real.json").exists(),
                        "a refused removal must leave every file in place")

    def test_an_absolute_entry_aborts_the_whole_removal(self) -> None:
        self._corrupt(["real.json", str(Path(tempfile.gettempdir()) / "elsewhere.json")])
        with self.assertRaises(R.UnsafeManifest):
            R.archive(self.project, "godmode")
        self.assertTrue((self.project / "real.json").exists())


class Ownership(Base):
    def test_another_plugins_artifacts_are_not_touched(self) -> None:
        self.touch(".codex/ours.json")
        self.touch(".codex/theirs.json")
        M.record(self.project, "godmode", "codex", [self.project / ".codex" / "ours.json"])
        M.record(self.project, "other", "codex", [self.project / ".codex" / "theirs.json"])

        R.archive(self.project, "godmode")

        self.assertFalse((self.project / ".codex" / "ours.json").exists())
        self.assertTrue((self.project / ".codex" / "theirs.json").exists())

    def test_archiving_with_no_manifest_is_a_no_op_not_an_error(self) -> None:
        result = R.archive(self.project, "godmode")
        self.assertEqual(result["archived"], [])
        self.assertIsNone(result["archive_dir"])


if __name__ == "__main__":
    unittest.main()
