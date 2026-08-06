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
from godmode_runtime.godmode_errors import IdentityError  # noqa: E402
from godmode_runtime.godmode_parity import (  # noqa: E402
    absorption_check,
    parity_matrix,
    schema_ladder,
)


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def _build_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


RICH_TREE = {
    "src/main.py": "print('hello')\n",
    "tests/test_main.py": "def test_main():\n    pass\n",
    ".github/workflows/ci.yml": "name: ci\n",
    "README.md": "# project\n",
    "requirements.txt": "stdlib-only\n",
    "LICENSE": "MIT\n",
}

BARE_TREE = {
    "src/main.py": "print('hello')\n",
    "README.md": "# reference\n",
    "SECURITY.md": "report privately\n",
    "docs/guide.rst": "guide\n",
}

DIMENSIONS = (
    "file-categories", "entry-points", "test-surface", "documentation-surface",
    "configuration", "dependency-declarations", "ci-surface", "licence",
    "security-docs", "version-surfaces", "guidance-surfaces",
)


class ParityMatrixTests(unittest.TestCase):
    def test_divergent_trees_disagree_per_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            reference = base / "reference"
            project.mkdir()
            reference.mkdir()
            _build_tree(project, RICH_TREE)
            _build_tree(reference, BARE_TREE)
            result = parity_matrix(project, reference)
            self.assertFalse(result["aligned"])
            dimensions = result["dimensions"]
            self.assertEqual(sorted(dimensions), sorted(DIMENSIONS))
            # Project has tests and CI, the reference has neither.
            self.assertEqual(dimensions["test-surface"]["verdict"], "project-ahead")
            self.assertEqual(dimensions["test-surface"]["action"], "ignore")
            self.assertEqual(dimensions["ci-surface"]["verdict"], "project-ahead")
            # Reference has more documentation, so the matrix says adopt.
            self.assertEqual(dimensions["documentation-surface"]["verdict"], "reference-ahead")
            self.assertEqual(dimensions["documentation-surface"]["action"], "adopt")
            # Security surfaces never auto-resolve; mismatches demand a human look.
            self.assertEqual(dimensions["security-docs"]["verdict"], "reference-ahead")
            self.assertEqual(dimensions["security-docs"]["action"], "investigate")
            self.assertEqual(dimensions["licence"]["verdict"], "project-ahead")
            self.assertEqual(dimensions["licence"]["action"], "investigate")
            for name in DIMENSIONS:
                entry = dimensions[name]
                self.assertEqual(
                    entry["delta"],
                    entry["present_in_project"] - entry["present_in_reference"],
                )
                self.assertIn(entry["verdict"],
                              ("aligned", "project-ahead", "reference-ahead", "both-empty"))
                self.assertIn(entry["action"], ("adopt", "ignore", "investigate", "none"))

    def test_identical_trees_align_on_every_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            reference = base / "reference"
            project.mkdir()
            reference.mkdir()
            _build_tree(project, RICH_TREE)
            _build_tree(reference, RICH_TREE)
            result = parity_matrix(project, reference)
            self.assertTrue(result["aligned"])
            for entry in result["dimensions"].values():
                self.assertIn(entry["verdict"], ("aligned", "both-empty"))
                self.assertEqual(entry["action"], "none")
                self.assertEqual(entry["delta"], 0)
            self.assertNotIn("reference_staleness", result)

    def test_stale_reference_is_labelled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            reference = base / "reference"
            project.mkdir()
            reference.mkdir()
            _build_tree(project, RICH_TREE)
            _build_tree(reference, RICH_TREE)
            behind = 60 * 86400
            for current, _dirs, files in os.walk(reference):
                for name in files:
                    path = Path(current) / name
                    stamp = path.stat().st_mtime - behind
                    os.utime(path, (stamp, stamp))
            result = parity_matrix(project, reference)
            self.assertIn("reference_staleness", result)
            self.assertTrue(result["reference_staleness"].startswith("stale ("))
            self.assertIn("days behind", result["reference_staleness"])

    def test_network_reference_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaises(IdentityError):
                parity_matrix(project, "git://example.invalid/repo")

    def test_missing_reference_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaises(IdentityError):
                parity_matrix(project, project / "does-not-exist")


