"""L2 of the structure index: who calls what, across files.

Absorbed 2026-08-27 from an upstream code-analysis stack whose second
layer is the cross-file call graph. This index had names and imports (L1)
and nothing about use. Each Python entry now carries `calls` - per
top-level function, the names it calls - and `dependencies`, the other
indexed files that define those names. Names only, never bodies, the same
privacy line the index has always held; a callee nobody in the index
defines (a builtin, a library) is kept in `calls` and resolves to no
dependency, which is itself a fact worth reading.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_structure import (  # noqa: E402
    _load_index, build_structure_index, structure_outline,
)


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-l2-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "a.py").write_text("def helper(x):\n    return x + 1\n", encoding="utf-8")
        (root / "b.py").write_text(
            "import os\nfrom a import helper\n\n"
            "def run(p):\n    y = helper(3)\n    return os.path.join(p, str(y))\n\n"
            "class Runner:\n    def go(self):\n        return run('.')\n",
            encoding="utf-8")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


class CallGraphTests(unittest.TestCase):
    def test_calls_and_cross_file_dependencies_are_indexed(self) -> None:
        with _project() as (root, archive):
            report = build_structure_index(archive, root)
            entry = _load_index(archive)["files"]["b.py"]
        self.assertEqual(entry["calls"]["run"], ["helper", "join", "str"])
        self.assertEqual(entry["calls"]["Runner.go"], ["run"])
        self.assertEqual(entry["dependencies"], ["a.py"])
        self.assertEqual(report["edges"], 1)

    def test_the_outline_shows_the_dependency_not_the_body(self) -> None:
        with _project() as (root, archive):
            build_structure_index(archive, root)
            outline = structure_outline(archive)
        self.assertIn("b.py", outline)
        self.assertIn("-> a.py", outline)
        self.assertNotIn("x + 1", outline)
        self.assertNotIn("os.path.join", outline)


if __name__ == "__main__":
    unittest.main()
