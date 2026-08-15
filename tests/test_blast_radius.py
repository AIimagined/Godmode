"""PARTIAL-P2/B3-4: blast-radius-scaled evidence bar on `record_claim`.

Godmode's register already requires SOME evidence citation for a non-open
disposition; this closes the narrower nuance the lessons sweep found (L-119,
L-180, L-290): an ops-directed claim, a sticky/persisting side effect, or a
checksum-class guard needs a STRONGER bar than an ordinary claim - N>=2
INDEPENDENT witnesses, not just N>=1 citation that happens to resolve.

Opt-in, v1: a claim that never sets `blast_radius` is graded exactly as it
was before this field existed - the third test below is the direct proof of
that, not an incidental side effect of the other two.
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

from godmode_runtime.godmode_attest import (  # noqa: E402
    BLAST_RADIUS_KINDS,
    _independent_witness_count,
    _witness_identity,
    record_claim,
    record_step,
)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class WitnessIdentityTests(unittest.TestCase):
    """Unit-level coverage of the independence predicate itself, isolated
    from the claim-grading pipeline it feeds."""

    def test_same_cmd_string_twice_is_one_witness(self) -> None:
        self.assertEqual(
            _independent_witness_count(["cmd:pytest -k foo", "cmd:pytest -k foo"]), 1
        )

    def test_two_different_cmd_strings_are_two_witnesses(self) -> None:
        self.assertEqual(
            _independent_witness_count(["cmd:pytest -k foo", "cmd:pytest -k bar"]), 2
        )

    def test_same_file_different_line_ranges_is_one_witness(self) -> None:
        self.assertEqual(
            _independent_witness_count(
                ["file:lib/pin.py#L10-L20", "file:lib/pin.py#L40"]
            ),
            1,
        )

    def test_two_different_files_are_two_witnesses(self) -> None:
        self.assertEqual(
            _independent_witness_count(["file:lib/a.py", "file:lib/b.py"]), 2
        )

    def test_different_kinds_are_independent_regardless_of_target(self) -> None:
        # A file: and a cmd: citation are never "the same witness" just
        # because both concern the same subject.
        self.assertEqual(_witness_identity("file:lib/a.py")[0], "file")
        self.assertEqual(_witness_identity("cmd:lib/a.py")[0], "cmd")
        self.assertEqual(
            _independent_witness_count(["file:lib/a.py", "cmd:lib/a.py"]), 2
        )

    # Fix-round-1 (review I1): a bare path comparison let cosmetic spelling
    # alone launder one read of one file into two "independent" witnesses.
    # The reviewer's own exact repro is the first assertion below.

    def test_reviewers_exact_repro_dot_slash_prefix_is_one_witness(self) -> None:
        self.assertEqual(_independent_witness_count(["file:x", "file:./x"]), 1)

    def test_dot_dot_traversal_back_to_the_same_file_is_one_witness(self) -> None:
        self.assertEqual(_independent_witness_count(["file:x", "file:a/../x"]), 1)
        self.assertEqual(_independent_witness_count(["file:x", "file:x/../x"]), 1)

    def test_windows_case_insensitive_spelling_is_one_witness(self) -> None:
        # Casefolded only on a case-insensitive host (os.name == "nt"); this
        # suite runs on Windows, where file:X and file:x name the same file
        # on disk and must collapse to one witness.
        import os

        self.assertEqual(os.name, "nt", "this probe assumes the Windows CI host")
        self.assertEqual(_independent_witness_count(["file:X", "file:x"]), 1)

    def test_normalization_does_not_collapse_genuinely_different_files(self) -> None:
        # The fix must not overcorrect into treating every file: pair as one
        # witness - two real, distinct files stay two witnesses.
        self.assertEqual(_independent_witness_count(["file:a.py", "file:b.py"]), 2)
        self.assertEqual(
            _independent_witness_count(["file:sub/a.py", "file:sub/b.py"]), 2
        )


class BlastRadiusValidationTests(unittest.TestCase):
    def test_unknown_blast_radius_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_claim(
                    archive, project, "S-test", "shipped the migration",
                    "observed", blast_radius="nonexistent-kind",
                )

    def test_every_documented_kind_is_accepted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for kind in BLAST_RADIUS_KINDS:
                record_claim(
                    archive, project, "S-test", f"a {kind} claim, unresolved on purpose",
                    "observed", blast_radius=kind,
                )


class BlastRadiusGradingTests(unittest.TestCase):
    """Red-first, per the task contract: two copies of one witness downgrades;
    two independent witnesses pass; no field at all is untouched."""

    def test_ops_directed_claim_with_two_copies_of_one_witness_is_downgraded(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = "S-test"
            # One attestation makes the cmd: citation resolve at all; citing
            # it twice in the claim is the "two copies of one witness" shape
            # under test, not a second, distinct command run.
            record_step(
                archive, session, "check:migration", "ran",
                evidence=["cmd:psql -c 'select 1'"],
            )
            record = record_claim(
                archive, project, session,
                "the migration ran against production",
                "verified",
                cites=["cmd:psql -c 'select 1'", "cmd:psql -c 'select 1'"],
                blast_radius="ops-directed",
            )
        data = record["data"]
        self.assertTrue(data["downgraded"])
        self.assertEqual(data["grade"], "hypothesis")
        self.assertIn("blast_radius", data["reason"])
        self.assertIn("independent witnesses", data["reason"])
        self.assertEqual(data["blast_radius"], "ops-directed")

    def test_ops_directed_claim_with_cmd_and_file_on_distinct_artifacts_passes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = "S-test"
            (project / "migration_state.txt").write_text("applied\n", encoding="utf-8")
            record_step(
                archive, session, "check:migration", "ran",
                evidence=["cmd:psql -c 'select 1'"],
            )
            record = record_claim(
                archive, project, session,
                "the migration ran against production",
                "verified",
                cites=["cmd:psql -c 'select 1'", "file:migration_state.txt"],
                blast_radius="ops-directed",
            )
        data = record["data"]
        self.assertFalse(data["downgraded"])
        self.assertEqual(data["grade"], "verified")
        self.assertEqual(data["blast_radius"], "ops-directed")

    def test_no_blast_radius_field_is_unaffected_by_duplicate_witnesses(self) -> None:
        # The exact citation shape that downgrades an ops-directed claim
        # above must NOT downgrade an ordinary one - blast_radius is opt-in.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = "S-test"
            record_step(
                archive, session, "check:migration", "ran",
                evidence=["cmd:psql -c 'select 1'"],
            )
            record = record_claim(
                archive, project, session,
                "the migration ran against production",
                "verified",
                cites=["cmd:psql -c 'select 1'", "cmd:psql -c 'select 1'"],
            )
        data = record["data"]
        self.assertFalse(data["downgraded"])
        self.assertEqual(data["grade"], "verified")
        self.assertIsNone(data["blast_radius"])

    def test_checksum_guard_needs_more_than_the_same_file_twice(self) -> None:
        # L-290's own shape: a pin/hash guard cited by re-reading the same
        # file location twice is not two witnesses touching the bytes.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = "S-test"
            (project / "lock.sha256").write_text("deadbeef\n", encoding="utf-8")
            record = record_claim(
                archive, project, session,
                "the checksum guard matches the pinned artifact",
                "verified",
                cites=["file:lock.sha256#L1", "file:lock.sha256"],
                blast_radius="checksum-guard",
            )
        data = record["data"]
        self.assertTrue(data["downgraded"])
        self.assertIn("blast_radius", data["reason"])


if __name__ == "__main__":
    unittest.main()
