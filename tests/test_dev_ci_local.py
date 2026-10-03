"""scripts/dev/ci_local.py: which path it picks, and the pure workflow-job
parsing it picks Linux jobs with.

Smoke only: PATH lookups are mocked so this never needs a real local Actions
runner or Docker, and the two execution paths are stubbed so this never
actually spends the ~30 min local run or shells out to a container tool.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = PLUGIN_ROOT / "scripts" / "dev"
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))

import ci_local  # noqa: E402

_WORKFLOW_SAMPLE = """\
name: sample

jobs:
  verify:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - run: echo hi

  netgate:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi

  verify-windows:
    runs-on: windows-latest
    steps:
      - run: echo hi
"""


class LinuxJobNamesTests(unittest.TestCase):
    def test_bare_ubuntu_latest_job_is_selected(self) -> None:
        self.assertEqual(ci_local.linux_job_names(_WORKFLOW_SAMPLE), ["netgate"])

    def test_matrix_and_other_os_jobs_are_not_selected(self) -> None:
        names = ci_local.linux_job_names(_WORKFLOW_SAMPLE)
        self.assertNotIn("verify", names)
        self.assertNotIn("verify-windows", names)

    def test_the_committed_workflow_yields_the_known_linux_jobs(self) -> None:
        text = ci_local.WORKFLOW.read_text(encoding="utf-8")
        names = ci_local.linux_job_names(text)
        for expected in ("netgate", "corpus-differential", "vuln-scan", "action"):
            self.assertIn(expected, names)
        for excluded in ("verify", "verify-windows", "stock-host", "stock-host-windows"):
            self.assertNotIn(excluded, names)


class PathSelectionTests(unittest.TestCase):
    def _which(self, present: set[str]):
        def fake(name: str):
            return f"/usr/bin/{name}" if name in present else None
        return fake

    def test_runner_and_docker_present_takes_the_runner_path(self) -> None:
        with mock.patch.object(ci_local.shutil, "which", side_effect=self._which({"act", "docker"})), \
             mock.patch.object(ci_local, "run_via_local_runner", return_value=0) as run_runner, \
             mock.patch.object(ci_local, "run_native") as run_native:
            code = ci_local.main([])
        self.assertEqual(code, 0)
        run_runner.assert_called_once()
        run_native.assert_not_called()

    def test_runner_present_without_docker_falls_back_to_native(self) -> None:
        with mock.patch.object(ci_local.shutil, "which", side_effect=self._which({"act"})), \
             mock.patch.object(ci_local, "run_via_local_runner") as run_runner, \
             mock.patch.object(ci_local, "run_native", return_value=0) as run_native:
            code = ci_local.main([])
        self.assertEqual(code, 0)
        run_native.assert_called_once()
        run_runner.assert_not_called()

    def test_neither_on_path_falls_back_to_native(self) -> None:
        with mock.patch.object(ci_local.shutil, "which", side_effect=self._which(set())), \
             mock.patch.object(ci_local, "run_via_local_runner") as run_runner, \
             mock.patch.object(ci_local, "run_native", return_value=0) as run_native:
            code = ci_local.main([])
        self.assertEqual(code, 0)
        run_native.assert_called_once()
        run_runner.assert_not_called()

    def test_native_flag_skips_the_runner_path_even_when_both_are_on_path(self) -> None:
        with mock.patch.object(ci_local.shutil, "which", side_effect=self._which({"act", "docker"})), \
             mock.patch.object(ci_local, "run_via_local_runner") as run_runner, \
             mock.patch.object(ci_local, "run_native", return_value=0) as run_native:
            code = ci_local.main(["--native"])
        self.assertEqual(code, 0)
        run_native.assert_called_once()
        run_runner.assert_not_called()


class MatrixTests(unittest.TestCase):
    """The local check runs the Python versions CI runs, read from the
    workflow rather than typed by hand, and names a version this machine
    cannot run instead of silently skipping it."""

    def test_versions_come_from_the_workflow_matrix(self) -> None:
        text = 'matrix:\n  os: [ubuntu-latest]\n  python-version: ["3.11", "3.13"]\n'
        self.assertEqual(ci_local.ci_python_versions(text), ["3.11", "3.13"])
        self.assertEqual(ci_local.ci_python_versions("jobs:\n  x:\n"), [])

    def test_the_committed_workflow_names_at_least_two_versions(self) -> None:
        versions = ci_local.ci_python_versions(ci_local.WORKFLOW.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(versions), 2, versions)
        current = f"{sys.version_info[0]}.{sys.version_info[1]}"
        self.assertEqual(ci_local.interpreter_for(current), [sys.executable])

    def test_a_shim_on_path_is_resolved_to_the_interpreter_it_starts(self) -> None:
        probe = mock.Mock(returncode=0, stdout="/real/python8.8\n")
        with mock.patch.object(ci_local.os, "name", "posix"), \
             mock.patch.object(ci_local.shutil, "which", return_value="/shim/python8.8"), \
             mock.patch.object(ci_local.subprocess, "run", return_value=probe):
            self.assertEqual(ci_local.interpreter_for("8.8"), ["/real/python8.8"])

    def test_a_missing_interpreter_is_named_not_skipped(self) -> None:
        args = mock.Mock(full=False, base="origin/main", jobs=1, matrix=True)
        with mock.patch.object(ci_local, "select", return_value=["tests.test_x"]), \
             mock.patch.object(ci_local, "changed_files", return_value=set()), \
             mock.patch.object(ci_local, "module_map", return_value={}), \
             mock.patch.object(ci_local.subprocess, "call", return_value=0) as call, \
             mock.patch.object(ci_local, "ci_python_versions", return_value=["8.8", "9.9"]), \
             mock.patch.object(ci_local, "interpreter_for",
                               side_effect=lambda v: ["py", "-8.8"] if v == "8.8" else None), \
             mock.patch("builtins.print") as printed:
            code = ci_local.run_native(args)
        self.assertEqual(code, 0)
        argvs = [c.args[0] for c in call.call_args_list]
        # Neither version is ever the running one, so this holds under every interpreter CI uses.
        self.assertEqual(len(argvs), 2, argvs)
        self.assertEqual(argvs[1][:2], ["py", "-8.8"])
        self.assertIn("tests.test_x", argvs[1])
        said = " ".join(str(c.args[0]) for c in printed.call_args_list)
        self.assertIn("9.9", said)
        self.assertIn("not on this machine", said)


if __name__ == "__main__":
    unittest.main()
