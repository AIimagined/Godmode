"""One list of directories a walk skips, not two that disagree.

`godmode_constants.IGNORED_DIRECTORY_NAMES` is what the atlas, the
database inventory and the scope fence skip. `godmode_structure` kept its
own `_SKIP_DIRS`, and the two had drifted in both directions: the
structure index walked into `coverage`, `target`, `.research`,
`.evidence` and `.decisions`, while every other walker descended into
`.tox`, `.mypy_cache` and `.pytest_cache`.

Neither is a correctness bug on its own - the index stores names and
hashes, never content, and a cache directory yields junk rather than
danger. The cost is that "which directories does godmode ignore?" had two
answers, and the one a reader found depended on which module they opened.

The union is the honest resolution: every entry on both lists was put
there for a reason by someone, and no reason to walk a build directory or
a type-checker cache has appeared since.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_structure  # noqa: E402
from godmode_runtime.godmode_constants import IGNORED_DIRECTORY_NAMES  # noqa: E402


class SingleOwnerTests(unittest.TestCase):
    def test_the_structure_index_reads_the_shared_list(self) -> None:
        self.assertIs(godmode_structure._SKIP_DIRS, IGNORED_DIRECTORY_NAMES)

    def test_build_output_is_skipped_everywhere(self) -> None:
        for name in ("dist", "build", "coverage", "target", "node_modules"):
            with self.subTest(directory=name):
                self.assertIn(name, IGNORED_DIRECTORY_NAMES)

    def test_tool_caches_are_skipped_everywhere(self) -> None:
        # These lived only in the structure index's private list, so every
        # other walk descended into them.
        for name in (".tox", ".mypy_cache", ".pytest_cache", "__pycache__"):
            with self.subTest(directory=name):
                self.assertIn(name, IGNORED_DIRECTORY_NAMES)

    def test_source_control_metadata_is_skipped_everywhere(self) -> None:
        for name in (".git", ".hg", ".svn"):
            with self.subTest(directory=name):
                self.assertIn(name, IGNORED_DIRECTORY_NAMES)


if __name__ == "__main__":
    unittest.main()
