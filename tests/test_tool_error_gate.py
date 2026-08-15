"""PARTIAL-P3/B3-7: an external tool's own declared error severity, observed
in a checker's own captured output, gates 'confirmed' the same way godmode's
own HARD rules already gate a step with no attestation.

L-173's exact shape: the engine's own linter had already logged
`media_missing_id` at `[error]` severity - "this will render silently
broken" - and the pipeline logged it and shipped anyway, because nothing
read the linter's OWN output, only its exit code. `record_verdict` now
tests every checker's own stdout+stderr against whatever error patterns
`register_error_pattern` has declared for the tool that checker invokes;
undeclared tools cost nothing at all.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_attest import declared_error_patterns, register_error_pattern  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_verdict import TOOL_ERROR_ACK, record_verdict  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _write_noisy_pytest_stub(project: Path, message: str, exit_code: int = 0) -> str:
    """A checker whose OWN command text names 'pytest' as a whole token
    (fix-round-1/I2: word-boundary matching, not substring - the filename is
    `pytest.py`, not `pytest_check.py`, so "pytest" is not glued to other
    identifier characters by an underscore) and whose OWN output carries
    `message`, but which still exits `exit_code` regardless - the exact
    L-173 shape: the tool's severity lives in what it printed, not in
    whether the harness called that a failure."""
    path = project / "pytest.py"
    path.write_text(
        f"import sys\nprint({message!r})\nsys.exit({exit_code})\n", encoding="utf-8",
    )
    return f"{sys.executable} pytest.py"


class DeclarationTests(unittest.TestCase):
    def test_undeclared_registry_is_empty(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(declared_error_patterns(archive), {})

    def test_register_then_read_back(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            self.assertEqual(
                declared_error_patterns(archive), {"pytest": r"(?i)\berror\b"}
            )

    def test_invalid_pattern_is_refused_at_registration(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                register_error_pattern(archive, "S-test", "pytest", "(unbalanced")

    def test_catastrophic_backtracking_shape_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                register_error_pattern(archive, "S-test", "pytest", r"(a+)+b")


class ToolErrorGateTests(unittest.TestCase):
    """Red-first, per the task contract."""

    def test_undeclared_tool_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            # No register_error_pattern call at all - the whole point.
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertEqual(record["data"]["tool_error_findings"], [])

    def test_declared_pattern_matched_confirmed_without_ack_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                )

    def test_declared_pattern_matched_confirmed_with_remediated_ack_passes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                tool_error_ack="acknowledged-remediated",
            )
        data = record["data"]
        self.assertEqual(data["disposition"], "confirmed")
        self.assertEqual(len(data["tool_error_findings"]), 1)
        self.assertEqual(data["tool_error_findings"][0]["tool"], "pytest")
        self.assertEqual(data["tool_error_ack"], "acknowledged-remediated")

    def test_declared_pattern_matched_confirmed_with_deferred_ack_passes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                tool_error_ack="acknowledged-deferred: known flaky asset, ticket-123",
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")

    def test_malformed_ack_is_refused_eagerly(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                    tool_error_ack="acknowledged",
                )

    def test_declared_pattern_that_never_matches_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\bfatal\b")
            checker = _write_noisy_pytest_stub(project, "all good, no issues")
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertEqual(record["data"]["tool_error_findings"], [])

    def test_declared_tool_not_named_in_this_checker_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            # Declared for a DIFFERENT tool than the one this checker names.
            register_error_pattern(archive, "S-test", "eslint", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertEqual(record["data"]["tool_error_findings"], [])

    def test_refuted_disposition_is_never_gated(self) -> None:
        # Only 'confirmed' claims the output was clean enough to trust - a
        # checker that already failed on its own exit code needs no ack.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id", exit_code=1)
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
            )
        self.assertEqual(record["data"]["disposition"], "refuted")
        self.assertEqual(len(record["data"]["tool_error_findings"]), 1)

    # Fix-round-1 (review M1): a "deferred" reason of pure whitespace must be
    # refused exactly like an empty one - the guarantee "a reason is
    # required" was not fully enforced.
    def test_whitespace_only_deferred_reason_is_refused_like_empty(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)\berror\b")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id")
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                    tool_error_ack="acknowledged-deferred:   ",
                )

    # Fix-round-1 (review M3): a matched excerpt that carries secret-shaped
    # content must never reach the archive verbatim - it is redacted before
    # `tool_error_findings` is ever written. The declared pattern here is
    # deliberately GREEDY (the exact shape the review flagged: not a narrow
    # `\berror\b` but something that captures the rest of the line), so the
    # match naturally sweeps up the planted token.
    def test_secret_shaped_excerpt_is_redacted_before_archiving(self) -> None:
        planted_token = "ghp_" + "abcdefghijklmnopqrstuvwx"  # github_pat shape, 24 chars
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)ERROR:.*")
            checker = _write_noisy_pytest_stub(
                project, f"ERROR: leaked {planted_token} during run",
            )
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                tool_error_ack="acknowledged-remediated",
            )
        findings = record["data"]["tool_error_findings"]
        self.assertEqual(len(findings), 1)
        excerpt = findings[0]["excerpt"]
        self.assertNotIn(planted_token, excerpt)
        self.assertEqual(excerpt, "[redacted: secret-shaped content]")

    def test_a_secret_free_match_is_archived_verbatim_not_over_redacted(self) -> None:
        # The redaction is real, not incidental - proves it does not fire on
        # every match, only ones that actually carry a secret shape.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "pytest", r"(?i)ERROR:.*")
            checker = _write_noisy_pytest_stub(project, "ERROR: media_missing_id, no secrets here")
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt", checker,
                tool_error_ack="acknowledged-remediated",
            )
        excerpt = record["data"]["tool_error_findings"][0]["excerpt"]
        self.assertEqual(excerpt, "ERROR: media_missing_id, no secrets here")


class ToolNameWordBoundaryTests(unittest.TestCase):
    """Fix-round-1 (review I2): the declared tool must match a whole TOKEN
    of the checker command, not merely a substring - the reviewer's own
    exact repro (declared `lint` matching `python unlinted_check.py`,
    confirmed live) is the first two assertions below."""

    def test_reviewers_exact_repro_substring_neighbor_is_not_gated(self) -> None:
        from godmode_runtime.godmode_verdict import _tool_named_in

        self.assertFalse(_tool_named_in("lint", "python unlinted_check.py"))

    def test_whole_token_forms_are_still_gated(self) -> None:
        from godmode_runtime.godmode_verdict import _tool_named_in

        self.assertTrue(_tool_named_in("lint", "lint --fix"))
        self.assertTrue(_tool_named_in("lint", "python -m lint"))

    def test_end_to_end_declared_lint_does_not_gate_an_unrelated_checker(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "lint", r"(?i)\berror\b")
            script = project / "unlinted_check.py"
            script.write_text(
                "import sys\nprint('ERROR: unrelated failure')\nsys.exit(0)\n",
                encoding="utf-8",
            )
            record = record_verdict(
                archive, project, "shipped clean", "ok", "file:witness.txt",
                f"{sys.executable} unlinted_check.py",
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertEqual(record["data"]["tool_error_findings"], [])

    def test_end_to_end_declared_lint_gates_a_real_lint_invocation(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("ok\n", encoding="utf-8")
            register_error_pattern(archive, "S-test", "lint", r"(?i)\berror\b")
            script = project / "lint.py"
            script.write_text(
                "import sys\nprint('ERROR: real lint failure')\nsys.exit(0)\n",
                encoding="utf-8",
            )
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "shipped clean", "ok", "file:witness.txt",
                    f"{sys.executable} lint.py",
                )


class RawAppendDefenseInDepthTests(unittest.TestCase):
    """godmode_invariants._verdict_invariants holds a raw archive.append to
    the same rule record_verdict enforces (mirrors U-V1's drive-vs-acquit
    and terminated-vs-truncated invariants, both defended the same way)."""

    def test_raw_confirmed_with_findings_and_no_ack_is_refused(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw",
                    {
                        "claim": "x", "claimed_value": "1",
                        "witness": {"kind": "file", "ref": "x"},
                        "checks": [{"checker": "pytest x", "exit": 0, "disposition": "confirmed"}],
                        "disposition": "confirmed", "run_state": "terminated",
                        "acquitted_by": "independent",
                        "tool_error_findings": [{"tool": "pytest", "excerpt": "ERROR: x"}],
                        "tool_error_ack": None,
                    },
                    evidence=[],
                )

    def test_raw_confirmed_with_findings_and_valid_ack_is_accepted(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            record = archive.append(
                "verdict", "raw",
                {
                    "claim": "x", "claimed_value": "1",
                    "witness": {"kind": "file", "ref": "x"},
                    "checks": [{"checker": "pytest x", "exit": 0, "disposition": "confirmed"}],
                    "disposition": "confirmed", "run_state": "terminated",
                    "acquitted_by": "independent",
                    "tool_error_findings": [{"tool": "pytest", "excerpt": "ERROR: x"}],
                    "tool_error_ack": "acknowledged-remediated",
                },
                evidence=[],
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")


class AckVocabularySyncTests(unittest.TestCase):
    """`godmode_invariants` stays dependency-free of `godmode_verdict` on
    purpose (see that module's docstring) and keeps its own copy of the ack
    pattern by hand - this asserts the two copies still agree, the same
    discipline `test_register.py` already applies to `_REGISTER_STATES`."""

    def test_the_archive_seam_ack_pattern_matches_this_module(self) -> None:
        from godmode_runtime import godmode_invariants

        self.assertEqual(godmode_invariants._TOOL_ERROR_ACK.pattern, TOOL_ERROR_ACK.pattern)

    def test_both_copies_accept_the_same_vocabulary(self) -> None:
        from godmode_runtime import godmode_invariants

        for ok in ("acknowledged-remediated", "acknowledged-deferred: known flaky"):
            self.assertTrue(TOOL_ERROR_ACK.match(ok))
            self.assertTrue(godmode_invariants._TOOL_ERROR_ACK.match(ok))
        for bad in ("", "acknowledged", "acknowledged-deferred", "remediated"):
            self.assertFalse(TOOL_ERROR_ACK.match(bad))
            self.assertFalse(godmode_invariants._TOOL_ERROR_ACK.match(bad))


if __name__ == "__main__":
    unittest.main()
