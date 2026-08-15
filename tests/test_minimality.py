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
from godmode_runtime.godmode_minimality import (  # noqa: E402
    duplicate_authority_findings, minimality_report,
)

_EXPECTED_SECTIONS = {
    "duplicate-symbols", "orphan-symbols", "speculative-seams",
    "unexercised-surfaces", "charter-decay", "duplicate-authority",
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


# GAP-2: duplicate-authority. Two or more independently-declared data
# literals asserting one fact, fingerprinted by member-set Jaccard reusing
# godmode_atlas._jaccard - the same near-dup machinery `duplicates()` above
# already applies to name/body shingles, applied here to literal members.
class DuplicateAuthorityCollectionTests(unittest.TestCase):
    def test_two_source_lists_seventy_percent_shared_are_flagged_naming_both(self) -> None:
        # B is a 7-of-10 subset of A: |intersection|/|union| = 7/10 = 0.7,
        # over the default 0.6 threshold. Neither file is under tests/, so
        # the test-vs-source exemption never applies here.
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "list_a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\", \"hotel\", \"india\", \"juliet\"]\n",
                encoding="utf-8")
            (project / "list_b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\"]\n",
                encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["verdict"], "duplicate-authority-found")
        self.assertEqual(len(report["findings"]), 1)
        hit = report["findings"][0]
        self.assertAlmostEqual(hit["similarity"], 0.7)
        named = {hit["a"]["path"], hit["b"]["path"]}
        self.assertEqual(named, {"list_a.py", "list_b.py"})

    def test_two_source_lists_fifty_percent_shared_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "list_a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\", \"hotel\", \"india\", \"juliet\"]\n",
                encoding="utf-8")
            (project / "list_b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\"]\n",
                encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["verdict"], "no-drift-found")
        self.assertEqual(report["findings"], [])

    def test_threshold_is_tunable(self) -> None:
        """The default-0.6 threshold documented in the report is a real
        parameter, not a number baked past reach."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "list_a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\", \"hotel\", \"india\", \"juliet\"]\n",
                encoding="utf-8")
            (project / "list_b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\"]\n",
                encoding="utf-8")
            tightened = duplicate_authority_findings(project, threshold=0.9)
            loosened = duplicate_authority_findings(project, threshold=0.4)
        self.assertEqual(tightened["findings"], [])
        self.assertEqual(len(loosened["findings"]), 1)

    def test_exact_test_fixture_vs_source_is_exempt(self) -> None:
        """The classic false positive this class of detector earns a bad
        reputation from: a test fixture intentionally restates a source
        list verbatim as a known-good sample. Exempted only when the match
        is EXACT and only one side is under tests/."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "constants.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\"]\n", encoding="utf-8")
            tests_dir = project / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_roles.py").write_text(
                "EXPECTED_ROLES = [\"alpha\", \"bravo\", \"charlie\"]\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["findings"], [])

    def test_near_but_not_exact_test_vs_source_still_flags(self) -> None:
        """A fixture that has drifted from the source it samples - not an
        exact mirror - is exactly the drift this detector exists to catch,
        even across a test/source boundary."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "constants.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\"]\n",
                encoding="utf-8")
            tests_dir = project / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_roles.py").write_text(
                "EXPECTED_ROLES = [\"alpha\", \"bravo\", \"charlie\", \"delta\"]\n",
                encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(len(report["findings"]), 1)

    def test_two_source_sites_exact_match_still_flags(self) -> None:
        """Two SOURCE sites (no test/ on either side) at 100% similarity are
        not exempted - only the test-vs-source pairing is."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\"]\n", encoding="utf-8")
            (project / "b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\"]\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["findings"][0]["similarity"], 1.0)

    def test_a_collection_with_fewer_than_three_members_is_not_a_candidate(self) -> None:
        """Two members is almost always a deliberate pair, not an
        enumeration someone might independently duplicate; below the
        minimum-members floor, nothing is even extracted to compare."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text("PAIR = [\"on\", \"off\"]\n", encoding="utf-8")
            (project / "b.py").write_text("SWITCH = [\"on\", \"off\"]\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["collections_examined"], 0)
        self.assertEqual(report["findings"], [])

    def test_enum_like_dict_keys_are_compared_as_membership(self) -> None:
        """A dict's keys are the vocabulary being asserted (the
        EVENT_KINDS/MASKS shape) - values are per-key detail a second site
        restating the vocabulary would not need to copy."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "kinds.py").write_text(
                "KINDS = frozenset({\"one\", \"two\", \"three\", \"four\"})\n", encoding="utf-8")
            (project / "masks.py").write_text(
                "MASKS = {\"one\": (\"a\",), \"two\": (\"b\",), \"three\": (\"c\",)}\n",
                encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(sorted(report["findings"][0]["shared_members"]), ["one", "three", "two"])


class DuplicateAuthorityVersionTests(unittest.TestCase):
    def test_disagreeing_version_pins_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "constants.py").write_text(
                "RUNTIME_VERSION = \"1.2.3\"\n", encoding="utf-8")
            (project / "plugin.json").write_text(
                "{\"name\": \"x\", \"version\": \"1.2.4\"}\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["verdict"], "duplicate-authority-found")
        version_hits = [f for f in report["findings"] if f["kind"] == "version"]
        self.assertEqual(len(version_hits), 1)
        self.assertEqual(version_hits[0]["a"]["value"], "1.2.3")
        self.assertEqual(version_hits[0]["b"]["value"], "1.2.4")

    def test_agreeing_version_pins_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "constants.py").write_text(
                "RUNTIME_VERSION = \"1.2.3\"\n", encoding="utf-8")
            (project / "plugin.json").write_text(
                "{\"name\": \"x\", \"version\": \"1.2.3\"}\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["findings"], [])

    def test_an_unrelated_numeric_string_is_not_pulled_in_by_value_shape_alone(self) -> None:
        """The name hint gates the comparison; a numeric-looking string
        assigned to a variable that says nothing about a version is never
        compared against an actual version pin just because it parses as
        digits-and-dots."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "constants.py").write_text(
                "RUNTIME_VERSION = \"1.2.3\"\n", encoding="utf-8")
            (project / "ratios.py").write_text(
                "ASPECT_RATIO = \"1.2.9\"\n", encoding="utf-8")
            report = duplicate_authority_findings(project)
        self.assertEqual(report["version_literals_examined"], 1)
        self.assertEqual(report["findings"], [])


class MagicCountNoteTests(unittest.TestCase):
    def test_the_report_carries_a_magic_count_advisory_note(self) -> None:
        """The spec's third ask: name the magic-count anti-pattern
        (`assert len(x) == N`) and recommend subset/superset assertions -
        no code enforcement of it in v1, just the note."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            report = duplicate_authority_findings(project)
        self.assertIn("magic-count", report["note"])
        self.assertIn("subset", report["note"])

    def test_the_note_reaches_the_minimality_report_too(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            report = minimality_report(project, archive=None)
            by_section = {s["section"]: s for s in report["sections"]}
            self.assertIn("magic-count", by_section["duplicate-authority"]["note"])


class MinimalityReportWiringTests(unittest.TestCase):
    def test_the_duplicate_authority_section_count_matches_the_detector(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "list_a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\", \"hotel\", \"india\", \"juliet\"]\n",
                encoding="utf-8")
            (project / "list_b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\"]\n",
                encoding="utf-8")
            expected = duplicate_authority_findings(project)
            report = minimality_report(project, archive=None)
            by_section = {s["section"]: s for s in report["sections"]}
            self.assertEqual(by_section["duplicate-authority"]["count"],
                             len(expected["findings"]))

    def test_threshold_kwarg_flows_through_minimality_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "list_a.py").write_text(
                "ROLE_NAMES = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\", \"hotel\", \"india\", \"juliet\"]\n",
                encoding="utf-8")
            (project / "list_b.py").write_text(
                "ROLE_LABELS = [\"alpha\", \"bravo\", \"charlie\", \"delta\", \"echo\", "
                "\"foxtrot\", \"golf\"]\n",
                encoding="utf-8")
            report = minimality_report(project, archive=None, duplicate_authority_threshold=0.9)
            by_section = {s["section"]: s for s in report["sections"]}
            self.assertEqual(by_section["duplicate-authority"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
