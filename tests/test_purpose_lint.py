"""NS-12b: a shipped skill's PURPOSE.md, and the `seq:` cite it names.

`lint_frontmatter` holds a skill this repository actually ships (one whose
directory is a direct child of a real `skills/`) to a PURPOSE.md naming the
archive record(s) that justified it: present, and citing at least one
well-formed `seq:<n>` token. Both are hard, blocking requirements checkable
on any clone. Whether that cite actually *resolves* in an archive - the
same referential check `require_seq_cite` runs for a `claim --cite seq:`
(`godmode_fingerprint.seq_cite_resolves`) - is reported as an advisory only,
never blocking: the archive that could prove a record real lives in exactly
one checkout (the one that accumulated it), so a fresh clone or CI checkout
opens the same kind of archive, empty, and must not fail a skill for a cite
it simply has no way to check. This suite's own fixtures are the one place
that can prove resolution actually works, because each builds and appends
to its own throwaway archive, so it knows in advance whether a cite ought to
resolve. A fixture skill that is not shipped (not a child of a real
`skills/`) is never held to any of this - covered already by
`test_skill_frontmatter.py`'s generic fixtures, which carry no PURPOSE.md at
all and must keep passing unrelated to this rule.

Every fixture here is its own throwaway git repository, so `resolve_anchor`
gives it its own archive under its own temp state home - never the real
project archive, and no write verb ever touches it, only `Chronicle.append`
against a fixture the test itself created and the OS deletes on cleanup.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
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
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402

SKILL_MD = """---
name: alpha
description: Use when a change touches the alpha subsystem. Not for beta work or routine reads.
---
# alpha
Body text with no path reference.
"""


@contextmanager
def _shipped_skill_fixture():
    """A throwaway repo shaped like this project (`skills/` + `scripts/` at
    its root) with one skill, `skills/alpha`, so `_is_shipped_skill` holds it
    to the PURPOSE.md rule - and its own isolated archive to cite into.
    """
    with tempfile.TemporaryDirectory(prefix="godmode-purpose-") as temporary:
        base = Path(temporary)
        root = base / "project"
        state = base / "private-state"
        (root / "skills" / "alpha").mkdir(parents=True)
        (root / "scripts").mkdir()
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                       ["config", "user.name", "d"]):
            subprocess.run(["git", *command], cwd=root, capture_output=True)
        (root / "skills" / "alpha" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        (root / "seed.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, capture_output=True)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            yield root / "skills" / "alpha"


def _purpose_findings(result: dict) -> list[str]:
    return [f for f in result["findings"] if f.startswith("purpose:")]


def _purpose_advisories(result: dict) -> list[str]:
    return [f for f in result.get("advisories", []) if f.startswith("purpose-unresolved:")]


class PurposeLintTests(unittest.TestCase):
    def test_missing_purpose_file_fails(self) -> None:
        with _shipped_skill_fixture() as skill_dir:
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("is missing" in f for f in findings), findings)

    def test_purpose_with_no_cite_fails(self) -> None:
        with _shipped_skill_fixture() as skill_dir:
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nThis skill exists for the alpha subsystem.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            self.assertFalse(result["passed"], result)
            self.assertTrue(any("cites no seq: record" in f for f in findings), findings)

    def test_purpose_citing_nonexistent_sequence_is_advisory_not_blocking(self) -> None:
        """An unresolved cite is reported, never a `passed`-flipping failure.

        This fixture is the one place that can prove resolution detection
        actually works: it knows `seq:999999` was never appended to its own
        throwaway archive, so it can assert the advisory fires - without
        making that check load-bearing for `passed`, which must stay true
        on any clone that cannot open this archive at all.
        """
        with _shipped_skill_fixture() as skill_dir:
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nMotivated by seq:999999, which nothing ever appended.\n",
                encoding="utf-8",
            )
            root = skill_dir.parent.parent
            archive = Chronicle(resolve_anchor(root))
            result = lint_frontmatter(skill_dir, archive=archive)
            findings = _purpose_findings(result)
            advisories = _purpose_advisories(result)
            self.assertEqual(findings, [], result)
            self.assertTrue(any("does not resolve" in a for a in advisories), advisories)

    def test_purpose_with_resolving_cite_passes_with_no_advisory(self) -> None:
        with _shipped_skill_fixture() as skill_dir:
            root = skill_dir.parent.parent
            archive = Chronicle(resolve_anchor(root))
            record = archive.append(kind="action", subject="purpose-lint-fixture", data={})
            seq = record["sequence"]
            (skill_dir / "PURPOSE.md").write_text(
                f"# Purpose\n\nMotivated by seq:{seq}, a real fixture record.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir, archive=archive)
            findings = _purpose_findings(result)
            advisories = _purpose_advisories(result)
            self.assertEqual(findings, [], result)
            self.assertEqual(advisories, [], result)

    def test_purpose_resolved_by_default_without_an_explicit_archive(self) -> None:
        """`lint_frontmatter` opens the project's own archive when none is
        passed - the path `lint_all` (and therefore `selftest`) actually
        takes for every shipped skill.
        """
        with _shipped_skill_fixture() as skill_dir:
            root = skill_dir.parent.parent
            archive = Chronicle(resolve_anchor(root))
            record = archive.append(kind="action", subject="purpose-lint-fixture", data={})
            seq = record["sequence"]
            (skill_dir / "PURPOSE.md").write_text(
                f"# Purpose\n\nMotivated by seq:{seq}, a real fixture record.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            advisories = _purpose_advisories(result)
            self.assertEqual(findings, [], result)
            self.assertEqual(advisories, [], result)

    def test_purpose_unresolved_by_default_without_an_explicit_archive_stays_advisory(self) -> None:
        """Same default-archive path as above, but for a cite that does not
        resolve: still advisory-only, still `passed`, because the project's
        own archive not holding a record is exactly the fresh-clone/CI case
        this control must never fail on.
        """
        with _shipped_skill_fixture() as skill_dir:
            (skill_dir / "PURPOSE.md").write_text(
                "# Purpose\n\nMotivated by seq:999999, which nothing ever appended.\n",
                encoding="utf-8",
            )
            result = lint_frontmatter(skill_dir)
            findings = _purpose_findings(result)
            advisories = _purpose_advisories(result)
            self.assertEqual(findings, [], result)
            self.assertTrue(any("does not resolve" in a for a in advisories), advisories)


if __name__ == "__main__":
    unittest.main()
