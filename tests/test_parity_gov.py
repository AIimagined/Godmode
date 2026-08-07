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
from godmode_runtime.godmode_errors import ArchiveError, IdentityError  # noqa: E402
from godmode_runtime.godmode_parity import (  # noqa: E402
    absorption_check,
    adoption_floor,
    parity_matrix,
    schema_ladder,
    waive,
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


@contextmanager
def two_trees(project_files: dict[str, str], reference_files: dict[str, str]):
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        reference = base / "reference"
        project.mkdir()
        reference.mkdir()
        _build_tree(project, project_files)
        _build_tree(reference, reference_files)
        yield project, reference


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
    "capability", "architecture", "runtime-wiring", "tests", "documentation",
    "configuration", "dependency-declarations", "licence", "security-docs",
    "identity-freshness", "project-invariants",
)

VERDICTS = ("ADOPT", "EXTEND", "DIVERGE-DELIBERATELY", "REJECT", "ALIGNED")


class ParityMatrixTests(unittest.TestCase):
    def test_divergent_trees_disagree_per_dimension(self) -> None:
        with two_trees(RICH_TREE, BARE_TREE) as (project, reference):
            result = parity_matrix(project, reference)
            self.assertFalse(result["aligned"])
            self.assertFalse(result["accepted"])
            dimensions = result["dimensions"]
            self.assertEqual(sorted(dimensions), sorted(DIMENSIONS))
            # Project has tests the reference lacks: an extension to keep, never ignore.
            self.assertEqual(dimensions["tests"]["verdict"], "EXTEND")
            self.assertIn("tests/test_main.py", dimensions["tests"]["local_extensions"])
            # The project also exposes a public symbol the reference has no twin for.
            self.assertEqual(dimensions["capability"]["verdict"], "EXTEND")
            self.assertIn("test_main", dimensions["capability"]["local_extensions"])
            # Reference has more documentation, so the matrix names adopt candidates.
            self.assertEqual(dimensions["documentation"]["verdict"], "ADOPT")
            self.assertIn("SECURITY.md", dimensions["documentation"]["adopt_candidates"])
            # Sensitive surfaces never auto-resolve; divergence must be deliberate.
            self.assertEqual(dimensions["security-docs"]["verdict"], "DIVERGE-DELIBERATELY")
            self.assertEqual(dimensions["licence"]["verdict"], "DIVERGE-DELIBERATELY")
            for name in DIMENSIONS:
                entry = dimensions[name]
                self.assertEqual(
                    entry["delta"],
                    entry["present_in_project"] - entry["present_in_reference"],
                )
                self.assertIn(entry["verdict"], VERDICTS)
                self.assertTrue(entry["reason"])
                self.assertNotIn("\n", entry["reason"])

    def test_identical_trees_align_on_every_dimension(self) -> None:
        with two_trees(RICH_TREE, RICH_TREE) as (project, reference):
            result = parity_matrix(project, reference)
            self.assertTrue(result["aligned"])
            self.assertTrue(result["accepted"])
            for entry in result["dimensions"].values():
                self.assertEqual(entry["verdict"], "ALIGNED")
                self.assertEqual(entry["delta"], 0)
            self.assertNotIn("reference_staleness", result)

    def test_stale_reference_is_labelled(self) -> None:
        with two_trees(RICH_TREE, RICH_TREE) as (project, reference):
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
            freshness = result["dimensions"]["identity-freshness"]
            self.assertEqual(freshness["verdict"], "DIVERGE-DELIBERATELY")

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


