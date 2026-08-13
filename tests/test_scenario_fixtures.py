"""Two formerly host-only scenarios, staged locally after all.

tool-call-interception and concurrent-agent-collision were listed in
NEEDS_A_HOST, but neither actually needed a live host - they needed the
real entrypoint instead of the function it wraps. hooks/godmode_session_hook.py
IS the pre-tool boundary (this project drove it directly, as a subprocess,
throughout its own hook-latency optimisation); Chronicle's write_lock is
built specifically to serialise concurrent writers, testable with real
threads against one archive.

Each carries its own negative control here (not just at the point of
discovery): the guard disabled, the assertion proven capable of going red.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_scenarios import (  # noqa: E402
    NEEDS_A_HOST, SCENARIOS, run,
)


class ScenarioMigrationTests(unittest.TestCase):
    def test_both_scenarios_moved_out_of_needs_a_host(self) -> None:
        host_only = {name for name, _ in NEEDS_A_HOST}
        self.assertNotIn("tool-call-interception", host_only)
        self.assertNotIn("concurrent-agent-collision", host_only)

    def test_both_scenarios_are_now_staged(self) -> None:
        staged = {entry[0] for entry in SCENARIOS}
        self.assertIn("tool-call-interception", staged)
        self.assertIn("concurrent-agent-collision", staged)

    def test_two_host_only_scenarios_remain_and_are_named(self) -> None:
        self.assertEqual(len(NEEDS_A_HOST), 2)
        for name, why in NEEDS_A_HOST:
            self.assertTrue(why)

    def test_tool_call_interception_is_caught(self) -> None:
        report = run(only="tool-call-interception")
        self.assertTrue(report["scenarios"][0]["caught"])

    def test_concurrent_agent_collision_is_caught(self) -> None:
        report = run(only="concurrent-agent-collision")
        self.assertTrue(report["scenarios"][0]["caught"])


class NegativeControlTests(unittest.TestCase):
    """Proven at discovery time, pinned here so it stays proven."""

    def test_a_boundary_that_never_refuses_is_not_caught(self) -> None:
        import json
        import subprocess

        from godmode_runtime import godmode_scenarios as scen

        def always_allows(project, archive):
            result = subprocess.run(
                [sys.executable, "-c", "print('{}')"],
                input="{}", capture_output=True, text=True, timeout=10)
            decision = json.loads(result.stdout)
            permission = decision.get("hookSpecificOutput", {}).get("permissionDecision")
            return permission in ("ask", "deny"), f"permissionDecision={permission!r}"

        original = scen.SCENARIOS
        scen.SCENARIOS = tuple(
            (n, r, f, always_allows) if n == "tool-call-interception" else (n, r, f, fn)
            for n, r, f, fn in original
        )
        try:
            report = scen.run(only="tool-call-interception")
        finally:
            scen.SCENARIOS = original
        self.assertFalse(report["scenarios"][0]["caught"])

    def test_a_disabled_write_lock_produces_a_corrupted_chain(self) -> None:
        import contextlib

        from godmode_runtime.godmode_chronicle import Chronicle
        from godmode_runtime import godmode_scenarios as scen

        @contextlib.contextmanager
        def noop_lock(self, timeout_seconds=5.0):
            yield

        original_lock = Chronicle.write_lock
        Chronicle.write_lock = noop_lock
        try:
            report = scen.run(only="concurrent-agent-collision")
        finally:
            Chronicle.write_lock = original_lock
        self.assertFalse(report["scenarios"][0]["caught"])
        self.assertIn("sequence is not contiguous",
                      report["scenarios"][0]["observed"].lower())


if __name__ == "__main__":
    unittest.main()
