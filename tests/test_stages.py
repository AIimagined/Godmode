from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session, record_claim  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_stages import (  # noqa: E402
    SOP_STEPS,
    STAGES,
    advance,
    skip_stage,
    sop_attest,
    sop_status,
    stage_gate,
)


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, state, anchor, archive


class StageMachineShapeTests(unittest.TestCase):
    def test_stage_order_is_the_section_12_lifecycle(self) -> None:
        self.assertEqual(
            STAGES,
            ("discover", "preflight", "parity", "plan", "change",
             "verify", "document", "report", "checkpoint"),
        )

    def test_unknown_stage_is_refused_not_guessed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            with self.assertRaises(ArchiveError):
                stage_gate(archive, project, "deploy")


class StageGateTests(unittest.TestCase):
    def test_change_is_blocked_before_plan_approval(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            verdict = stage_gate(archive, project, "change")
            self.assertFalse(verdict["allowed"])
            missing_stages = {entry["stage"] for entry in verdict["missing"]}
            self.assertIn("plan", missing_stages)
            self.assertIn("change", missing_stages)
            # discover asks for nothing, so an empty archive still satisfies it.
            satisfied_stages = {entry["stage"] for entry in verdict["satisfied"]}
            self.assertIn("discover", satisfied_stages)

    def test_skip_with_reason_unblocks_parity(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.append("inventory", "baseline", {"files": 3}, evidence=[])
            blocked = stage_gate(archive, project, "parity")
            self.assertFalse(blocked["allowed"])

            skip_stage(archive, "S-test", "parity",
                       reason="single implementation; no sibling surface to compare")
            verdict = stage_gate(archive, project, "parity")
            self.assertTrue(verdict["allowed"], verdict)
            parity = [e for e in verdict["satisfied"] if e["stage"] == "parity"]
            self.assertTrue(parity and parity[0]["via"].startswith("skip"), verdict)

    def test_a_reasonless_skip_does_not_count(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.append("inventory", "baseline", {"files": 3}, evidence=[])
            # Written around the helper on purpose: the gate itself must enforce
            # the reason, not merely the convenience wrapper.
            archive.append("decision", "stage-skip:parity",
                           {"session": "S-test", "reason": ""}, evidence=[])
            verdict = stage_gate(archive, project, "parity")
            self.assertFalse(verdict["allowed"], verdict)
            parity = [e for e in verdict["missing"] if e["stage"] == "parity"]
            self.assertIn("reason", parity[0]["detail"])
            with self.assertRaises(ArchiveError):
                skip_stage(archive, "S-test", "parity", reason="   ")

    def test_a_parity_decision_satisfies_parity_without_a_skip(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.append("inventory", "baseline", {"files": 3}, evidence=[])
            archive.append("decision", "parity: rotate path matches access-token path",
                           {"session": "S-test"}, evidence=[])
            verdict = stage_gate(archive, project, "parity")
            self.assertTrue(verdict["allowed"], verdict)

    def test_report_tolerates_a_non_git_project_as_needs_input(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            verdict = stage_gate(archive, project, "report")
            report = [e for e in verdict["missing"] if e["stage"] == "report"]
            self.assertTrue(report, verdict)
            self.assertIn("needs-input", report[0]["detail"])


class AdvanceTests(unittest.TestCase):
    def test_advance_records_a_stage_attestation_when_the_gate_passes(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            session = open_session(archive, "stage-test")
            archive.append("inventory", "baseline", {"files": 3}, evidence=[])
            outcome = advance(archive, project, "preflight", session)
            self.assertTrue(outcome["recorded"], outcome)
            subjects = [r["subject"] for r in archive.select(kind="attestation", limit=50)]
            self.assertIn("stage:preflight", subjects)

    def test_advance_refuses_a_blocked_stage(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            session = open_session(archive, "stage-test")
            with self.assertRaises(ArchiveError):
                advance(archive, project, "change", session)
            subjects = [r["subject"] for r in archive.select(kind="attestation", limit=50)]
            self.assertNotIn("stage:change", subjects)


class SopTests(unittest.TestCase):
    def test_sop_steps_are_the_fifteen_from_t0_to_t14(self) -> None:
        self.assertEqual(len(SOP_STEPS), 15)
        self.assertEqual([step["id"] for step in SOP_STEPS],
                         [f"T{n}" for n in range(15)])
        for step in SOP_STEPS:
            self.assertTrue(step["text"])
            self.assertTrue(step["evidence_kind"])
        stale = next(step for step in SOP_STEPS if step["id"] == "T2")
        self.assertEqual(stale["evidence_kind"], "command")
        self.assertEqual(stale["binding"], "godmode_mistakes.stale_runtime")

    def test_empty_session_reports_next_step_t0(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            session = open_session(archive, "sop-test")
            status = sop_status(archive, session)
            self.assertEqual(status["next"], "T0")
            self.assertEqual(len(status["missing"]), 15)
            self.assertFalse(status["premature_rca"])

    def test_sop_attest_advances_the_next_step(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            session = open_session(archive, "sop-test")
            sop_attest(archive, session, "T0",
                       result="TypeError: 'NoneType' object is not iterable")
            status = sop_status(archive, session)
            self.assertEqual(status["next"], "T1")
            self.assertNotIn("T0", status["missing"])
            with self.assertRaises(ArchiveError):
                sop_attest(archive, session, "T99", result="no such step")

    def test_rca_claim_without_t1_is_premature(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            session = open_session(archive, "sop-test")
            record_claim(archive, project, session,
                         "The root cause is a stale worker process.", "hypothesis")
            status = sop_status(archive, session)
            self.assertTrue(status["premature_rca"], status)
            self.assertIn("T1", status["premature_rca_missing"])

            for step in ("T1", "T2", "T12"):
                sop_attest(archive, session, step, result="observed")
            settled = sop_status(archive, session)
            self.assertFalse(settled["premature_rca"], settled)


if __name__ == "__main__":
    unittest.main()
