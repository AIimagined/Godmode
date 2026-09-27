"""A push is staged only over a green preflight at HEAD; preflight runs
the workflow's own gates (Codex audit of 37 red CI runs, 2026-09-10)."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _slow import slow  # noqa: E402

from godmode_runtime.godmode_preflight import (preflight_gate, shard_modules,  # noqa: E402
                                              suite_growth_finding,
                                              workflow_gate_commands)
from test_godmode_runtime import isolated_project  # noqa: E402

WORKFLOW = """name: x
jobs:
  verify:
    steps:
      - run: python -m compileall scripts hooks tests
      - run: python -m unittest discover -s tests -v
      - run: python scripts/godmode.py --version
      - run: python scripts/godmode.py --project . selftest --brief
      - run: python scripts/godmode.py --project . evals --brief
  other:
    steps:
      - run: python scripts/godmode.py --project . grid --brief
"""


@slow
class WorkflowGateTests(unittest.TestCase):
    def test_the_verify_job_gates_are_read_in_order_without_the_suite(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / ".github" / "workflows").mkdir(parents=True)
            (project / ".github" / "workflows" / "godmode-verify.yml").write_text(WORKFLOW, encoding="utf-8")
            self.assertEqual(workflow_gate_commands(project), [
                "python -m compileall scripts hooks tests",
                "python scripts/godmode.py --project . selftest --brief",
                "python scripts/godmode.py --project . evals --brief",
            ])

    def test_this_repository_declares_its_gates(self) -> None:
        gates = workflow_gate_commands(PLUGIN_ROOT)
        self.assertGreaterEqual(len(gates), 10)
        self.assertTrue(any("verb" in g or "selftest" in g for g in gates))

    def test_shards_cover_every_module_once(self) -> None:
        shards = shard_modules(PLUGIN_ROOT / "tests", 4)
        flat = sorted(m for shard in shards for m in shard)
        self.assertEqual(flat, sorted(set(flat)))
        self.assertIn("tests.test_preflight_gate", flat)


@slow
class StageGateTests(unittest.TestCase):
    def test_a_push_needs_a_green_preflight_at_head(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
                            "-m", "x"], cwd=project, check=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True).stdout.strip()
            self.assertIsNone(preflight_gate(archive, project, "git status"))
            reason = preflight_gate(archive, project, "git push origin main")
            self.assertIn("no preflight attestation", reason)
            archive.append("attestation", "preflight", {"status": "failed", "head": head, "session": "s"}, evidence=[])
            self.assertIn("failed", preflight_gate(archive, project, "git push origin main"))
            archive.append("attestation", "preflight", {"status": "ran", "head": "0" * 40, "session": "s"}, evidence=[])
            self.assertIn("HEAD is", preflight_gate(archive, project, "gh release create v1"))
            archive.append("attestation", "preflight", {"status": "ran", "head": head, "session": "s"}, evidence=[])
            self.assertIsNone(preflight_gate(archive, project, "git push origin main"))

    def test_a_reworded_commit_reuses_the_verdict_and_a_file_change_does_not(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            (project / "a.txt").write_text("a", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=project, check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], cwd=project, check=True)
            tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=project,
                                  capture_output=True, text=True).stdout.strip()
            archive.append("attestation", "preflight",
                           {"status": "ran", "head": "0" * 40, "tree": tree, "session": "s"}, evidence=[])
            subprocess.run(git + ["commit", "-q", "--amend", "-m", "reworded"], cwd=project, check=True)
            self.assertIsNone(preflight_gate(archive, project, "git push origin main"))
            (project / "a.txt").write_text("b", encoding="utf-8")
            subprocess.run(git + ["commit", "-q", "-am", "y"], cwd=project, check=True)
            self.assertIsNotNone(preflight_gate(archive, project, "git push origin main"))


@slow
class CiVerifiedBranchTests(unittest.TestCase):
    def test_a_plain_push_to_a_branch_ci_runs_on_needs_no_local_preflight(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / ".github" / "workflows").mkdir(parents=True)
            (project / ".github" / "workflows" / "godmode-verify.yml").write_text(
                'on:\n  push:\n    branches: [main, "sprint/**"]\n', encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
                            "-m", "x"], cwd=project, check=True)
            self.assertIsNone(preflight_gate(archive, project, "git push origin sprint/v1"))
            self.assertIsNone(preflight_gate(archive, project, "git push origin HEAD:sprint/v1"))
            for held in ("git push origin main", "git push origin HEAD:main", "git push --force origin sprint/v1",
                         "git push origin sprint/v1;echo x", "git push origin :sprint/v1", "git push origin v1"):
                self.assertIsNotNone(preflight_gate(archive, project, held), held)


@slow
class RemoteRefTests(unittest.TestCase):
    def test_origin_branch_stands_in_for_a_missing_upstream(self) -> None:
        from godmode_runtime.godmode_preflight import _remote_ref

        with isolated_project() as (project, _s, _a, _archive):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project)]
            subprocess.run(["git", "init", "-q", "-b", "main", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"], check=True, capture_output=True)
            self.assertEqual(_remote_ref(project), "")
            subprocess.run(git + ["update-ref", "refs/remotes/origin/main", "HEAD"], check=True, capture_output=True)
            self.assertEqual(_remote_ref(project), "origin/main")


def _write_test_module(project: Path, name: str, count: int) -> None:
    (project / "tests").mkdir(exist_ok=True)
    body = "\n\n".join(f"def test_{i}():\n    pass" for i in range(count)) + "\n"
    (project / "tests" / f"test_{name}.py").write_text(body, encoding="utf-8")


def _commit(project: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message],
                   cwd=project, check=True, capture_output=True)


@slow
class SuiteGrowthFindingTests(unittest.TestCase):
    """Release check: how much `tests/test_*.py` grew (modules, `def
    test_` functions) since `git describe --tags --abbrev=0` .. HEAD.
    Reports nothing with no previous tag; a finding only past 10% growth
    over the previous count."""

    def test_no_previous_tag_reports_nothing(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 5)
            _commit(project, "seed")
            self.assertIsNone(suite_growth_finding(project))

    def test_git_unavailable_reports_nothing(self) -> None:
        # Not a git repository at all: `git describe` fails the same way
        # a missing git binary would for this check's purposes.
        with isolated_project() as (project, _s, _a, _archive):
            self.assertIsNone(suite_growth_finding(project))

    def test_growth_under_ten_percent_reports_nothing(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 20)
            _commit(project, "seed")
            subprocess.run(["git", "tag", "v1.0.0"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 21)  # +1 of 20 = 5%
            _commit(project, "one more test")
            self.assertIsNone(suite_growth_finding(project))

    def test_growth_over_ten_percent_is_a_finding(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 10)
            _commit(project, "seed")
            subprocess.run(["git", "tag", "v1.0.0"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 13)  # +3 of 10 = 30%
            _commit(project, "more tests")
            finding = suite_growth_finding(project)
            self.assertIsNotNone(finding)
            self.assertEqual(finding["check"], "suite-growth")
            self.assertIn("v1.0.0", finding["detail"])

    def test_a_new_test_module_alone_can_cross_the_threshold(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 10)
            _commit(project, "seed")
            subprocess.run(["git", "tag", "v1.0.0"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "b", 5)
            _commit(project, "new module")
            finding = suite_growth_finding(project)
            self.assertIsNotNone(finding)


@slow
class SuiteGrowthProjectModeTests(unittest.TestCase):
    """R1 "enforce harm, advise on quality" as it lands on the suite-growth
    check: past-10% growth is informational in the default advise mode
    and a real finding in strict mode - the same rule the rest of the
    archive-scan slice already follows."""

    def _repo_over_threshold(self, project: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
        _write_test_module(project, "a", 10)
        _commit(project, "seed")
        subprocess.run(["git", "tag", "v1.0.0"], cwd=project, check=True, capture_output=True)
        _write_test_module(project, "a", 13)
        _commit(project, "more tests")

    def test_advise_mode_reports_growth_as_advisory(self) -> None:
        from unittest import mock

        from godmode_runtime.godmode_preflight import push_preflight

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._repo_over_threshold(project)
            archive.append("assumption", "the bed assumes nothing moves", {"detail": "test fixture"})
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=None):
                report = push_preflight(project, archive=archive)
            findings = [j for j in report["judgment"] if j.get("check") == "suite-growth"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].get("severity"), "advisory")

    def test_strict_mode_leaves_the_growth_finding_blocking(self) -> None:
        from unittest import mock

        from godmode_runtime.godmode_preflight import push_preflight
        from godmode_runtime.godmode_projectmode import set_project_mode

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._repo_over_threshold(project)
            archive.append("assumption", "the bed assumes nothing moves", {"detail": "test fixture"})
            set_project_mode(archive, "strict")
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=None):
                report = push_preflight(project, archive=archive)
            findings = [j for j in report["judgment"] if j.get("check") == "suite-growth"]
            self.assertEqual(len(findings), 1)
            self.assertNotEqual(findings[0].get("severity"), "advisory")
            self.assertEqual(report["verdict"], "findings")

    def test_no_tag_yields_no_finding_either_mode(self) -> None:
        from unittest import mock

        from godmode_runtime.godmode_preflight import push_preflight

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
            _write_test_module(project, "a", 10)
            _commit(project, "seed")
            archive.append("assumption", "the bed assumes nothing moves", {"detail": "test fixture"})
            with mock.patch("godmode_runtime.godmode_reach.reach_finding", return_value=None):
                report = push_preflight(project, archive=archive)
            findings = [j for j in report["judgment"] if j.get("check") == "suite-growth"]
            self.assertEqual(findings, [])


@slow
class AttestationSemanticsTests(unittest.TestCase):
    def test_judgment_findings_ride_a_ran_attestation_and_mechanical_ones_fail_it(self) -> None:
        import inspect

        from godmode_runtime import godmode_preflight as pf

        source = inspect.getsource(pf.push_preflight)
        self.assertIn('status = "ran"', source)
        self.assertIn('elif mechanical or suite_red:', source)
        self.assertIn('"history-terms-pushed"', source)


if __name__ == "__main__":
    unittest.main()
