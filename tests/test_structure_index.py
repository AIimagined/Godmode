"""B4-6 MVP: a per-project structural index so resume-time context comes
from a cache instead of re-reading source.

Scope deliberately narrow and stated: files, top-level symbols and imports
for Python (via `ast`), file-level entries for everything else. Names and
content hashes only - no source bodies in state. Incremental by content
hash: an unchanged file is never re-parsed. The outline renders from the
index alone (the source can be gone) and is bounded with its truncation
stated.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_structure import (  # noqa: E402
    INDEX_FILENAME, build_structure_index, structure_outline,
)

from test_godmode_runtime import isolated_project  # noqa: E402

BODY_MARKER = "NINETEEN-COPPER-HERONS"


def _seed(project: Path) -> None:
    (project / "pkg").mkdir(exist_ok=True)
    (project / "pkg" / "engine.py").write_text(
        "import json\n"
        "from pathlib import Path\n\n"
        "class TurbineController:\n"
        "    def spin(self):\n"
        f"        return '{BODY_MARKER}'\n\n"
        "def calibrate_rotor(x):\n"
        "    return x * 2\n",
        encoding="utf-8")
    (project / "README.md").write_text("# readme\n", encoding="utf-8")


class IndexBuildsAndRendersFromState(unittest.TestCase):
    def test_the_outline_renders_without_the_source(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _seed(project)
            build_structure_index(archive, project)
            (project / "pkg" / "engine.py").unlink()
            outline = structure_outline(archive)
            self.assertIn("TurbineController", outline)
            self.assertIn("calibrate_rotor", outline)

    def test_unchanged_files_are_never_reparsed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _seed(project)
            first = build_structure_index(archive, project)
            self.assertGreaterEqual(first["indexed"], 2)
            second = build_structure_index(archive, project)
            self.assertEqual(second["indexed"], 0)
            self.assertEqual(second["reused"], first["files"])
            (project / "pkg" / "engine.py").write_text(
                "def recalibrated(): pass\n", encoding="utf-8")
            third = build_structure_index(archive, project)
            self.assertEqual(third["indexed"], 1)

    def test_the_index_carries_names_and_hashes_never_bodies(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _seed(project)
            build_structure_index(archive, project)
            raw = (archive.root / INDEX_FILENAME).read_text(encoding="utf-8")
            self.assertNotIn(BODY_MARKER, raw)
            self.assertIn("TurbineController", raw)

    def test_a_non_python_file_gets_a_file_level_entry_only(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _seed(project)
            build_structure_index(archive, project)
            index = json.loads(
                (archive.root / INDEX_FILENAME).read_text(encoding="utf-8"))
            entry = index["files"]["README.md"]
            self.assertNotIn("classes", entry)
            self.assertTrue(entry["hash"])

    def test_the_outline_is_bounded_and_states_its_cut(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            for i in range(300):
                (project / f"m{i:03d}.py").write_text(
                    f"def fn_{i}(): pass\n", encoding="utf-8")
            build_structure_index(archive, project)
            outline = structure_outline(archive, limit_lines=50)
            lines = outline.strip().splitlines()
            self.assertLessEqual(len(lines), 50)
            self.assertIn("not shown", outline)

    def test_a_broken_python_file_is_recorded_file_level_not_fatal(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / "broken.py").write_text("def (((\n", encoding="utf-8")
            report = build_structure_index(archive, project)
            self.assertEqual(report["files"], 1)
            outline = structure_outline(archive)
            self.assertIn("broken.py", outline)


class ConsoleStructureCommand(unittest.TestCase):
    def test_context_structure_builds_and_renders(self) -> None:
        from godmode_runtime import godmode_console as console
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _seed(project)
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                code = console.main(["--project", str(project),
                                     "context", "structure"])
            payload = json.loads(out.getvalue())
            self.assertEqual(code, 0)
            self.assertIn("TurbineController", payload["outline"])
            self.assertGreaterEqual(payload["report"]["files"], 2)


if __name__ == "__main__":
    unittest.main()
