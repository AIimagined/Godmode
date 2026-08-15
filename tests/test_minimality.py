"""godmode minimality: one ranked view over four existing surfaces.

Aggregation only. Each test holds the report to a surface that already has
its own tests: the report must not invent a count those surfaces did not
produce, and an empty project must report zeros with a stated basis rather
than a manufactured finding.
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

from godmode_runtime.godmode_atlas import build, speculative_seams  # noqa: E402
from godmode_runtime.godmode_minimality import minimality_report  # noqa: E402

_EXPECTED_SECTIONS = {
    "duplicate-symbols", "orphan-symbols", "speculative-seams",
    "unexercised-surfaces", "charter-decay",
}


class SectionsPresentTests(unittest.TestCase):
    def test_every_expected_section_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            report = minimality_report(project, archive=None)
            names = {s["section"] for s in report["sections"]}
            self.assertEqual(names, _EXPECTED_SECTIONS)
            for section in report["sections"]:
                self.assertIn("basis", section)
                self.assertIn("count", section)
                self.assertIn("items", section)

    def test_sections_are_ranked_by_count_descending(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            report = minimality_report(project, archive=None)
            counts = [s["count"] for s in report["sections"]]
            self.assertEqual(counts, sorted(counts, reverse=True))


class CountsMatchUnderlyingSurfacesTests(unittest.TestCase):
    def test_atlas_counts_match_the_atlas_functions_directly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            # Two near-identical functions (duplicate), one function nothing
            # calls (orphan), and a module only one non-test file imports
            # (speculative seam).
            (project / "seam.py").write_text(
                "def seam_helper():\n    return 1\n", encoding="utf-8")
            (project / "consumer.py").write_text(
                "from seam import seam_helper\n\n\ndef use_it():\n    return seam_helper()\n",
                encoding="utf-8")
            (project / "twin_a.py").write_text(
                "def compute_total(items):\n"
                "    total = 0\n"
                "    for item in items:\n"
                "        total = total + item\n"
                "    return total\n", encoding="utf-8")
            (project / "twin_b.py").write_text(
                "def compute_sum(values):\n"
                "    total = 0\n"
                "    for item in values:\n"
                "        total = total + item\n"
                "    return total\n", encoding="utf-8")
            (project / "unreached.py").write_text(
                "def nobody_calls_this():\n    return 42\n", encoding="utf-8")

            atlas = build(project)
            expected_duplicates = len(atlas.duplicates())
            expected_orphans = len(atlas.orphans())
            expected_seams = len(speculative_seams(atlas)["findings"])

            report = minimality_report(project, archive=None)
            by_section = {s["section"]: s["count"] for s in report["sections"]}
            self.assertEqual(by_section["duplicate-symbols"], expected_duplicates)
            self.assertEqual(by_section["orphan-symbols"], expected_orphans)
            self.assertEqual(by_section["speculative-seams"], expected_seams)
            self.assertGreaterEqual(expected_seams, 1, "fixture must produce a real seam")

    def test_total_findings_is_the_sum_of_every_section(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            report = minimality_report(project, archive=None)
            self.assertEqual(
                report["total_findings"], sum(s["count"] for s in report["sections"]))


class EmptyProjectHonestZerosTests(unittest.TestCase):
    def test_an_empty_project_reports_zeros_with_a_basis_not_a_manufactured_finding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            report = minimality_report(project, archive=None)
            self.assertEqual(report["total_findings"], 0)
            self.assertEqual(report["verdict"], "minimal")
            for section in report["sections"]:
                self.assertEqual(section["count"], 0)
                self.assertTrue(section["basis"], f"{section['section']} has no stated basis")
                self.assertEqual(section["items"], [])

    def test_no_archive_states_the_basis_as_no_archive_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            report = minimality_report(project, archive=None)
            by_section = {s["section"]: s for s in report["sections"]}
            self.assertIn("no archive", by_section["unexercised-surfaces"]["basis"])
            self.assertIn("no archive", by_section["charter-decay"]["basis"])


if __name__ == "__main__":
    unittest.main()
