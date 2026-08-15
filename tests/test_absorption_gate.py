"""B3-5: license/provenance gate for external-repo interaction.

GAP-4 (lessons sweep 2026-08-15), generalised by the same day's operator
refinement: before absorbing a pattern, algorithm, or prose doctrine read
from an external repository, the source's license/redistribution terms are
checked first - separately from, and prior to, whether the absorption stays
clean-room. Detection is generic: any external-repo interaction, not only
"distill the idea". The gate itself is requirement-driven - nothing fires as
a hard gate until the operator's own policy declares it; undeclared, it stays
advisory and never blocks.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    LICENSE_CLASSIFICATIONS,
    POLICY_FILENAME,
    classify_action,
    detect_external_repo,
    license_verdict,
    record_license_attestation,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _declare_gate(project: Path) -> None:
    (project / POLICY_FILENAME).write_text(
        json.dumps({"external_absorption_gate": True}), encoding="utf-8"
    )


class DetectionTests(unittest.TestCase):
    """Generic on purpose: a URL, a clone, a curl, or an explicit flag are
    all one condition, not four."""

    def test_a_github_clone_is_detected(self) -> None:
        self.assertEqual(
            detect_external_repo("git clone https://github.com/octocat/hello-world"),
            "github.com/octocat/hello-world",
        )

    def test_a_curl_to_a_repo_host_is_detected(self) -> None:
        self.assertIsNotNone(
            detect_external_repo("curl -sL https://gitlab.com/foo/bar/-/archive.tar.gz")
        )

    def test_an_explicit_source_repo_flag_is_detected(self) -> None:
        self.assertEqual(
            detect_external_repo("some-skill --source-repo https://example.com/x"),
            "https://example.com/x",
        )

    def test_ordinary_work_names_no_repository(self) -> None:
        self.assertIsNone(detect_external_repo("ls -la"))
        self.assertIsNone(detect_external_repo("git status"))

    def test_detection_is_additive_and_never_changes_protected_or_category(self) -> None:
        """A regression here would silently loosen an existing gate, which
        is worse than adding no gate at all."""
        before = classify_action("git status")
        self.assertIsNone(before["external_repo_ref"])
        self.assertFalse(before["protected"])

        cloned = classify_action("git clone https://github.com/octocat/hello-world")
        self.assertEqual(cloned["external_repo_ref"], "github.com/octocat/hello-world")
        # Still fails closed as a mutation - this field only adds information,
        # it does not stand in for the existing capability gate.
        self.assertTrue(cloned["protected"])
        self.assertEqual(cloned["category"], "unclassified-mutation")


class AttestationTests(unittest.TestCase):
    def test_an_unknown_classification_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError):
                record_license_attestation(archive, "github.com/x/y", "public-domain-ish")

    def test_every_declared_classification_is_accepted(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for classification in LICENSE_CLASSIFICATIONS:
                note = "" if classification == "permissive" else "read the concept, wrote our own code"
                record_license_attestation(archive, "github.com/x/y", classification, note)

    def test_non_permissive_without_a_clean_room_note_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError):
                record_license_attestation(archive, "github.com/x/y", "unlicensed")

    def test_permissive_needs_no_clean_room_note(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            record_license_attestation(archive, "github.com/x/y", "permissive")


class VerdictTests(unittest.TestCase):
    def test_an_operation_naming_no_repository_is_not_applicable(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            verdict = license_verdict(archive, project, "ls -la")
        self.assertFalse(verdict["applicable"])
        self.assertTrue(verdict["allowed"])

    def test_undeclared_is_advisory_and_never_blocks(self) -> None:
        """Red-first is about the declared mode; undeclared must never turn
        red, or an operator who declared nothing gets a gate anyway."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertTrue(verdict["applicable"])
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["gate"], "advisory")

    def test_undeclared_still_records_what_a_check_would_have_covered(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            license_verdict(archive, project, "git clone https://github.com/octocat/hello-world")
            records = archive.select(kind="action", limit=50)
        subjects = [r["subject"] for r in records]
        self.assertTrue(any(s.startswith("license-check-advisory:") for s in subjects), subjects)

    def test_declared_and_unattested_is_red(self) -> None:
        """Red-first: the very first call with a declared policy and no
        attestation must block, or the gate never proved it could refuse."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _declare_gate(project)
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertTrue(verdict["applicable"])
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["gate"], "declared")
        self.assertIn("license attest", verdict["remedy"])

    def test_declared_and_attested_permissive_is_green(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _declare_gate(project)
            record_license_attestation(archive, "github.com/octocat/hello-world", "permissive")
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertTrue(verdict["allowed"])
        self.assertEqual(verdict["classification"], "permissive")

    def test_declared_non_permissive_with_a_clean_room_note_is_green(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _declare_gate(project)
            record_license_attestation(
                archive, "github.com/octocat/hello-world", "copyleft-incompatible",
                clean_room_note="read the algorithm, wrote our own implementation",
            )
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertTrue(verdict["allowed"])

    def test_the_verdict_checks_the_note_independently_of_the_writer(self) -> None:
        """The classification alone is not enough for anything but
        permissive. `record_license_attestation` already refuses to write a
        non-permissive attestation without a note, so this exercises the
        read side's own defence directly, in case a record ever arrives by
        another route."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _declare_gate(project)
            archive.append(
                "action", "license-check:github.com/octocat/hello-world",
                {"repo_ref": "github.com/octocat/hello-world",
                 "classification": "unlicensed", "clean_room_note": ""},
                evidence=[],
            )
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertFalse(verdict["allowed"])
        self.assertIn("clean-room", verdict["detail"])

    def test_a_later_attestation_supersedes_an_earlier_one(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _declare_gate(project)
            record_license_attestation(
                archive, "github.com/octocat/hello-world", "unlicensed", "first pass note"
            )
            record_license_attestation(archive, "github.com/octocat/hello-world", "permissive")
            verdict = license_verdict(
                archive, project, "git clone https://github.com/octocat/hello-world"
            )
        self.assertEqual(verdict["classification"], "permissive")


class CLITests(unittest.TestCase):
    """The command surface the remedy message actually names."""

    def test_the_console_exposes_license_attest_and_check(self) -> None:
        from godmode_runtime.godmode_console import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "license", "attest", "--repo", "github.com/x/y",
            "--classification", "permissive",
        ])
        self.assertEqual(args.repo, "github.com/x/y")
        checked = parser.parse_args(["license", "check", "--operation", "git clone x"])
        self.assertEqual(checked.operation, "git clone x")


if __name__ == "__main__":
    unittest.main()
