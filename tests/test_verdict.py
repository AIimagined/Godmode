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

import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


def _write_stub(project: Path, name: str, exit_code: int) -> str:
    """A tiny checker script that only ever exits with a fixed code -
    `ok.py`/`fail.py` from the case matrix. Never reads the witness; the
    panel fold under test is about disagreement between checkers'
    dispositions, not about what any one of them recomputes."""
    path = project / name
    path.write_text(f"import sys\nsys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {name}"


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

    def _raw_verdict_data(self, **overrides: object) -> dict:
        data = {
            "claim": "raw", "claimed_value": "v",
            "witness": {"kind": "file", "ref": "witness.txt"},
            "checker": "cmd:x", "disposition": "confirmed",
            "run_state": "terminated", "acquitted_by": "independent",
        }
        data.update(overrides)
        return data

    def test_archive_append_refuses_raw_self_confirmed(self) -> None:
        # The review's exact probe: a hand-built record that never goes
        # through record_verdict/_append_verdict must still be refused, at
        # the archive layer itself, not just by the helper function.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw self-confirmed",
                    self._raw_verdict_data(acquitted_by="self"),
                    evidence=[],
                )

    def test_archive_append_refuses_raw_truncated_confirmed(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw truncated-confirmed",
                    self._raw_verdict_data(run_state="truncated"),
                    evidence=[],
                )

    def test_archive_append_accepts_valid_raw_verdict(self) -> None:
        # Green control: the registry guards only the two forbidden
        # combinations, not the kind itself - a legitimate raw append still
        # lands.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = archive.append(
                "verdict", "raw refuted",
                self._raw_verdict_data(disposition="refuted"),
                evidence=[],
            )
        self.assertEqual(record["data"]["disposition"], "refuted")

    def test_fresh_interpreter_without_verdict_import_still_blocks_forbidden_combos(self) -> None:
        """The invariant guard must be innate to the archive core, not a side
        effect of some other module having been imported first.

        Mirrors the reviewer's exact probe: a FRESH Python process imports
        only godmode_chronicle and godmode_anchor - never godmode_verdict,
        never godmode_console (the only module that would pull
        godmode_verdict in transitively) - and still refuses both forbidden
        raw-append combinations. This is the test that fails if registration
        is ever made lazy again (e.g. reverting to a kind-owning module
        self-registering at its own import).
        """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            state = base / "private-state"
            project.mkdir()
            script = (
                "import sys\n"
                f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
                "assert 'godmode_runtime.godmode_verdict' not in sys.modules\n"
                "from godmode_runtime import godmode_chronicle\n"
                "from godmode_runtime.godmode_anchor import resolve_anchor\n"
                "from godmode_runtime.godmode_errors import ArchiveError\n"
                "assert 'godmode_runtime.godmode_verdict' not in sys.modules, "
                "'godmode_chronicle must not import godmode_verdict'\n"
                "assert godmode_chronicle.KIND_INVARIANTS.get('verdict') is not None, "
                "'KIND_INVARIANTS must be populated eagerly, before any other import'\n"
                f"anchor = resolve_anchor({str(project)!r})\n"
                "archive = godmode_chronicle.Chronicle(anchor)\n"
                "archive.initialize()\n"
                "base_data = {'claim': 'raw', 'claimed_value': 'v', "
                "'witness': {'kind': 'file', 'ref': 'witness.txt'}, "
                "'checker': 'cmd:x', 'disposition': 'confirmed', "
                "'run_state': 'terminated', 'acquitted_by': 'independent'}\n"
                "blocked = 0\n"
                "try:\n"
                "    archive.append('verdict', 'raw self-confirmed (no verdict import)', "
                "dict(base_data, acquitted_by='self'), evidence=[])\n"
                "except ArchiveError:\n"
                "    blocked += 1\n"
                "try:\n"
                "    archive.append('verdict', 'raw truncated-confirmed (no verdict import)', "
                "dict(base_data, run_state='truncated'), evidence=[])\n"
                "except ArchiveError:\n"
                "    blocked += 1\n"
                "print('BLOCKED:' + str(blocked))\n"
            )
            env = dict(os.environ)
            env["GODMODE_STATE_HOME"] = str(state)
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=30, env=env,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("BLOCKED:2", result.stdout)

    def test_empty_checker_cmd_is_malformed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt", "",
            )
        self.assertEqual(record["data"]["disposition"], "witness-malformed")
        self.assertTrue(any(e.startswith("reason:checker-empty")
                            for e in record["evidence"]))

    def test_unparseable_checker_cmd_is_malformed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt", "'unbalanced",
            )
        self.assertEqual(record["data"]["disposition"], "witness-malformed")
        self.assertTrue(any(e.startswith("reason:checker-unparseable")
                            for e in record["evidence"]))

    def test_quoted_checker_path_still_runs(self) -> None:
        # A checker command quoted to protect a space-containing interpreter
        # path must still run, not fall to malformed because the quote
        # marks rode along as literal characters in the token.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")
            _write_checker(project)
            record = record_verdict(
                archive, project, "sum improved", "42",
                "file:witness.txt",
                f'"{sys.executable}" check.py witness.txt 42',
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")

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


class PanelFold(unittest.TestCase):
    """U-E4: `record_verdict` accepts a REPEATED `--checker` (1..N); the
    panel folds to one disposition by a closed rule, never a score.
    `contested` joins the disposition enum for exactly the disagreement
    case; a `confirmed` fold can never carry a refuting check, checked both
    through the fold itself and through a direct raw append that bypasses
    it (the archive-seam invariant added to godmode_invariants.py)."""

    def _witness(self, project: Path) -> None:
        (project / "witness.txt").write_text("21\n21\n", encoding="utf-8")

    def test_all_confirm_confirmed(self) -> None:
        # [ok, ok] -> confirmed
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            ok1 = _write_stub(project, "ok1.py", 0)
            ok2 = _write_stub(project, "ok2.py", 0)
            record = record_verdict(
                archive, project, "panel agrees", "42", "file:witness.txt",
                [ok1, ok2],
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        checks = record["data"]["checks"]
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c["disposition"] == "confirmed" for c in checks))

    def test_split_is_contested_and_uncitable(self) -> None:
        # [ok, fail] -> contested; verdict: citation fails
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            ok = _write_stub(project, "ok.py", 0)
            fail = _write_stub(project, "fail.py", 1)
            verdict = record_verdict(
                archive, project, "panel disagrees", "42", "file:witness.txt",
                [ok, fail],
            )
            self.assertEqual(verdict["data"]["disposition"], "contested")
            claim = record_claim(
                archive, project, "session-1", "the panel-backed claim", "verified",
                cites=[f"verdict:{verdict['sequence']}"],
            )
        # `contested` resolves through the SAME rule that already refuses
        # refuted/witness-malformed - `_citation_resolves` only accepts
        # `disposition == "confirmed"` (godmode_attest.py, unmodified here).
        self.assertEqual(claim["data"]["grade"], "hypothesis")
        self.assertTrue(claim["data"]["downgraded"])

    def test_all_refute_refuted(self) -> None:
        # [fail, fail] -> refuted
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            fail1 = _write_stub(project, "fail1.py", 1)
            fail2 = _write_stub(project, "fail2.py", 1)
            record = record_verdict(
                archive, project, "panel refutes", "42", "file:witness.txt",
                [fail1, fail2],
            )
        self.assertEqual(record["data"]["disposition"], "refuted")
        self.assertTrue(all(c["disposition"] == "refuted" for c in record["data"]["checks"]))

    def test_malformed_minority_is_stated_gap(self) -> None:
        # [ok, crash] -> confirmed + gap recorded in checks
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            ok = _write_stub(project, "ok.py", 0)
            crash = str(project / "does-not-exist.py")  # missing path -> crash
            record = record_verdict(
                archive, project, "panel with a crash", "42", "file:witness.txt",
                [ok, crash],
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        checks = record["data"]["checks"]
        self.assertEqual(len(checks), 2)
        gaps = [c for c in checks if c["disposition"] == "witness-malformed"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("reason", gaps[0])
        judged = [c for c in checks if c["disposition"] == "confirmed"]
        self.assertEqual(len(judged), 1)

    def test_all_malformed_witness_malformed(self) -> None:
        # [crash, crash] -> witness-malformed
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            crash1 = str(project / "no-such-checker-1.py")
            crash2 = str(project / "no-such-checker-2.py")
            record = record_verdict(
                archive, project, "panel all crash", "42", "file:witness.txt",
                [crash1, crash2],
            )
        self.assertEqual(record["data"]["disposition"], "witness-malformed")
        self.assertEqual(len(record["data"]["checks"]), 2)
        self.assertTrue(
            all(c["disposition"] == "witness-malformed" for c in record["data"]["checks"])
        )

    def test_single_checker_string_still_a_one_element_panel(self) -> None:
        # Backward compat: a bare `checker_cmd` string (every pre-panel
        # caller) still folds to a one-element panel, unchanged output.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._witness(project)
            _write_checker(project)
            record = record_verdict(
                archive, project, "sum improved", "42", "file:witness.txt",
                f"{sys.executable} check.py witness.txt 42",
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")
        self.assertEqual(len(record["data"]["checks"]), 1)
        self.assertIn("checker_exit:0", record["evidence"])

    def _raw_panel_data(self, **overrides: object) -> dict:
        data = {
            "claim": "raw panel", "claimed_value": "v",
            "witness": {"kind": "file", "ref": "witness.txt"},
            "checker": "cmd:panel", "disposition": "confirmed",
            "run_state": "terminated", "acquitted_by": "independent",
            "checks": [
                {"checker": "cmd:a", "exit": 0, "disposition": "confirmed"},
                {"checker": "cmd:b", "exit": 1, "disposition": "refuted"},
            ],
        }
        data.update(overrides)
        return data

    def test_append_invariant_confirmed_with_refuting_check_refused(self) -> None:
        # Plant: hand-build a record dict with disposition=confirmed but a
        # `checks` entry that came back refuted, and append it RAW (never
        # through record_verdict/_fold_panel, which could never produce this
        # combination itself) -> the archive seam refuses it outright.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "verdict", "raw confirmed with a refuting check",
                    self._raw_panel_data(),
                    evidence=[],
                )

    def test_append_invariant_allows_confirmed_when_no_check_refutes(self) -> None:
        # Green control: the new rule only fires on an actual refuting
        # check - a confirmed fold whose checks all agree still lands.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = archive.append(
                "verdict", "raw confirmed, panel agrees",
                self._raw_panel_data(checks=[
                    {"checker": "cmd:a", "exit": 0, "disposition": "confirmed"},
                    {"checker": "cmd:b", "exit": None, "disposition": "witness-malformed",
                     "reason": "checker-timeout"},
                ]),
                evidence=[],
            )
        self.assertEqual(record["data"]["disposition"], "confirmed")


if __name__ == "__main__":
    unittest.main()