class AbsorptionTests(unittest.TestCase):
    def test_absorbed_only_after_reader_and_guard(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            path = "vendor/synced.py"

            unwired = absorption_check(archive, path)
            self.assertFalse(unwired["absorbed"])
            self.assertEqual(unwired["missing"], ["reader", "guard"])
            self.assertIsNone(unwired["reader"])
            self.assertIsNone(unwired["guard"])

            archive.append(
                "change", "adopt vendored helper",
                {"files": [path], "summary": "wired into loader"},
                evidence=[f"file:{path}#L1-L10"],
            )
            half_wired = absorption_check(archive, path)
            self.assertFalse(half_wired["absorbed"])
            self.assertEqual(half_wired["missing"], ["guard"])
            self.assertIsNotNone(half_wired["reader"])

            # A guard that never ran does not count.
            archive.append(
                "attestation", "guard:vendor-integrity",
                {"status": "blocked", "session": "s1"},
                evidence=[f"file:{path}"],
            )
            still_unguarded = absorption_check(archive, path)
            self.assertFalse(still_unguarded["absorbed"])

            archive.append(
                "attestation", "guard:vendor-integrity",
                {"status": "ran", "session": "s1"},
                evidence=[f"file:{path}"],
            )
            absorbed = absorption_check(archive, path)
            self.assertTrue(absorbed["absorbed"])
            self.assertEqual(absorbed["missing"], [])
            self.assertIsNotNone(absorbed["reader"])
            self.assertIsNotNone(absorbed["guard"])
            self.assertEqual(absorbed["path"], path)

    def test_guard_alone_is_not_a_reader(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            path = "vendor/lonely.py"
            archive.append(
                "attestation", "guard:lonely",
                {"status": "ran", "session": "s1"},
                evidence=[f"file:{path}"],
            )
            result = absorption_check(archive, path)
            self.assertFalse(result["absorbed"])
            self.assertEqual(result["missing"], ["reader"])


class SchemaLadderTests(unittest.TestCase):
    def test_existing_column_wins_rung_one(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            decision = schema_ladder(archive, {
                "change": "store the user's email address",
                "existing_tables": ["users"],
                "existing_columns": {"users": ["email", "created_at"]},
                "proposed_table": None,
                "proposed_column": "email_address",
            })
            self.assertEqual(decision["rung"], 1)
            self.assertTrue(decision["approved"])
            self.assertFalse(decision["requires_review"])
            self.assertIn("users.email", decision["decision"])

    def test_existing_table_wins_over_new_table(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            decision = schema_ladder(archive, {
                "change": "track order line items",
                "existing_tables": ["orders"],
                "existing_columns": {"orders": ["id", "total"]},
                "proposed_table": "order_items",
                "proposed_column": "sku",
            })
            self.assertLessEqual(decision["rung"], 2)
            self.assertTrue(decision["approved"])
            self.assertFalse(decision["requires_review"])
            self.assertIn("orders", decision["decision"])

    def test_unreviewed_new_table_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            decision = schema_ladder(archive, {
                "change": "collect crash reports",
                "existing_tables": ["users"],
                "existing_columns": {"users": ["email"]},
                "proposed_table": "crashes",
                "proposed_column": "trace",
            })
            self.assertEqual(decision["rung"], 3)
            self.assertTrue(decision["requires_review"])
            self.assertFalse(decision["approved"])

    def test_reviewed_new_table_is_approved(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            decision = schema_ladder(archive, {
                "change": "collect crash reports",
                "existing_tables": ["users"],
                "existing_columns": {"users": ["email"]},
                "proposed_table": "crashes",
                "proposed_column": "trace",
                "review": "reviewed: distinct write pattern, no existing fit",
            })
            self.assertEqual(decision["rung"], 3)
            self.assertTrue(decision["requires_review"])
            self.assertTrue(decision["approved"])


if __name__ == "__main__":
    unittest.main()
