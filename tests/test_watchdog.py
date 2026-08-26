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
