"""Cheap gates run before the suite, and a red one stops the suite from
starting (0.3.31: seconds-long workflow gates refused pushes only after
a 35-minute suite had run)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test_push_preflight import _git, _sharded_repo  # noqa: E402

from godmode_runtime.godmode_preflight import push_preflight  # noqa: E402

_SUITE = ["python -m unittest discover"]


class PreflightOrderTests(unittest.TestCase):
    def test_stale_gate_table_stops_before_the_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            (repo / "hooks").mkdir()
            (repo / "hooks" / "gate_table.json").write_text(
                '{"generated_from": "000000000000"}', encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "stale table")
            report = push_preflight(repo, suite=_SUITE, suite_shards=4)
            findings = [f for f in report["mechanical"] if f["check"] == "gate-table"]
            self.assertEqual(len(findings), 1, report["mechanical"])
            self.assertIn("hooks/gate_table.json", findings[0]["detail"])
            self.assertIn("scripts/dev/build_decision_table.py", findings[0]["detail"])
            self.assertEqual(report["shards_ran"], [])
            self.assertFalse([j for j in report["judgment"] if j["check"] == "suite"])
            self.assertEqual(report["stopped_at"]["check"], "gate-table")
            self.assertTrue(any(s.startswith("suite: not run") for s in report["skipped"]),
                            report["skipped"])

    def test_red_workflow_gate_stops_before_the_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            (repo / "gate_red.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            workflow = repo / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "godmode-verify.yml").write_text(
                "jobs:\n  verify:\n    steps:\n      - run: python gate_red.py\n",
                encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "red gate")
            report = push_preflight(repo, suite=_SUITE, suite_shards=4)
            self.assertEqual(report["stopped_at"],
                             {"check": "workflow-gate", "command": "python gate_red.py"})
            self.assertEqual(report["shards_ran"], [])
            self.assertEqual(report["verdict"], "findings")

    def test_untracked_edit_after_retest_is_named_not_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            (repo / "late_edit.py").write_text("y = 2\n", encoding="utf-8")
            (repo / "notes.txt").write_text("scratch\n", encoding="utf-8")
            report = push_preflight(repo)
            self.assertEqual(report["untracked_after_retest"], ["late_edit.py", "notes.txt"])
            finding = [j for j in report["judgment"] if j["check"] == "untracked-after-retest"]
            self.assertEqual(len(finding), 1, report["judgment"])
            self.assertIn("late_edit.py", finding[0]["detail"])
            self.assertEqual(report["verdict"], "findings")

    def test_green_gates_still_run_every_shard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _sharded_repo(Path(tmp), failing="c")
            report = push_preflight(repo, suite=_SUITE, suite_shards=4)
            self.assertIsNone(report["stopped_at"])
            self.assertEqual(report["shards_ran"], [0, 1, 2, 3])
            suite = [j for j in report["judgment"] if j["check"] == "suite"]
            self.assertEqual(len(suite), 1, report["judgment"])


if __name__ == "__main__":
    unittest.main()
