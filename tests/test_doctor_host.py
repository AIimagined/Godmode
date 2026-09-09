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


    def test_codex_project_hooks_with_a_dead_install_path_are_reported(self) -> None:
        """Ninth field report 2026-09-05: the project's .codex/hooks.json
        pointed at a 0.3.4 install path that no longer existed, and nothing
        said so until a human read the file."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".codex").mkdir()
            (project / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command",
                 "command": 'cd "C:/old/godmode/0.3.4/hooks"; ./run-hook.cmd godmode_gate_fast.py'}]}]}}),
                encoding="utf-8")
            code, report = _doctor(project, "--host", "codex")
        self.assertEqual(code, 0, report)
        self.assertFalse(report["healthy"], report)
        self.assertTrue(any("0.3.4" in issue for issue in report["issues"]), report["issues"])
        self.assertIn("project_hooks", report)
        self.assertFalse(report["project_hooks"]["targets_exist"], report["project_hooks"])

    def test_a_launcher_without_its_executable_bit_is_named(self) -> None:
        # Runs on every OS: the POSIX rule is passed in, the mode bit is mocked.
        import os
        launcher = PLUGIN_ROOT / "hooks" / "run-hook.cmd"
        real_access = os.access
        def no_exec(path, mode, *args, **kwargs):
            if mode == os.X_OK and Path(str(path)) == launcher:
                return False
            return real_access(path, mode, *args, **kwargs)
        with mock.patch.object(os, "access", no_exec):
            issues = console._launcher_mode_issues(PLUGIN_ROOT, posix=True)
        self.assertEqual(len(issues), 1)
        self.assertIn("run-hook.cmd lost its executable bit", issues[0])
        self.assertIn("chmod +x", issues[0])
        self.assertEqual(console._launcher_mode_issues(PLUGIN_ROOT, posix=False), [])

    def test_an_unknown_host_is_refused_with_the_known_list(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, report = _doctor(project, "--host", "nonesuch")
        self.assertEqual(code, 1, report)
        self.assertIn("grok", report["refused"])


if __name__ == "__main__":
    unittest.main()
