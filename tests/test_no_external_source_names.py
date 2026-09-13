"""No shipped surface carries a name the project asked to keep out of it.

Whether a project publishes what it read, referenced or learned from is the
project's decision. This check enforces whatever was declared and takes no
position of its own; supplying no list leaves the class quiet.

The deny class needs a list supplied at runtime, so when none is present it
reports `unmeasured` rather than clean - an absent instrument is graded
distinctly from a negative result (R8).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import no_external_source_names as N  # noqa: E402


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(body)
    return path


class DenyNames(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_planted_deny_name_is_reported(self) -> None:
        _write(self.tmp, "README.md", "We took the manifest idea from Acmeforge.\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], deny_names=["acmeforge"])
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0].kind, "deny-name")
        self.assertEqual(findings[0].line, 1)

    def test_the_match_is_case_insensitive(self) -> None:
        _write(self.tmp, "README.md", "see ACMEFORGE for details\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], deny_names=["acmeforge"])
        self.assertEqual(len(findings), 1, findings)

    def test_a_clean_surface_reports_nothing(self) -> None:
        _write(self.tmp, "README.md", "An install writes a manifest of what it created.\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], deny_names=["acmeforge"])
        self.assertEqual(findings, [])

    def test_a_substring_of_a_longer_word_is_not_a_match(self) -> None:
        """`roma` must not fire on `aroma`. A guard that cries wolf gets disabled."""
        _write(self.tmp, "README.md", "the aromatic branch\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], deny_names=["roma"])
        self.assertEqual(findings, [])


class ForgeUrls(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_forge_url_is_reported_without_any_list(self) -> None:
        _write(self.tmp, "docs/x.md", "see https://github.com/someone/somerepo for prior art\n")
        findings = N.scan(self.tmp, [self.tmp / "docs" / "x.md"], deny_names=None)
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0].kind, "forge-url")

    def test_our_own_documentation_links_are_not_findings(self) -> None:
        """A link to a language or a standard is not a source identity."""
        _write(self.tmp, "docs/x.md", "see https://docs.python.org/3/library/json.html\n")
        findings = N.scan(self.tmp, [self.tmp / "docs" / "x.md"], deny_names=None)
        self.assertEqual(findings, [])


class AbsentInstrument(unittest.TestCase):
    def test_no_list_grades_that_class_unmeasured_not_clean(self) -> None:
        report = N.report(deny_names=None, findings=[])
        self.assertEqual(report["deny_class"], "unmeasured")
        self.assertEqual(report["forge_class"], "clean")

    def test_a_list_present_and_clean_says_clean(self) -> None:
        report = N.report(deny_names=["acmeforge"], findings=[])
        self.assertEqual(report["deny_class"], "clean")


class FindingShape(unittest.TestCase):
    def test_every_finding_carries_a_remedy(self) -> None:
        """R15: a finding without a remedy is malformed."""
        import tempfile

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            _write(tmp, "README.md", "Acmeforge did it first.\n")
            findings = N.scan(tmp, [tmp / "README.md"], deny_names=["acmeforge"])
            self.assertTrue(findings)
            for finding in findings:
                self.assertTrue(finding.remedy, f"no remedy on {finding}")


class TheRealTree(unittest.TestCase):
    def test_the_tracked_tree_has_no_forge_urls_in_shipped_surfaces(self) -> None:
        paths = N.shipped_paths(PLUGIN_ROOT)
        self.assertTrue(paths, "no shipped surfaces found; the selector is wrong")
        findings = [f for f in N.scan(PLUGIN_ROOT, paths, deny_names=None)]
        self.assertEqual(findings, [], f"forge URLs in shipped surfaces: {findings}")


if __name__ == "__main__":
    unittest.main()
