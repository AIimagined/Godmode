"""The pre-tool boundary: metering that counts, and a gate that actually stops.

These prove the two controls the capability table used to call UNAVAILABLE:
a host-invoked decision point before each tool call, and spend measured by the
runtime rather than reported to it.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
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

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


class MeterTests(unittest.TestCase):
    def test_tool_calls_and_wall_time_are_measured_not_reported(self) -> None:
        from godmode_runtime.godmode_guardrails import meter_tool_call, read_meter

        with isolated_project() as (_project, archive):
            for _ in range(3):
                meter_tool_call(archive, "S-1", "Bash")
            meter = read_meter(archive, "S-1")
            self.assertEqual(meter["tool_calls"], 3)
            self.assertIn("Bash", meter["by_tool"])
            self.assertGreaterEqual(meter["seconds"], 0)
            self.assertEqual(meter["source"], "measured")

    def test_meter_is_per_session(self) -> None:
        from godmode_runtime.godmode_guardrails import meter_tool_call, read_meter

        with isolated_project() as (_project, archive):
            meter_tool_call(archive, "S-1", "Bash")
            meter_tool_call(archive, "S-2", "Read")
            self.assertEqual(read_meter(archive, "S-1")["tool_calls"], 1)
            self.assertEqual(read_meter(archive, "S-2")["tool_calls"], 1)

    def test_measured_spend_feeds_the_ceiling_verdict(self) -> None:
        from godmode_runtime.godmode_guardrails import (
            check_ceilings, meter_tool_call, read_meter,
        )

        with isolated_project() as (project, archive):
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tool_calls": 2}), encoding="utf-8")
            for _ in range(3):
                meter_tool_call(archive, "S-1", "Bash")
            verdict = check_ceilings(project, read_meter(archive, "S-1"))
            self.assertEqual(verdict["verdict"], "over-ceiling")
            self.assertEqual(verdict["exceeded"][0]["ceiling"], "tool_calls")

    def test_a_corrupt_meter_restarts_instead_of_raising(self) -> None:
        from godmode_runtime.godmode_guardrails import meter_tool_call, read_meter

        with isolated_project() as (_project, archive):
            meter_tool_call(archive, "S-1", "Bash")
            (archive.root / "godmode-meter.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(read_meter(archive, "S-1")["tool_calls"], 0)
            meter_tool_call(archive, "S-1", "Bash")
            self.assertEqual(read_meter(archive, "S-1")["tool_calls"], 1)


class ToolOperationTests(unittest.TestCase):
    def test_tool_payloads_become_classifiable_operations(self) -> None:
        from godmode_runtime.godmode_guardrails import tool_operation

        self.assertEqual(
            tool_operation("Bash", {"command": "git push origin main"}),
            "git push origin main")
        self.assertEqual(
            tool_operation("Write", {"file_path": "src/app.py"}), "write file src/app.py")
        self.assertEqual(
            tool_operation("Edit", {"file_path": "src/app.py"}), "edit file src/app.py")
        # An unknown tool still yields something the classifier can fail closed on.
        self.assertIn("Unknown", tool_operation("Unknown", {"x": 1}))


class PreToolGateTests(unittest.TestCase):
    """The hook is invoked as the host invokes it: JSON on stdin, exit code out."""

    def _run(self, payload: dict, project: Path, state: Path) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        return subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"),
             "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", timeout=120, env=environment,
        )

    @contextmanager
    def _hosted(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
            yield project, state, archive

    def test_read_only_tool_use_is_allowed(self) -> None:
        with self._hosted() as (project, state, _archive):
            done = self._run({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "git status"}}, project, state)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("permissionDecision", done.stdout)

    def test_protected_tool_use_is_denied_in_the_hosts_own_contract(self) -> None:
        with self._hosted() as (project, state, _archive):
            done = self._run({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "git push --force origin main"}},
                             project, state)
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            decision = payload["hookSpecificOutput"]
            self.assertEqual(decision["hookEventName"], "PreToolUse")
            self.assertEqual(decision["permissionDecision"], "deny")
            self.assertIn("capability", decision["permissionDecisionReason"].lower())

    def test_a_skip_pattern_interrupts_the_run_at_the_next_tool_call(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with self._hosted() as (project, state, archive):
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                session = open_session(archive, "gate")
                for step in ("read sources", "run parity", "check invariants"):
                    record_step(archive, session, step, "skipped", reason="in a hurry")
            done = self._run({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "git status"}}, project, state)
            payload = json.loads(done.stdout)
            decision = payload["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "deny")
            self.assertIn("skipped", decision["permissionDecisionReason"])

    def test_an_exceeded_ceiling_stops_the_run(self) -> None:
        with self._hosted() as (project, state, _archive):
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tool_calls": 2}), encoding="utf-8")
            # A mutating tool: read-only tools are exempt from the gate by name,
            # so they never reach the meter.
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                       "tool_input": {"file_path": "a.py"}}
            for _ in range(3):
                done = self._run(payload, project, state)
            body = json.loads(done.stdout)
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("ceiling", body["hookSpecificOutput"]["permissionDecisionReason"])

    def test_read_only_tools_skip_the_gate_entirely(self) -> None:
        with self._hosted() as (project, state, _archive):
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tool_calls": 1}), encoding="utf-8")
            for _ in range(4):
                done = self._run({"hook_event_name": "PreToolUse", "tool_name": "Read",
                                  "tool_input": {"file_path": "a.py"}}, project, state)
            # Never metered, never denied: a read cannot breach a mutation budget.
            self.assertEqual(done.returncode, 0)
            self.assertEqual(done.stdout.strip(), "")

    def test_an_uninitialized_project_never_blocks_the_host(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "fresh"
            project.mkdir()
            done = self._run({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "rm -rf /"}}, project, base / "state")
            # No archive means no contract to enforce; the gate must not brick a
            # project that never opted in.
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn('"deny"', done.stdout)


class CapabilityReportingTests(unittest.TestCase):
    """CX-1: the env-var sniff is gone. See tests/test_hookproof.py for the full
    live-proof contract this exercises; this class only guards the specific
    regression that motivated the change - an operator exporting
    GODMODE_PRETOOL_GATE by hand used to fake HARD with no hook involved."""

    def test_the_env_var_alone_never_fakes_hard(self) -> None:
        from godmode_runtime.godmode_anchor import host_capabilities
        from godmode_runtime.godmode_hookproof import interception_state

        with mock.patch.dict(os.environ, {"GODMODE_PRETOOL_GATE": "1"}, clear=False):
            # No interception evidence passed at all: the same honest
            # UNAVAILABLE as no proof existing.
            self.assertEqual(
                host_capabilities()["controls"]["tool_call_interception"], "UNAVAILABLE")
            with isolated_project() as (_project, archive):
                # An archive with no proof record: still UNAVAILABLE, even
                # with the variable set.
                state = interception_state(archive, "claude")
                self.assertEqual(
                    host_capabilities(tool_call_interception=state)
                    ["controls"]["tool_call_interception"],
                    "UNAVAILABLE",
                )

    def test_interception_is_reported_hard_only_from_a_real_proof(self) -> None:
        from godmode_runtime.godmode_anchor import current_host, host_capabilities
        from godmode_runtime.godmode_hookproof import (
            interception_state, record_interception_proof)

        environment = {k: v for k, v in os.environ.items() if k != "GODMODE_PRETOOL_GATE"}
        with mock.patch.dict(os.environ, environment, clear=True):
            with isolated_project() as (_project, archive):
                host = current_host()
                self.assertEqual(
                    host_capabilities(tool_call_interception=interception_state(archive, host))
                    ["controls"]["tool_call_interception"],
                    "UNAVAILABLE",
                )
                record_interception_proof(archive, host=host, tool="Bash", request_id="n1")
                self.assertEqual(
                    host_capabilities(tool_call_interception=interception_state(archive, host))
                    ["controls"]["tool_call_interception"],
                    "HARD",
                )


if __name__ == "__main__":
    unittest.main()
