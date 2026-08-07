"""A linter that only finds faults can only ever flatter.

Every check the document linter shipped with was negative — rationale leaks,
unverifiable claims, counterfactuals, internal notes, unfinished markers, local
paths. All six ask whether a document contains something it should not. None
asked whether it contains something it must, so a release note that silently
omitted its verification section was reported `clean`.

That is the most flattering possible failure mode: a one-sided linter's every
false negative makes the output look better than it is, which is the wrong
direction for a tool whose job is to stop overclaiming.

An artifact contract closes the other half. It declares the sections a document
must carry, and both halves are checked: present, and not empty. A heading with
nothing under it satisfies a word-search and satisfies nobody reading it.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_docslint import lint_docs  # noqa: E402


CONTRACT = {"contracts": {"RELEASE_NOTES_*.md": ["Verifying", "Upgrading"]}}


def _project(contract: dict | None = None, **files: str):
    holder = tempfile.TemporaryDirectory(prefix="godmode-contract-")
    root = Path(holder.name)
    if contract is not None:
        (root / ".godmode-docslint.json").write_text(
            json.dumps(contract), encoding="utf-8")
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return holder


def _codes(report: dict) -> list[str]:
    return [finding["check"] for finding in report["findings"]]


class MissingSectionTests(unittest.TestCase):
    def test_a_required_section_that_is_absent_is_reported(self) -> None:
        with _project(CONTRACT, **{
            "RELEASE_NOTES_v1.md": "# v1\n\n## Upgrading\n\nRun the installer.\n"
        }) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("missing-section", _codes(report))
        self.assertTrue(any("Verifying" in f["why"] for f in report["findings"]))

    def test_a_complete_document_is_clean(self) -> None:
        with _project(CONTRACT, **{
            "RELEASE_NOTES_v1.md":
                "# v1\n\n## Verifying\n\nRun the suite.\n\n## Upgrading\n\nInstall it.\n"
        }) as raw:
            report = lint_docs(Path(raw))
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "clean")

    def test_a_missing_section_fails_the_command(self) -> None:
        """An obligation not met is not a stylistic note."""
        with _project(CONTRACT, **{"RELEASE_NOTES_v1.md": "# v1\n\nnothing.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertGreaterEqual(report["high_severity"], 1)

    def test_documents_outside_the_contract_are_untouched(self) -> None:
        with _project(CONTRACT, **{"README.md": "# hello\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("missing-section", _codes(report))


class EmptySectionTests(unittest.TestCase):
    """Present is not complete: the half that a word-search would miss."""

    def test_a_heading_with_nothing_under_it_is_reported(self) -> None:
        with _project(CONTRACT, **{
            "RELEASE_NOTES_v1.md":
                "# v1\n\n## Verifying\n\n## Upgrading\n\nInstall it.\n"
        }) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("empty-section", _codes(report))
        self.assertTrue(any("Verifying" in f["why"]
                            for f in report["findings"] if f["check"] == "empty-section"))

    def test_a_heading_followed_only_by_blank_lines_is_empty(self) -> None:
        with _project(CONTRACT, **{
            "RELEASE_NOTES_v1.md":
                "# v1\n\n## Verifying\n\n\n\n## Upgrading\n\nInstall it.\n"
        }) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("empty-section", _codes(report))

    def test_the_last_section_in_a_file_is_checked_too(self) -> None:
        """A trailing heading has no following heading to bound it, which is
        exactly where an off-by-one would hide the finding."""
        with _project(CONTRACT, **{
            "RELEASE_NOTES_v1.md": "# v1\n\n## Upgrading\n\nInstall it.\n\n## Verifying\n"
        }) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("empty-section", _codes(report))


class ContractConfigurationTests(unittest.TestCase):
    def test_no_contract_declared_means_no_positive_checks(self) -> None:
        """The negative checks must keep working for projects that declare
        nothing, so the new half cannot become a reason to skip the linter."""
        with _project(None, **{"README.md": "# hi\n\nThis is the most secure tool.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertNotIn("missing-section", _codes(report))
        self.assertIn("unverifiable-claim", _codes(report))

    def test_a_contract_matches_by_path_not_only_by_name(self) -> None:
        with _project({"contracts": {"docs/**/*.md": ["Scope"]}}, **{
            "docs/guides/setup.md": "# setup\n\nno scope heading here.\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("missing-section", _codes(report))

    def test_a_malformed_contract_is_reported_not_ignored(self) -> None:
        """Silently dropping an unreadable contract would mean an operator who
        mistyped it believes their documents are under a check that never ran."""
        with _project({"contracts": {"README.md": "Scope"}}, **{
            "README.md": "# hi\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("malformed-contract", _codes(report))

    def test_the_report_states_which_contracts_were_applied(self) -> None:
        with _project(CONTRACT, **{"RELEASE_NOTES_v1.md": "# v1\n"}) as raw:
            report = lint_docs(Path(raw))
        self.assertIn("contracts_applied", report)
        self.assertEqual(report["contracts_applied"], ["RELEASE_NOTES_*.md"])


if __name__ == "__main__":
    unittest.main()
