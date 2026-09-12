"""No shipped surface names an outside project.

The rule that research provenance stays in the private ledger and never enters
a tracked file has been enforced by attention. Attention is the wrong
instrument: a single session wrote a 274-line source sweep whose entire subject
was outside projects, and two work-item keys naming an outside project had
already been sitting in the coverage manifest for a day.

The ledger half of this check needs the ledger, which is deliberately outside
this repository. When it is absent the check reports that class as
`unmeasured` rather than clean - an absent instrument is graded distinctly from
a negative result (R8).
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


class LedgerNames(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_planted_ledger_name_is_reported(self) -> None:
        _write(self.tmp, "README.md", "We took the manifest idea from Acmeforge.\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], ledger_names=["acmeforge"])
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0].kind, "ledger-name")
        self.assertEqual(findings[0].line, 1)

    def test_the_match_is_case_insensitive(self) -> None:
        _write(self.tmp, "README.md", "see ACMEFORGE for details\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], ledger_names=["acmeforge"])
        self.assertEqual(len(findings), 1, findings)

    def test_a_clean_surface_reports_nothing(self) -> None:
        _write(self.tmp, "README.md", "An install writes a manifest of what it created.\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], ledger_names=["acmeforge"])
        self.assertEqual(findings, [])

    def test_a_substring_of_a_longer_word_is_not_a_match(self) -> None:
        """`roma` must not fire on `aroma`. A guard that cries wolf gets disabled."""
        _write(self.tmp, "README.md", "the aromatic branch\n")
        findings = N.scan(self.tmp, [self.tmp / "README.md"], ledger_names=["roma"])
        self.assertEqual(findings, [])


class ForgeUrls(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_forge_url_is_reported_without_any_ledger(self) -> None:
        _write(self.tmp, "docs/x.md", "see https://github.com/someone/somerepo for prior art\n")
        findings = N.scan(self.tmp, [self.tmp / "docs" / "x.md"], ledger_names=None)
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0].kind, "forge-url")

    def test_our_own_documentation_links_are_not_findings(self) -> None:
        """A link to a language or a standard is not a source identity."""
        _write(self.tmp, "docs/x.md", "see https://docs.python.org/3/library/json.html\n")
        findings = N.scan(self.tmp, [self.tmp / "docs" / "x.md"], ledger_names=None)
        self.assertEqual(findings, [])


class AbsentInstrument(unittest.TestCase):
    def test_no_ledger_grades_that_class_unmeasured_not_clean(self) -> None:
        report = N.report(ledger_names=None, findings=[])
        self.assertEqual(report["ledger_class"], "unmeasured")
        self.assertEqual(report["forge_class"], "clean")

    def test_a_ledger_present_and_clean_says_clean(self) -> None:
        report = N.report(ledger_names=["acmeforge"], findings=[])
        self.assertEqual(report["ledger_class"], "clean")


class FindingShape(unittest.TestCase):
    def test_every_finding_carries_a_remedy(self) -> None:
        """R15: a finding without a remedy is malformed."""
        import tempfile

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            _write(tmp, "README.md", "Acmeforge did it first.\n")
            findings = N.scan(tmp, [tmp / "README.md"], ledger_names=["acmeforge"])
            self.assertTrue(findings)
            for finding in findings:
                self.assertTrue(finding.remedy, f"no remedy on {finding}")


class TheRealTree(unittest.TestCase):
    def test_the_tracked_tree_has_no_forge_urls_in_shipped_surfaces(self) -> None:
        paths = N.shipped_paths(PLUGIN_ROOT)
        self.assertTrue(paths, "no shipped surfaces found; the selector is wrong")
        findings = [f for f in N.scan(PLUGIN_ROOT, paths, ledger_names=None)]
        self.assertEqual(findings, [], f"forge URLs in shipped surfaces: {findings}")


if __name__ == "__main__":
    unittest.main()
