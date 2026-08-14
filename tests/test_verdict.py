"""U-V1: witness + independent-checker verdicts.

"Agent claims it fixed X" becomes admissible only as: a claimed value stated
explicitly, a data-only witness sufficient to recompute it, and a checker
that recomputes from the witness alone (never invoking the producer) and
asserts against the stated claim.

Three dispositions, never two: a witness that cannot be read, or a checker
that never ran to completion, means the claim was never judged
(witness-malformed) - a different fact from "judged and found false"
(refuted). The drive-vs-acquit invariant (a self-acquitted "confirmed" is
refused) and the terminated-vs-truncated invariant (a truncated run cannot
be "confirmed") are both enforced at the moment the record would be written,
not left to a later reader to notice.
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

from godmode_runtime.godmode_attest import record_claim  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_verdict import (  # noqa: E402
    attest_run_state,
    record_verdict,
    verdict_for,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _write_checker(project: Path) -> Path:
    checker = project / "check.py"
    checker.write_text(
        "import sys,pathlib\n"
        "total=sum(int(l) for l in pathlib.Path(sys.argv[1]).read_text().split())\n"
        "sys.exit(0 if total==int(sys.argv[2]) else 1)\n",
        encoding="utf-8",
    )
    return checker


class VerdictTests(unittest.TestCase):
    def test_confirmed_when_checker_recomputes_the_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt",
                f"{sys.executable} check.py witness.txt 42",
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertIn("checker_exit:0", record["evidence"])

    def test_refuted_when_witness_disagrees_with_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            record = record_verdict(
                archive, project, "sum improved", "43",
                "file:witness.txt",
                f"{sys.executable} check.py witness.txt 43",
            )
        self.assertEqual(record["data"]["disposition"], "refuted")

    def test_malformed_when_witness_missing(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_checker(project)
            # witness.txt is never created - the checker must never run.
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt",
                f"{sys.executable} check.py witness.txt 42",
            )
        self.assertEqual(record["data"]["disposition"], "witness-malformed")
        self.assertNotIn("checker_exit:0", record["evidence"])
        self.assertNotIn("checker_exit:1", record["evidence"])

    def test_malformed_when_checker_cannot_run(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt",
                "godmode-nonexistent-checker-binary witness.txt 42",
            )
        self.assertEqual(record["data"]["disposition"], "witness-malformed")

    def test_self_acquitted_quality_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "sum improved", "42",
                    "file:witness.txt",
                    f"{sys.executable} check.py witness.txt 42",
                    acquitted_by="self",
                )

    def test_truncated_never_confirmed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            with self.assertRaises(ArchiveError):
                record_verdict(
                    archive, project, "sum improved", "42",
                    "file:witness.txt",
                    f"{sys.executable} check.py witness.txt 42",
                    run_state="truncated",
                )

    def test_self_may_attest_execution_only(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = attest_run_state(archive, run_state="terminated", claim="ran to completion")
        self.assertIsNone(record["data"]["disposition"])
        self.assertEqual(record["data"]["acquitted_by"], "self")
        self.assertEqual(record["data"]["run_state"], "terminated")

    def test_claim_citing_confirmed_verdict_resolves(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            verdict = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt",
                f"{sys.executable} check.py witness.txt 42",
            )
            claim = record_claim(
                archive, project, "session-1", "the sum was fixed", "verified",
                cites=[f"verdict:{verdict['sequence']}"],
            )
        self.assertEqual(claim["data"]["grade"], "verified")
        self.assertFalse(claim["data"]["downgraded"])

    def test_claim_citing_refuted_verdict_downgrades(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            verdict = record_verdict(
                archive, project, "sum improved", "43",
                "file:witness.txt",
                f"{sys.executable} check.py witness.txt 43",
            )
            claim = record_claim(
                archive, project, "session-1", "the sum was fixed", "verified",
                cites=[f"verdict:{verdict['sequence']}"],
            )
        self.assertEqual(claim["data"]["grade"], "hypothesis")
        self.assertTrue(claim["data"]["downgraded"])

    def test_verdict_for_returns_none_when_absent(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(verdict_for(archive, 999))


if __name__ == "__main__":
    unittest.main()
