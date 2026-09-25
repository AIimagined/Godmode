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


if __name__ == "__main__":
    unittest.main()
