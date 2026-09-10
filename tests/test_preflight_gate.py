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

from godmode_runtime.godmode_preflight import (preflight_gate, shard_modules,  # noqa: E402
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