class CapabilityDimensionTests(unittest.TestCase):
    def test_reference_extra_symbol_is_named_adopt_candidate(self) -> None:
        with two_trees(
            {"pkg/mod.py": "def alpha():\n    return 1\n"},
            {"pkg/mod.py": "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"},
        ) as (project, reference):
            result = parity_matrix(project, reference)
            capability = result["dimensions"]["capability"]
            self.assertEqual(capability["verdict"], "ADOPT")
            self.assertEqual(capability["adopt_candidates"], ["beta"])
            self.assertIn("beta", capability["reason"])
            # An open ADOPT recommendation blocks acceptance until it is waived.
            self.assertFalse(result["accepted"])

    def test_project_only_symbol_is_extend_never_ignore(self) -> None:
        with two_trees(
            {"pkg/mod.py": "def alpha():\n    return 1\n\ndef gamma():\n    return 3\n"},
            {"pkg/mod.py": "def alpha():\n    return 1\n"},
        ) as (project, reference):
            result = parity_matrix(project, reference)
            capability = result["dimensions"]["capability"]
            self.assertEqual(capability["verdict"], "EXTEND")
            self.assertEqual(capability["local_extensions"], ["gamma"])
            self.assertIn("gamma", capability["reason"])


class AcceptanceGatingTests(unittest.TestCase):
    def test_waive_records_reason_and_flips_accepted(self) -> None:
        with two_trees(
            {"pkg/mod.py": "def alpha():\n    return 1\n"},
            {"pkg/mod.py": "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"},
        ) as (project, reference):
            result = parity_matrix(project, reference)
            self.assertFalse(result["accepted"])
            waive(result, "capability", "beta arrives with the next milestone")
            self.assertEqual(
                result["dimensions"]["capability"]["waived"]["reason"],
                "beta arrives with the next milestone",
            )
            self.assertTrue(result["accepted"])

    def test_waive_requires_reason_and_known_dimension(self) -> None:
        with two_trees(
            {"pkg/mod.py": "def alpha():\n    return 1\n"},
            {"pkg/mod.py": "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"},
        ) as (project, reference):
            result = parity_matrix(project, reference)
            with self.assertRaises(ArchiveError):
                waive(result, "capability", "   ")
            with self.assertRaises(ArchiveError):
                waive(result, "no-such-dimension", "reason")


class AdoptionFloorTests(unittest.TestCase):
    def test_invariant_record_flips_adopt_to_reject(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _build_tree(project, {
                "settings.toml": "[local]\nfix = true\n",
                "patches/fix.py": "# protected local fix, no symbols\n",
            })
            reference = project.parent / "reference"
            reference.mkdir()
            _build_tree(reference, {
                "settings.toml": "[local]\nfix = false\n",
                "extra.toml": "[extra]\n",
                "docs/guide.md": "# guide\n",
            })
            archive.append(
                "invariant", "local settings fix must persist",
                {"status": "active"}, evidence=["file:settings.toml"],
            )
            archive.append(
                "invariant", "local patch is deliberate",
                {"status": "active"}, evidence=["file:patches/fix.py"],
            )
            result = parity_matrix(project, reference, archive=archive)
            configuration = result["dimensions"]["configuration"]
            self.assertEqual(configuration["verdict"], "REJECT")
            self.assertEqual(
                configuration["reason"],
                "protected local fix; parity is a floor, not a ceiling",
            )
            self.assertEqual(result["floor"]["flipped"]["configuration"], ["settings.toml"])
            # An ADOPT with no protected overlap keeps its recommendation.
            self.assertEqual(result["dimensions"]["documentation"]["verdict"], "ADOPT")
            self.assertNotIn("documentation", result["floor"]["flipped"])
            # The invariant citing a project-only path surfaces as the E-14 floor.
            invariants = result["dimensions"]["project-invariants"]
            self.assertEqual(invariants["verdict"], "DIVERGE-DELIBERATELY")
            self.assertEqual(invariants["protected_paths"], ["patches/fix.py"])

    def test_floor_without_overlap_changes_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _build_tree(project, {"settings.toml": "[local]\n"})
            reference = project.parent / "reference"
            reference.mkdir()
            _build_tree(reference, {"settings.toml": "[local]\n", "extra.toml": "[extra]\n"})
            archive.append(
                "invariant", "unrelated invariant",
                {"status": "active"}, evidence=["file:elsewhere/thing.py"],
            )
            matrix = parity_matrix(project, reference)
            self.assertEqual(matrix["dimensions"]["configuration"]["verdict"], "ADOPT")
            report = adoption_floor(archive, matrix)
            self.assertEqual(report["flipped"], {})
            self.assertEqual(matrix["dimensions"]["configuration"]["verdict"], "ADOPT")


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
