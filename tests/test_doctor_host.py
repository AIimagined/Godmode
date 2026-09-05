"""`doctor --host <name>`: the wiring check a field machine can run itself.

Ninth field report 2026-09-05 (Codex): a project hook config pointed at a
0.3.4 install path that no longer existed, the archive home was unwritable
under the sandbox, and the codex binary was a PowerShell shim - each found
by hand. One command should answer: does the host's hook artifact exist
and parse, which interpreter answers, is the archive writable, and what
grade of interception is on record.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _doctor(project: Path, *args: str) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(["--project", str(project), "doctor", *args])
    return code, json.loads(out.getvalue())


class DoctorHostTests(unittest.TestCase):
    def test_a_known_host_reports_artifact_interpreter_archive_and_grade(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, report = _doctor(project, "--host", "grok")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["host"], "grok")
        self.assertIn("hook_artifact", report)
        self.assertTrue(report["hook_artifact"]["present"])
        self.assertTrue(report["hook_artifact"]["parses"])
        self.assertIn("interpreters", report)
        self.assertTrue(any(report["interpreters"].values()), report["interpreters"])
        self.assertIs(report["archive_writable"], True)
        self.assertIn(report["interception"], ("HARD", "DEGRADED", "PARTIAL", "SOFT", "UNAVAILABLE"))

    def test_an_unknown_host_is_refused_with_the_known_list(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, report = _doctor(project, "--host", "nonesuch")
        self.assertEqual(code, 1, report)
        self.assertIn("grok", report["refused"])


if __name__ == "__main__":
    unittest.main()
