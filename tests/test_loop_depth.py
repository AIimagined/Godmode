"""Depth tests for the anti-loop layer.

These exist because the loop detectors are the control of last resort: by the
time they fire, the agent has already failed to notice its own repetition, so a
wrong rollback target or an unreadable verdict is not a cosmetic bug - it sends
the operator back into the loop. Each class pins one behaviour: rollback must
name a STABLE checkpoint (S15.3), the stop notice must be readable without the
findings JSON, the repetition threshold must be a project decision, and blaming
the model must be reachable via transport-captured evidence.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402


@contextmanager
def isolated_archive():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, archive


def _oscillate(archive: Chronicle) -> None:
    for subject in ("use sync io", "use async io", "use sync io"):
        archive.append("change", subject, {"files": ["io.py"]})


class OscillationRollbackTests(unittest.TestCase):
    """S15.3: only a checkpoint recorded stable is a safe rollback target."""

    def test_rollback_cites_the_green_checkpoint_not_the_later_red_one(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            archive.append("checkpoint", "stable", {"status": "green"})  # seq 1
            archive.append("checkpoint", "broken", {"status": "red"})  # seq 2
            _oscillate(archive)
            hits = [f for f in analyze(archive)["findings"] if f["detector"] == "oscillation"]
            self.assertTrue(hits)
            self.assertIn("seq:1", hits[0]["detail"])
            self.assertNotIn("seq:2", hits[0]["detail"])

    def test_verified_checkpoint_also_qualifies_as_stable(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            archive.append("checkpoint", "shipped", {"status": "verified"})  # seq 1
            archive.append("checkpoint", "broken", {"status": "red"})  # seq 2
            _oscillate(archive)
            hits = [f for f in analyze(archive)["findings"] if f["detector"] == "oscillation"]
            self.assertTrue(hits)
            self.assertIn("seq:1", hits[0]["detail"])

    def test_only_unstable_checkpoints_means_no_rollback_target(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            archive.append("checkpoint", "broken", {"status": "red"})  # seq 1
            _oscillate(archive)
            hits = [f for f in analyze(archive)["findings"] if f["detector"] == "oscillation"]
            self.assertTrue(hits)
            self.assertNotIn("roll back to checkpoint", hits[0]["detail"])
            self.assertIn("record one before continuing", hits[0]["detail"])


class LoopNoticeTests(unittest.TestCase):
    """A blocking verdict must also arrive as four plain sentences, because the
    reader who most needs it will not parse the findings JSON."""

    def test_notice_renders_four_parts_from_the_top_blocking_finding(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            archive.append("change", "retry the fix", {"files": ["a.py"]})
            archive.append("change", "retry the fix", {"files": ["a.py"]})
            report = analyze(archive)
            self.assertTrue(report["blocking"])
            notice = report["notice"]
            self.assertIsInstance(notice, str)
            for marker in ("What repeated:", "What this means:", "Next safe step:"):
                self.assertIn(marker, notice)
            self.assertIn("further mutation until the evidence changes", notice.lower())
            top = [f for f in report["findings"] if f["blocking"]][0]
            self.assertIn(top["detail"], notice)

    def test_notice_is_none_when_nothing_blocks(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            archive.append("change", "one honest attempt", {"files": ["a.py"]})
            report = analyze(archive)
            self.assertFalse(report["blocking"])
            self.assertIsNone(report["notice"])


class ThresholdConfigTests(unittest.TestCase):
    """The repetition threshold is a project decision, bounded so it cannot
    silently disable the detector."""

    def test_configured_threshold_is_honored_by_analyze(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (project, archive):
            (project / ".godmode-loop.json").write_text(
                json.dumps({"repeat_threshold": 5}), encoding="utf-8")
            for _ in range(4):
                archive.append("action", "run the suite", {"command": "unittest"})
            below = analyze(archive)
            self.assertFalse(
                [f for f in below["findings"] if f["detector"] == "repeated-action"])
            archive.append("action", "run the suite", {"command": "unittest"})
            at = analyze(archive)
            self.assertTrue(
                [f for f in at["findings"] if f["detector"] == "repeated-action"])

    def test_threshold_defaults_and_clamps(self) -> None:
        from godmode_runtime.godmode_loop import repeat_threshold

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            config = project / ".godmode-loop.json"
            self.assertEqual(repeat_threshold(project), 3)
            config.write_text('{"repeat_threshold": 4}', encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 4)
            config.write_text('{"repeat_threshold": 100}', encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 10)
            config.write_text('{"repeat_threshold": 1}', encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 2)
            # Malformed declarations fall back rather than crash or disable.
            config.write_text("not json", encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 3)
            config.write_text('{"repeat_threshold": true}', encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 3)
            config.write_text('{"repeat_threshold": "5"}', encoding="utf-8")
            self.assertEqual(repeat_threshold(project), 3)
        self.assertEqual(repeat_threshold(None), 3)


class ModelBlameTransportRouteTests(unittest.TestCase):
    """Request/response captured at the transport layer is a non-model control:
    no model sits between the wire and the record."""

    def test_transport_evidence_attestation_permits_blame(self) -> None:
        from godmode_runtime.godmode_loop import model_blame_allowed

        with isolated_archive() as (_project, archive):
            self.assertFalse(model_blame_allowed(archive.read_events())["allowed"])
            archive.append("attestation", "transport-evidence:request-response-capture",
                           {"status": "ran", "session": "s"})
            verdict = model_blame_allowed(archive.read_events())
            self.assertTrue(verdict["allowed"])
            self.assertEqual(verdict["controls"], ["seq:1"])

    def test_transport_route_still_respects_the_session_filter(self) -> None:
        from godmode_runtime.godmode_loop import model_blame_allowed

        with isolated_archive() as (_project, archive):
            archive.append("attestation", "transport-evidence:proxy-capture",
                           {"status": "ran", "session": "other"})
            verdict = model_blame_allowed(archive.read_events(), session="mine")
            self.assertFalse(verdict["allowed"])


def _checkpoint(archive: Chronicle, status: str = "red") -> None:
    archive.append("checkpoint", "round", {"status": status})


class StallEscalationTests(unittest.TestCase):
    """U-R2: 0/2/4 consecutive no-progress rounds -> nominal/redirect/halt;
    an operator-sourced record clears the halt."""

    def test_zero_empty_rounds_is_nominal(self) -> None:
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            archive.append("change", "did something", {"files": ["a.py"]})
            _checkpoint(archive)
            self.assertEqual(stall_escalation(archive.read_events()), [])

    def test_two_consecutive_empty_rounds_is_a_blocking_redirect_finding(self) -> None:
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            _checkpoint(archive)
            _checkpoint(archive)
            findings = stall_escalation(archive.read_events())
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["detector"], "stall-redirect")
            self.assertTrue(findings[0]["blocking"])
            self.assertIn("record what you'll do differently", findings[0]["detail"])

    def test_four_consecutive_empty_rounds_is_a_governance_halt(self) -> None:
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            for _ in range(4):
                _checkpoint(archive)
            findings = stall_escalation(archive.read_events())
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["detector"], "stall-escalation")
            self.assertTrue(findings[0]["blocking"])
            self.assertIn("human escalation required", findings[0]["detail"])

    def test_operator_sourced_record_after_halt_clears_it(self) -> None:
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            for _ in range(4):
                _checkpoint(archive)
            self.assertTrue(stall_escalation(archive.read_events()))
            archive.append("request", "operator redirected the work",
                           {"digest": "x", "status": "open", "source": "stated"})
            self.assertEqual(stall_escalation(archive.read_events()), [])

    def test_an_inferred_record_does_not_clear_the_halt(self) -> None:
        # source="inferred" is the agent's own reading, not an operator's -
        # it must not count as the human escalation the halt asked for.
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            for _ in range(4):
                _checkpoint(archive)
            archive.append("request", "agent inferred a direction",
                           {"digest": "x", "status": "open", "source": "inferred"})
            findings = stall_escalation(archive.read_events())
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["detector"], "stall-escalation")

    def test_progress_between_checkpoints_breaks_the_streak(self) -> None:
        from godmode_runtime.godmode_loop import stall_escalation

        with isolated_archive() as (_project, archive):
            _checkpoint(archive)
            _checkpoint(archive)
            archive.append("attestation", "check:ran", {"status": "ran", "session": "s"})
            _checkpoint(archive)
            # Streak reset by the attestation, so only one empty round follows it.
            self.assertEqual(stall_escalation(archive.read_events()), [])

    def test_analyze_folds_the_stall_finding_into_blocking(self) -> None:
        from godmode_runtime.godmode_loop import analyze

        with isolated_archive() as (_project, archive):
            for _ in range(4):
                _checkpoint(archive)
            report = analyze(archive)
            self.assertTrue(report["blocking"])
            self.assertTrue(
                [f for f in report["findings"] if f["detector"] == "stall-escalation"])


class StateFreshnessWatchdogTests(unittest.TestCase):
    """U-R2's freshness watchdog: a loop-active claim needs a fresh archive;
    a stale head file while active routes to the same human-escalation path
    as a stall streak."""

    def test_inactive_loop_is_not_evaluated(self) -> None:
        from godmode_runtime.godmode_guardrails import state_freshness

        with isolated_archive() as (_project, archive):
            verdict = state_freshness(archive, active=False)
            self.assertFalse(verdict["stale"])
            self.assertEqual(verdict["verdict"], "not-active")

    def test_active_loop_with_a_fresh_archive_is_nominal(self) -> None:
        from godmode_runtime.godmode_guardrails import state_freshness

        with isolated_archive() as (_project, archive):
            archive.append("change", "touch it", {"files": ["a.py"]})
            verdict = state_freshness(archive, active=True, max_age_s=900)
            self.assertFalse(verdict["stale"])
            self.assertEqual(verdict["verdict"], "nominal")

    def test_active_loop_with_a_stale_head_escalates(self) -> None:
        from godmode_runtime.godmode_guardrails import state_freshness

        with isolated_archive() as (_project, archive):
            archive.append("change", "touch it", {"files": ["a.py"]})
            old = time.time() - 10_000
            os.utime(archive.head, (old, old))
            verdict = state_freshness(archive, active=True, max_age_s=900)
            self.assertTrue(verdict["stale"])
            self.assertEqual(verdict["verdict"], "human-escalation")

    def test_watchdog_folds_freshness_in_when_loop_active_is_set(self) -> None:
        from godmode_runtime.godmode_attest import open_session
        from godmode_runtime.godmode_guardrails import watchdog

        with isolated_archive() as (_project, archive):
            session = open_session(archive, "watch")
            old = time.time() - 10_000
            os.utime(archive.head, (old, old))
            nominal = watchdog(archive, session, loop_active=False)
            self.assertEqual(nominal["verdict"], "nominal")
            escalated = watchdog(archive, session, loop_active=True, max_state_age_s=900)
            self.assertEqual(escalated["verdict"], "interrupt")
            self.assertTrue(escalated["freshness"]["stale"])


class MaturityDeclarationTests(unittest.TestCase):
    """Task 10b: maturity is report-only|assisted; unattended is refused."""

    def test_legal_maturities_are_accepted(self) -> None:
        from godmode_runtime.godmode_loop import declare_maturity

        self.assertEqual(declare_maturity("report-only"), "report-only")
        self.assertEqual(declare_maturity("assisted"), "assisted")

    def test_unattended_is_refused_and_names_the_policy(self) -> None:
        from godmode_runtime.godmode_errors import ArchiveError
        from godmode_runtime.godmode_loop import declare_maturity

        with self.assertRaises(ArchiveError) as ctx:
            declare_maturity("unattended")
        message = str(ctx.exception).lower()
        self.assertIn("unattended", message)
        self.assertIn("refused", message)

    def test_unknown_maturity_is_also_refused(self) -> None:
        from godmode_runtime.godmode_errors import ArchiveError
        from godmode_runtime.godmode_loop import declare_maturity

        with self.assertRaises(ArchiveError):
            declare_maturity("fully-autonomous")


class LoopPreflightTests(unittest.TestCase):
    """Task 10b: `loop_ready` audits a declaration's structural shape before
    the first cycle."""

    _READY = {
        "maturity": "assisted",
        "stop_contract": "max_records:50",
        "budget_s": 300,
        "verdict_path": "godmode-state/verdict.json",
        "escalation": {"n1": 2, "n2": 4},
    }

    def test_a_complete_declaration_is_ready(self) -> None:
        from godmode_runtime.godmode_loop import loop_ready

        verdict = loop_ready(dict(self._READY))
        self.assertEqual(verdict["verdict"], "ready")
        self.assertFalse(verdict["blocking"])
        self.assertEqual(verdict["findings"], [])

    def test_missing_stop_contract_is_pre_flight_red(self) -> None:
        from godmode_runtime.godmode_loop import loop_ready

        declaration = dict(self._READY)
        del declaration["stop_contract"]
        verdict = loop_ready(declaration)
        self.assertEqual(verdict["verdict"], "not-ready")
        self.assertTrue(verdict["blocking"])
        self.assertTrue(
            [f for f in verdict["findings"] if f["check"] == "stop-contract"])

    def test_missing_budget_is_pre_flight_red(self) -> None:
        from godmode_runtime.godmode_loop import loop_ready

        declaration = dict(self._READY)
        del declaration["budget_s"]
        verdict = loop_ready(declaration)
        self.assertTrue(verdict["blocking"])
        self.assertTrue([f for f in verdict["findings"] if f["check"] == "budget"])

    def test_missing_verdict_path_is_pre_flight_red(self) -> None:
        from godmode_runtime.godmode_loop import loop_ready

        declaration = dict(self._READY)
        del declaration["verdict_path"]
        verdict = loop_ready(declaration)
        self.assertTrue(verdict["blocking"])
        self.assertTrue(
            [f for f in verdict["findings"] if f["check"] == "verdict-path"])

    def test_insane_escalation_thresholds_are_pre_flight_red(self) -> None:
        from godmode_runtime.godmode_loop import loop_ready

        declaration = dict(self._READY)
        declaration["escalation"] = {"n1": 4, "n2": 2}  # backwards
        verdict = loop_ready(declaration)
        self.assertTrue(verdict["blocking"])
        self.assertTrue(
            [f for f in verdict["findings"] if f["check"] == "escalation-thresholds"])

    def test_declaring_unattended_is_refused_before_any_finding_is_computed(self) -> None:
        from godmode_runtime.godmode_errors import ArchiveError
        from godmode_runtime.godmode_loop import loop_ready

        declaration = dict(self._READY)
        declaration["maturity"] = "unattended"
        with self.assertRaises(ArchiveError):
            loop_ready(declaration)


if __name__ == "__main__":
    unittest.main()
