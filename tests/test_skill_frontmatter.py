"""Every shipped skill's frontmatter passes the linter; a seeded bad one fails.

The linter is a selftest control so a skill cannot ship with an over-broad
description, a missing negative-scope clause, or a path that does not exist.
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

from godmode_runtime.godmode_skillfront import lint_all, lint_frontmatter  # noqa: E402

GOOD = """---
name: alpha
description: Use when a change touches the alpha subsystem. Not for beta work or routine reads.
---
# alpha
See `README.md` for the layout.
"""


class FrontmatterLintTests(unittest.TestCase):
    def _skill(self, text: str) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, root, ignore_errors=True)
        (root / "README.md").write_text("layout\n", encoding="utf-8")
        skill = root / "alpha"
        skill.mkdir()
        (skill / "SKILL.md").write_text(text, encoding="utf-8")
        return skill

    def test_good_skill_passes(self) -> None:
        result = lint_frontmatter(self._skill(GOOD))
        self.assertTrue(result["passed"], result)

    def test_missing_negative_scope_fails(self) -> None:
        bad = GOOD.replace(" Not for beta work or routine reads.", "")
        result = lint_frontmatter(self._skill(bad))
        self.assertFalse(result["passed"])
        self.assertTrue(any(f.startswith("negative-scope") for f in result["findings"]), result)

    def test_orphan_reference_fails(self) -> None:
        bad = GOOD.replace("`README.md`", "`docs/does-not-exist.md`")
        result = lint_frontmatter(self._skill(bad))
        self.assertTrue(any(f.startswith("orphan-reference") for f in result["findings"]), result)

    def test_over_budget_fails(self) -> None:
        bad = GOOD.replace("Not for beta work", "Not for beta work " + "x" * 1100)
        result = lint_frontmatter(self._skill(bad))
        self.assertTrue(any(f.startswith("budget") for f in result["findings"]), result)

    def test_repo_root_fallback_does_not_reach_sideways_skills_scripts_dirs(self) -> None:
        """A sibling directory that happens to carry skills/ and scripts/ is not the root.

        `_repo_root` only walks a skill directory's own ancestors, never siblings,
        so a decoy that is not on that chain must not be picked up by the fallback.
        """
        from godmode_runtime.godmode_skillfront import _repo_root

        outer = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, outer, ignore_errors=True)
        decoy = outer / "decoy"
        (decoy / "skills").mkdir(parents=True)
        (decoy / "scripts").mkdir(parents=True)
        skill = outer / "alpha"
        skill.mkdir()
        (skill / "SKILL.md").write_text(GOOD, encoding="utf-8")

        root = _repo_root(skill)

        self.assertEqual(root, skill.parent.parent)
        self.assertNotEqual(root, decoy)

    def test_every_shipped_skill_passes(self) -> None:
        report = lint_all(PLUGIN_ROOT / "skills")
        self.assertTrue(report["passed"], report["per_skill"])


if __name__ == "__main__":
    unittest.main()
