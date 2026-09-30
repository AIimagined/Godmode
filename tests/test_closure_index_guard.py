"""The closure check's saved-index guard: a partial index is refused, a
budget trip is named on stderr, and the unbounded retest rebuild announces
itself on stderr."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_closure  # noqa: E402
from godmode_runtime.godmode_atlas import Atlas, build as build_atlas, save_index  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402

ROOT_DIR = godmode_closure._CLOSURE_ROOT_DIRS[0]


def _project(raw: str) -> Path:
    project = Path(raw)
    (project / ROOT_DIR).mkdir(parents=True)
    (project / ROOT_DIR / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (project / ROOT_DIR / "b.py").write_text("from a import alpha\n", encoding="utf-8")
    return project


class ClosureIndexGuardTests(unittest.TestCase):
    def test_a_partial_index_is_refused_and_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(raw)
            atlas = build_atlas(project, roots=godmode_closure._CLOSURE_ROOT_DIRS)
            save_index(atlas, project / godmode_closure._ATLAS_INDEX_FILENAME)
            # A file the saved index never saw: every stored file is still
            # fresh, so the old check read the index as complete.
            (project / ROOT_DIR / "c.py").write_text("def gamma():\n    return 3\n", encoding="utf-8")
            err = io.StringIO()
            with mock.patch.object(sys, "stderr", err):
                rebuilt = godmode_closure._atlas_for_closure(project)
            self.assertIn("partial", err.getvalue())
            self.assertIn(f"{ROOT_DIR}/c.py", err.getvalue())
            self.assertIn(f"{ROOT_DIR}/c.py", rebuilt.files)

    def test_a_complete_fresh_index_is_still_rehydrated(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(raw)
            atlas = build_atlas(project, roots=godmode_closure._CLOSURE_ROOT_DIRS)
            save_index(atlas, project / godmode_closure._ATLAS_INDEX_FILENAME)
            err = io.StringIO()
            with mock.patch.object(sys, "stderr", err):
                godmode_closure._atlas_for_closure(project)
            self.assertEqual(err.getvalue(), "")

    def test_a_budget_trip_is_named_on_stderr_and_raised(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(raw)
            tripped = Atlas(project=project, gap={"reason": "time budget", "scanned": 1, "unscanned": 2})
            err = io.StringIO()
            with mock.patch.object(godmode_closure, "build_atlas", return_value=tripped), \
                    mock.patch.object(sys, "stderr", err):
                with self.assertRaises(GodmodeError):
                    godmode_closure._atlas_for_closure(project)
            self.assertIn("did not finish within", err.getvalue())
            self.assertIn("1 of 3 files scanned", err.getvalue())

    def test_the_unbounded_rebuild_announces_itself_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = _project(raw)
            err = io.StringIO()
            with mock.patch.object(sys, "stderr", err):
                result = godmode_closure.refresh_atlas_index(project)
            self.assertIsNotNone(result)
            self.assertIn("rebuilding the closure atlas index (unbounded)", err.getvalue())


if __name__ == "__main__":
    unittest.main()
