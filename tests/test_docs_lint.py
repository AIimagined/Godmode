"""Public prose gets the same scrutiny as a claim.

The seed case is real: a README section justified the licence choice against an
alternative nobody had questioned. That is internal deliberation on a public
surface - it belongs in a decision record, where it is asked and answered once.
The linter exists so the next one is caught by a gate rather than by a reader.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_docslint import CHECKS, lint_docs, lint_text  # noqa: E402


class RationaleLeakTests(unittest.TestCase):
    def test_the_licence_justification_that_prompted_this_check_is_caught(self) -> None:
        findings = lint_text(
            "README.md",
            "Apache License 2.0 - chosen over MIT for its explicit patent grant, "
            "patent-retaliation clause, and trademark reservation.")
        self.assertTrue(findings)
        self.assertEqual(findings[0]["check"], "rationale-leak")
        self.assertIn("decision record", findings[0]["remedy"])

    def test_other_comparative_justifications_are_caught(self) -> None:
        for line in (
            "We picked Postgres over MySQL because replication is simpler.",
            "SQLite was chosen instead of a server database for portability.",
            "We use pytest rather than unittest because fixtures compose.",
        ):
            self.assertTrue(lint_text("README.md", line), line)

    def test_stating_the_choice_without_defending_it_passes(self) -> None:
        for line in (
            "Licensed under the Apache License 2.0.",
            "The runtime uses only the Python standard library.",
            "State lives below Git metadata or the OS application-data directory.",
        ):
            self.assertEqual(lint_text("README.md", line), [], line)


class UnverifiableClaimTests(unittest.TestCase):
    def test_superlatives_without_evidence_are_flagged(self) -> None:
        findings = lint_text("README.md", "Godmode is the most secure agent runtime available.")
        self.assertEqual(findings[0]["check"], "unverifiable-claim")

    def test_a_measured_number_is_not_a_superlative(self) -> None:
        self.assertEqual(
            lint_text("README.md", "Context bounded to 1,184 of 12,171 est. tokens (90%)."), [])

    def test_the_counterfactual_overclaim_is_flagged(self) -> None:
        findings = lint_text("README.md", "Godmode prevented 12 production incidents.")
        self.assertEqual(findings[0]["check"], "counterfactual-claim")

    def test_a_negated_counterfactual_is_the_disclaimer_not_the_claim(self) -> None:
        for line in (
            "It reports activity and never averted disaster.",
            "Refusals recorded, not disasters averted.",
            "This counts refusals rather than prevented incidents.",
        ):
            self.assertEqual(lint_text("README.md", line), [], line)


class InternalLeakTests(unittest.TestCase):
    def test_internal_deliberation_markers_are_flagged(self) -> None:
        for line in ("As we discussed, this ships next sprint.",
                     "TODO: rewrite this section before release.",
                     "FIXME the wording here"):
            findings = lint_text("README.md", line)
            self.assertTrue(findings, line)
            self.assertIn(findings[0]["check"], {"internal-leak", "unfinished-marker"})

    def test_a_local_path_is_flagged(self) -> None:
        findings = lint_text("README.md", r"Run it from C:\Users\someone\Documents\project.")
        self.assertEqual(findings[0]["check"], "local-path")


class GitIgnoredScopeTests(unittest.TestCase):
    """Scratch orchestration docs under a gitignored directory are working
    material, same as anything under `_PRIVATE_PARTS` - the .gitignore already
    says so; the linter should not need a second, hand-maintained list."""

    def _project_with_ignored_and_tracked_docs(self, tmp_path: Path) -> Path:
        project = tmp_path
        subprocess.run(["git", "init", "-q", str(project)],
                        check=True, capture_output=True, timeout=30)
        (project / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        scratch = project / "scratch"
        scratch.mkdir()
        (scratch / "notes.md").write_text(
            "Chosen over MIT because of patents.\n", encoding="utf-8")
        (project / "README.md").write_text(
            "Chosen over MIT because of patents.\n", encoding="utf-8")
        return project

    def test_a_gitignored_document_produces_zero_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = self._project_with_ignored_and_tracked_docs(Path(raw))
            report = lint_docs(project)
            paths = {f["path"] for f in report["findings"]}
            self.assertNotIn("scratch/notes.md", paths)

    def test_the_same_finding_outside_the_ignored_directory_still_fires(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = self._project_with_ignored_and_tracked_docs(Path(raw))
            report = lint_docs(project)
            paths = {f["path"] for f in report["findings"]}
            self.assertIn("README.md", paths)


class ScopeTests(unittest.TestCase):
    def test_only_public_documents_are_linted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "README.md").write_text(
                "Chosen over MIT because of patents.\n", encoding="utf-8")
            notes = project / ".godmode-private"
            notes.mkdir()
            (notes / "notes.md").write_text(
                "Chosen over MIT because of patents.\n", encoding="utf-8")
            report = lint_docs(project)
            paths = {f["path"] for f in report["findings"]}
            self.assertIn("README.md", paths)
            self.assertFalse(any(".godmode-private" in p for p in paths))

    def test_a_project_can_declare_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "README.md").write_text(
                "Godmode is the most secure runtime available.\n", encoding="utf-8")
            self.assertTrue(lint_docs(project)["findings"])
            (project / ".godmode-docslint.json").write_text(
                json.dumps({"ignore_checks": ["unverifiable-claim"]}), encoding="utf-8")
            self.assertEqual(lint_docs(project)["findings"], [])

    def test_every_check_declares_a_remedy(self) -> None:
        for name, check in CHECKS.items():
            self.assertTrue(check["remedy"], name)
            self.assertTrue(check["why"], name)


class ThisRepositoryTests(unittest.TestCase):
    def test_the_shipped_documents_pass_their_own_linter(self) -> None:
        report = lint_docs(PLUGIN_ROOT)
        self.assertEqual(report["findings"], [], report["findings"][:5])


# U-S4 - the charter prose linter rides in `lint_docs`'s report without
# joining its blocking findings. Full coverage (all three checks, red and
# green) lives in tests/test_prose_lint.py; this is the seam between the two
# modules, kept here since it is `lint_docs`'s own contract being extended.
class ProseAdvisoriesSeamTests(unittest.TestCase):
    def test_the_report_carries_a_prose_advisories_key(self) -> None:
        report = lint_docs(PLUGIN_ROOT)
        self.assertIn("prose_advisories", report)

    def test_prose_advisories_cannot_change_the_verdict_or_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            report = lint_docs(project)
        self.assertTrue(report["prose_advisories"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "clean")


if __name__ == "__main__":
    unittest.main()
