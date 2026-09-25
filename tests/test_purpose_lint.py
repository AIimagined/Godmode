"""NS-12b: a shipped skill's PURPOSE.md states the problem it solves.

`lint_frontmatter` holds a skill this repository actually ships (one whose
directory is a direct child of a real `skills/`) to a PURPOSE.md that carries
a `## Gap evidence` section stating, in plain public language, the problem
the skill solves. Both are hard, blocking requirements checkable on any
clone: presence of the section, and a minimum of plain prose in it.

A `seq:<n>` token in that section is also a finding, not merely discouraged:
a shipped PURPOSE.md is a public surface every reader of the skill sees,
while a `seq:<n>` cite points at a private, per-checkout archive record that
a fresh clone or CI checkout can never open. That citation belongs in the
local archive that produced it, never in a file that ships.

A fixture skill that is not shipped (not a child of a real `skills/`) is
never held to any of this - covered already by `test_skill_frontmatter.py`'s
generic fixtures, which carry no PURPOSE.md at all and must keep passing
unrelated to this rule.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402

SKILL_MD = """---
name: alpha
description: Use when a change touches the alpha subsystem. Not for beta work or routine reads.
---
# alpha
Body text with no path reference.
"""


def _shipped_skill_fixture(tmp: Path) -> Path:
    """A fixture shaped like this project (`skills/` + `scripts/` at its
    root) with one skill, `skills/alpha`, so `_is_shipped_skill` holds it to
    the PURPOSE.md rule.
    """
    root = tmp / "project"
    (root / "skills" / "alpha").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "skills" / "alpha" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    return root / "skills" / "alpha"


def _purpose_findings(result: dict) -> list[str]:
    return [f for f in result["findings"] if f.startswith("purpose:")]


class PurposeLintTests(unittest.TestCase):
    def test_missing_purpose_file_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            skill_dir = _shipped_skill_fixture(Path(raw))
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("is missing" in f for f in findings), findings)

    def test_purpose_with_no_gap_evidence_section_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            skill_dir = _shipped_skill_fixture(Path(raw))
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nThis skill exists for the alpha subsystem.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("no '## Gap evidence' section" in f for f in findings), findings)

    def test_purpose_with_a_seq_cite_fails(self) -> None:
        """A shipped file carries no private archive citation, resolvable or not."""
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            skill_dir = _shipped_skill_fixture(Path(raw))
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nThis skill exists for the alpha subsystem.\n\n"
                "## Gap evidence\n\nMotivated by seq:999999, a private record.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("cites a private archive record" in f for f in findings), findings)

    def test_purpose_with_a_short_gap_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            skill_dir = _shipped_skill_fixture(Path(raw))
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nThis skill exists for the alpha subsystem.\n\n"
                "## Gap evidence\n\nToo short.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("too short" in f for f in findings), findings)

    def test_purpose_with_a_plain_public_gap_statement_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            skill_dir = _shipped_skill_fixture(Path(raw))
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nThis skill exists for the alpha subsystem.\n\n"
                "## Gap evidence\n\n"
                "Changes to the alpha subsystem were made without anyone checking "
                "whether the beta subsystem depended on the changed behavior, "
                "and the resulting break was only found in production.\n\n"
                "## Promise\n\nAlpha changes are checked against beta first.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertEqual(findings, [], result)

    def test_a_fixture_skill_is_not_held_to_the_purpose_rule(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as raw:
            root = Path(raw)
            skill = root / "alpha"
            skill.mkdir()
            (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
            result = lint_frontmatter(skill)
            findings = _purpose_findings(result)
            self.assertEqual(findings, [], result)


if __name__ == "__main__":
    unittest.main()
