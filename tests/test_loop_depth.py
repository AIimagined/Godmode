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


if __name__ == "__main__":
    unittest.main()
