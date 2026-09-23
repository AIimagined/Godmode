"""C-55: an agent watchdog over the agent's own record.

No daemon - godmode is on demand, and the privacy boundary forbids a
watcher. "During a run" means invoked between steps, and the report says
so. It reads the newest window of the archive and names three anomaly
shapes: the same operation attempted again and again, a burst of
refusals, and a run of actions with no attestation behind them.
`--interrupt` writes the operator-stop flag the stop algebra already
honours, so an anomaly can halt the next guarded step without a new
mechanism.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
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

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_guardrails import OPERATOR_STOP_FLAG  # noqa: E402
from godmode_runtime.godmode_watchdog import watchdog_report  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-wd-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            yield root, archive


class WatchdogTests(unittest.TestCase):
    def test_a_repeated_operation_is_an_anomaly(self) -> None:
        with _project() as (_root, archive):
            for _ in range(3):
                archive.append("action", "shell", {"operation": "rm -rf build", "gate": "allow"})
            report = watchdog_report(archive)
        kinds = {a["kind"] for a in report["anomalies"]}
        self.assertIn("repeated-operation", kinds)
        self.assertEqual(report["verdict"], "anomaly")
        self.assertIn("between steps", report["note"])

    def test_three_different_relays_in_a_row_are_not_a_repeated_operation(self) -> None:
        # `agent-relay-seen` shares one subject on every hand-back - a
        # digest that fell back to `record["subject"]` (no distinguishing
        # `data["operation"]`) would read three DIFFERENT relays as the
        # same operation attempted three times. Each relay's data carries
        # a short hash prefix of its own prompt (mirroring
        # `hooks/godmode_session_hook.py`'s write), so distinct hand-backs
        # digest distinctly and never trip the repeat detector.
        with _project() as (_root, archive):
            for prompt in ("hand-back: report A", "hand-back: report B", "hand-back: report C"):
                archive.append("action", "agent-relay-seen",
                               {"chars": len(prompt),
                                "operation": "agent-relay:"
                                             + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]})
            report = watchdog_report(archive)
        kinds = {a["kind"] for a in report["anomalies"]}
        self.assertNotIn("repeated-operation", kinds)
        self.assertEqual(report["verdict"], "clean")

    def test_five_edits_to_different_files_are_not_a_repeated_operation(self) -> None:
        # Fix round 2 (Task 8 review, B2): `edit-recorded` shares one
        # subject on every edit, same failure mode as `agent-relay-seen`
        # above - a digest falling back to `record["subject"]` would read
        # five DIFFERENT edits as the same operation attempted five times.
        # `hooks/godmode_post_edit.py::_record_edit` writes the same
        # remedy: `data["operation"]` is a short hash prefix of the
        # edited path, so distinct paths digest distinctly.
        with _project() as (_root, archive):
            for i in range(5):
                path = f"src/file_{i}.py"
                archive.append("action", "edit-recorded", {
                    "path": path,
                    "operation": "edit:" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12],
                })
            report = watchdog_report(archive)
        kinds = {a["kind"] for a in report["anomalies"]}
        self.assertNotIn("repeated-operation", kinds)
        self.assertEqual(report["verdict"], "clean")

    def test_six_edits_without_an_attestation_are_not_an_unattested_run(self) -> None:
        # Fix round 2 (Task 8 review, B3): `edit-recorded` is bookkeeping
        # about an edit, never a run that wants attesting on its own - it
        # must not feed the unattested-run counter the way a real,
        # un-checked action does (compare
        # `test_actions_without_attestation_are_an_anomaly` above, which
        # is exactly six such actions and DOES trip the anomaly).
        with _project() as (_root, archive):
            for i in range(6):
                path = f"src/file_{i}.py"
                archive.append("action", "edit-recorded", {
                    "path": path,
                    "operation": "edit:" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12],
                })
            report = watchdog_report(archive)
        kinds = {a["kind"] for a in report["anomalies"]}
        self.assertNotIn("unattested-run", kinds)
        self.assertEqual(report["verdict"], "clean")

    def test_a_refusal_burst_is_an_anomaly(self) -> None:
        with _project() as (_root, archive):
            for n in range(3):
                archive.append("refusal", f"op-{n}", {"operation": f"git push --force {n}"})
            report = watchdog_report(archive)
        self.assertIn("refusal-burst", {a["kind"] for a in report["anomalies"]})

    def test_actions_without_attestation_are_an_anomaly(self) -> None:
        with _project() as (_root, archive):
            for n in range(6):
                archive.append("action", f"edit-{n}", {"operation": f"edit file{n}.py", "gate": "allow"})
            report = watchdog_report(archive)
        self.assertIn("unattested-run", {a["kind"] for a in report["anomalies"]})

    def test_a_quiet_record_is_clean_and_writes_no_flag(self) -> None:
        with _project() as (root, archive):
            archive.append("action", "edit-1", {"operation": "edit a.py", "gate": "allow"})
            archive.append("attestation", "tests", {"status": "ran", "result": "ok"})
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "watchdog", "--interrupt"])
            self.assertFalse((root / OPERATOR_STOP_FLAG).exists())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "clean")

    def test_interrupt_writes_the_operator_stop_flag_on_anomaly(self) -> None:
        with _project() as (root, archive):
            for _ in range(3):
                archive.append("action", "shell", {"operation": "rm -rf build", "gate": "allow"})
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "watchdog", "--interrupt"])
            self.assertTrue((root / OPERATOR_STOP_FLAG).is_file())
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertTrue(payload["interrupted"])


if __name__ == "__main__":
    unittest.main()
