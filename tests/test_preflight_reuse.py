"""Verification evidence is reused, not repeated: a green run already on
record for exactly this tree, interpreter and platform satisfies the push
preflight; a partial run never satisfies a full request; a different tree
is different evidence."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SCRIPTS / "dev") not in sys.path:
    sys.path.insert(0, str(SCRIPTS / "dev"))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime import godmode_preflight as pf  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


class ReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="godmode-reuse-")
        base = Path(self._temporary.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_a.py").write_text(
            "import unittest\nclass A(unittest.TestCase):\n    def test_a(self):\n        pass\n",
            encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "seed")
        self.tree = _git(self.repo, "rev-parse", "HEAD^{tree}")
        self._env = mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")})
        self._env.start()
        self.archive = Chronicle(resolve_anchor(self.repo))
        self.archive.initialize()

    def tearDown(self) -> None:
        self._env.stop()
        self._temporary.cleanup()

    def _record(self, subject: str, status: str, scope: str, suite: list[str] | None = None,
                tree: str | None = None, python: str | None = None) -> int:
        signature = pf.suite_signature(["--all"] if scope == "full" else suite)
        data = {"status": status, "tree": tree or self.tree, "seconds": 12.0,
                "python": python or pf._runtime_signature()["python"],
                "platform": sys.platform, **signature}
        return int(self.archive.append("attestation", subject, data, evidence=[])["sequence"])

    def test_a_green_full_run_by_the_runner_covers_any_selection(self) -> None:
        seq = self._record("suite-run", "green", "full")
        found = pf.reusable_suite_evidence(self.archive, self.tree, ["python", "x.py", "tests.test_a"])
        self.assertIsNotNone(found)
        self.assertEqual(found["sequence"], seq)
        self.assertEqual(found["covers"], "suite")

    def test_a_selection_covers_only_the_same_module_set(self) -> None:
        self._record("suite-run", "green", "selection", ["tests.test_a"])
        same = pf.reusable_suite_evidence(self.archive, self.tree, ["python", "run.py", "tests.test_a"])
        other = pf.reusable_suite_evidence(self.archive, self.tree, ["python", "run.py", "tests.test_b"])
        full = pf.reusable_suite_evidence(self.archive, self.tree, ["python", "run.py", "--all"])
        self.assertIsNotNone(same)
        self.assertIsNone(other, "a different module set is different evidence")
        self.assertIsNone(full, "a partial run never satisfies a full-release requirement")

    def test_a_red_run_another_tree_or_another_interpreter_is_not_evidence(self) -> None:
        self._record("suite-run", "red", "full")
        self.assertIsNone(pf.reusable_suite_evidence(self.archive, self.tree, None))
        self._record("suite-run", "green", "full", tree="0" * 40)
        self.assertIsNone(pf.reusable_suite_evidence(self.archive, self.tree, None))
        self._record("suite-run", "green", "full", python="2.7")
        self.assertIsNone(pf.reusable_suite_evidence(self.archive, self.tree, None))

    def test_a_green_preflight_on_this_tree_skips_the_whole_preflight(self) -> None:
        seq = self._record("preflight", "ran", "full")
        report = pf.push_preflight(self.repo, suite=["python", "-m", "unittest", "discover"],
                                   archive=self.archive)
        self.assertEqual(report["verdict"], "clean", report)
        self.assertTrue(report["suite_ran"])
        self.assertEqual(report["reused"]["sequence"], seq)
        newest = [r for r in self.archive.select(kind="attestation", limit=50)
                  if r.get("subject") == "preflight"][-1]
        self.assertEqual(newest["data"]["reused_from"], seq)
        self.assertEqual(newest["data"]["status"], "ran")

    def test_a_green_suite_run_skips_the_suite_and_keeps_the_gates(self) -> None:
        self._record("suite-run", "green", "full")
        with mock.patch.object(pf, "workflow_gate_commands", return_value=[]), \
                mock.patch.object(pf, "run_with_memory_cap") as ran:
            report = pf.push_preflight(self.repo, suite=["python", "-m", "unittest", "tests.test_a"],
                                       archive=self.archive)
        ran.assert_not_called()
        self.assertTrue(report["suite_ran"], report)
        self.assertEqual(report["reused"]["covers"], "suite")
        self.assertTrue(any(item.startswith("suite reused:") for item in report["skipped"]), report["skipped"])

    def test_a_shard_leg_never_reuses(self) -> None:
        self._record("preflight", "ran", "full")
        with mock.patch.object(pf, "workflow_gate_commands", return_value=[]), \
                mock.patch.object(pf, "run_with_memory_cap") as ran:
            ran.return_value = mock.Mock(returncode=0, memory_killed=False, stdout=b"", stderr=b"")
            report = pf.push_preflight(self.repo, suite=["python", "-m", "unittest", "discover"],
                                       archive=self.archive, suite_shards=2, shard_index=0)
        self.assertIsNone(report["reused"])

    def test_the_runner_records_a_timed_suite_run(self) -> None:
        import affected_tests
        with mock.patch.object(affected_tests, "REPO_ROOT", self.repo), \
                mock.patch.object(affected_tests, "_git",
                                  lambda *a: _git(self.repo, *a).splitlines()):
            affected_tests.record_suite_run(["tests.test_a"], full=False, code=0, seconds=4.2)
            affected_tests.record_suite_run(["tests.test_a"], full=False, code=0, seconds=3.9)
        runs = [r for r in Chronicle(resolve_anchor(self.repo)).select(kind="attestation", limit=50)
                if r.get("subject") == "suite-run"]
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["data"]["status"], "green")
        self.assertEqual(runs[0]["data"]["tree"], self.tree)
        self.assertEqual(runs[0]["data"]["seconds"], 4.2)
        self.assertEqual(runs[1]["data"]["repeat_of_same_tree"], 1)


if __name__ == "__main__":
    unittest.main()
