"""CX-1: truthful interception proof.

`GODMODE_PRETOOL_GATE` used to be read as evidence that a host actually calls
the pre-tool boundary, and nothing ever set it - so the claim could be wrong
in both directions: silently absent while the hook really was firing, and
trivially fakeable by any operator who exported the variable by hand. This
replaces the sniff with a chronicled live proof: a marker operation
(`godmode-probe:<nonce>`) that the hook treats as protected, denies
unconditionally, and records the denial for. `interception_state` reads that
record back, and only calls it `HARD` when the proof is fresh and nothing
newer says the hook came down.
"""

from __future__ import annotations

import argparse
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

from godmode_runtime.godmode_anchor import host_capabilities, resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_hooks  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    PROBE_PREFIX,
    SUBJECT_ANCHOR,
    SUBJECT_PROBE_FAILED,
    SUBJECT_UNINSTALLED,
    interception_state,
    last_proof,
    record_interception_proof,
    record_session_anchor,
    run_probe,
)

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"


def _no_denial_response() -> subprocess.CompletedProcess:
    # The reviewer's own live repro: a hook subprocess that returns 0 but
    # never emits a deny decision at all - a crashed, renamed, or silently
    # degraded hook, indistinguishable at the JSON layer from "this call
    # was never protected".
    return subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse"}}),
        stderr="",
    )


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


class RecordProofTests(unittest.TestCase):
    def test_record_interception_proof_is_content_free(self) -> None:
        with isolated_project() as (_project, archive):
            record = record_interception_proof(
                archive, host="claude", tool="Bash", request_id="abc123")
            self.assertEqual(record["kind"], "action")
            self.assertEqual(record["subject"], "hook-interception-proof")
            self.assertEqual(
                record["data"],
                {"host": "claude", "tool": "Bash", "request_id": "abc123", "proof": True},
            )

    def test_last_proof_returns_newest_matching_host(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="claude", tool="Bash", request_id="one")
            second = record_interception_proof(archive, host="claude", tool="Bash", request_id="two")
            found = last_proof(archive, "claude")
            self.assertEqual(found["sequence"], second["sequence"])
            self.assertIn("recorded_at", found)
            self.assertIsNone(last_proof(archive, "codex"))

    def test_last_proof_with_no_host_filter_finds_any(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="codex", tool="shell_command", request_id="x")
            self.assertIsNotNone(last_proof(archive, None))

    def test_a_malformed_proof_record_is_refused(self) -> None:
        # Direct-append bypass, same defense-in-depth every other kind here
        # gets: a proof-shaped record missing a required field enforces
        # nothing while claiming to, so the archive refuses it outright.
        with isolated_project() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append(
                    "action", "hook-interception-proof",
                    {"host": "claude", "tool": "", "request_id": "x", "proof": True},
                    evidence=[],
                )


class InterceptionStateTests(unittest.TestCase):
    def test_no_proof_is_unavailable(self) -> None:
        with isolated_project() as (_project, archive):
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

    def test_fresh_proof_is_hard(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            self.assertEqual(interception_state(archive, "claude"), "HARD")

    def test_proof_from_a_prior_session_goes_stale_when_a_new_session_opens(self) -> None:
        with isolated_project() as (_project, archive):
            open_session(archive, "s1")
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            self.assertEqual(interception_state(archive, "claude"), "HARD")
            open_session(archive, "s2")
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

    def test_hook_uninstalled_after_proof_supersedes_it(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            archive.append("action", SUBJECT_UNINSTALLED, {"host": "claude"}, evidence=[])
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

    def test_probe_failed_after_proof_supersedes_it(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            archive.append("action", SUBJECT_PROBE_FAILED, {"host": "claude"}, evidence=[])
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

    def test_env_var_plays_no_role(self) -> None:
        # The whole defect this unit fixes: the sniff is gone, so exporting
        # the variable by hand must not fake anything, in either direction.
        with isolated_project() as (_project, archive):
            with mock.patch.dict(os.environ, {"GODMODE_PRETOOL_GATE": "1"}, clear=False):
                self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            environment = {k: v for k, v in os.environ.items() if k != "GODMODE_PRETOOL_GATE"}
            with mock.patch.dict(os.environ, environment, clear=True):
                self.assertEqual(interception_state(archive, "claude"), "HARD")


class HostCapabilitiesTests(unittest.TestCase):
    def test_no_interception_argument_is_unavailable(self) -> None:
        self.assertEqual(
            host_capabilities()["controls"]["tool_call_interception"], "UNAVAILABLE")

    def test_a_fresh_proofs_state_reports_hard(self) -> None:
        with isolated_project() as (_project, archive):
            with mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False):
                record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
                state = interception_state(archive, "claude")
                self.assertEqual(
                    host_capabilities(tool_call_interception=state)
                    ["controls"]["tool_call_interception"],
                    "HARD",
                )

    def test_env_var_alone_never_fakes_hard(self) -> None:
        with isolated_project() as (_project, archive):
            environment = {k: v for k, v in os.environ.items() if k != "GODMODE_PRETOOL_GATE"}
            environment["GODMODE_PRETOOL_GATE"] = "1"
            with mock.patch.dict(os.environ, environment, clear=True):
                state = interception_state(archive, "claude")
                self.assertEqual(
                    host_capabilities(tool_call_interception=state)
                    ["controls"]["tool_call_interception"],
                    "UNAVAILABLE",
                )


class ProbeMarkerHookTests(unittest.TestCase):
    """The real hook process: the probe marker is denied, and the denial IS the proof."""

    def _run(self, payload: dict, project: Path, state: Path,
             host: str = "claude") -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        environment["GODMODE_HOST"] = host
        return subprocess.run(
            [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
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

    def test_probe_marker_is_denied(self) -> None:
        with self._hosted() as (project, state, _archive):
            done = self._run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": f"{PROBE_PREFIX}abc123"}}, project, state)
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            decision = payload["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "deny")

    def test_probe_marker_denial_writes_the_proof_record(self) -> None:
        with self._hosted() as (project, state, archive):
            self._run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": f"{PROBE_PREFIX}nonce-xyz"}}, project, state)
            proof = last_proof(archive, "claude")
            self.assertIsNotNone(proof)
            self.assertEqual(proof["data"]["request_id"], "nonce-xyz")
            self.assertEqual(proof["data"]["tool"], "Bash")
            self.assertTrue(proof["data"]["proof"])
            self.assertEqual(interception_state(archive, "claude"), "HARD")

    def test_probe_marker_is_always_denied_regardless_of_staging(self) -> None:
        # A staged capability matches by exact operation text; since the
        # nonce changes every probe, nothing can pre-stage a pass on the
        # next one - but this locks the invariant directly rather than the
        # coincidence: the probe path never consults staged capabilities.
        with self._hosted() as (project, state, _archive):
            operation = f"{PROBE_PREFIX}nonce-cannot-be-staged"
            done = self._run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": operation}}, project, state)
            payload = json.loads(done.stdout)
            self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_probe_marker_reachable_via_bare_operation_too(self) -> None:
        # Host-neutral form: no tool_name, a bare operation string - the same
        # shape a non-Claude caller would send.
        with self._hosted() as (project, state, archive):
            done = self._run(
                {"operation": f"{PROBE_PREFIX}bare-op"}, project, state)
            self.assertEqual(done.returncode, 3, done.stdout)
            self.assertEqual(interception_state(archive, "claude"), "HARD")


class CLIHooksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-hookproof-cli-")
        self.project = Path(self._holder.name)
        self.state = self.project / "state"
        self._environment = dict(os.environ)
        os.environ["GODMODE_STATE_HOME"] = str(self.state)
        os.environ["GODMODE_HOST"] = "claude"
        done = subprocess.run(
            [sys.executable, str(GODMODE_CLI), "--project", str(self.project), "init"],
            capture_output=True, text=True, env=os.environ)
        assert done.returncode == 0, f"init failed: {done.stderr or done.stdout}"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environment)
        self._holder.cleanup()

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GODMODE_CLI), "--project", str(self.project), "--json", *args],
            capture_output=True, text=True, env=os.environ)

    def test_status_reports_unavailable_before_any_probe(self) -> None:
        done = self._cli("hooks", "status")
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        for field in ("plugin_installed", "session_hook_seen", "pretool_hook_seen",
                      "host_registration", "last_proof", "verdict"):
            self.assertIn(field, payload)
        self.assertEqual(payload["verdict"], "UNAVAILABLE")
        self.assertIsNone(payload["last_proof"])
        self.assertTrue(payload["plugin_installed"])
        self.assertTrue(payload["session_hook_seen"])
        self.assertTrue(payload["pretool_hook_seen"])

    def test_probe_flips_status_to_hard_and_exits_zero(self) -> None:
        probe = self._cli("hooks", "probe")
        self.assertEqual(probe.returncode, 0, probe.stderr or probe.stdout)
        probe_payload = json.loads(probe.stdout)
        self.assertTrue(probe_payload["denied"])
        self.assertTrue(probe_payload["proof_recorded"])
        self.assertEqual(probe_payload["state"], "HARD")

        status = self._cli("hooks", "status")
        self.assertEqual(status.returncode, 0, status.stderr)
        status_payload = json.loads(status.stdout)
        self.assertEqual(status_payload["verdict"], "HARD")
        self.assertIsNotNone(status_payload["last_proof"])

    def test_probe_on_an_uninitialized_project_fails_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fresh = Path(raw)
            done = subprocess.run(
                [sys.executable, str(GODMODE_CLI), "--project", str(fresh), "--json",
                 "hooks", "probe"],
                capture_output=True, text=True, env=os.environ)
            self.assertNotEqual(done.returncode, 0)


class RunProbeVerdictTests(unittest.TestCase):
    """Fix round 1, Critical-1: run_probe verdicts THIS attempt only.

    Reviewer's live repro, reproduced as a red test: a project already
    holding a valid, fresh proof from an earlier successful probe must not
    let that history answer for a probe attempt whose own denial was never
    observed.
    """

    def test_a_failed_probe_does_not_inherit_an_earlier_valid_proof(self) -> None:
        with isolated_project() as (project, archive):
            host = "claude"
            first = run_probe(project, archive, host)
            self.assertEqual(first["state"], "HARD")
            self.assertTrue(first["denied"])
            self.assertTrue(first["proof_recorded"])

            with mock.patch(
                "godmode_runtime.godmode_hookproof.subprocess.run",
                return_value=_no_denial_response(),
            ):
                second = run_probe(project, archive, host)

            self.assertFalse(second["denied"])
            self.assertFalse(second["proof_recorded"])
            # The binding constraint: state and exit code derive ONLY from
            # THIS attempt's denied/proof_recorded - never HARD here, no
            # matter what the prior proof said.
            self.assertNotEqual(second["state"], "HARD")
            self.assertEqual(second["state"], "UNAVAILABLE")
            # Historical context is visible in its own field, never folded
            # into this attempt's own verdict.
            self.assertIsNotNone(second["last_proof"])
            self.assertEqual(second["last_proof"]["data"]["request_id"], first["nonce"])

    def test_a_failed_probe_writes_a_probe_failed_record_and_downgrades_standing_state(
        self,
    ) -> None:
        with isolated_project() as (project, archive):
            host = "claude"
            run_probe(project, archive, host)
            self.assertEqual(interception_state(archive, host), "HARD")

            with mock.patch(
                "godmode_runtime.godmode_hookproof.subprocess.run",
                return_value=_no_denial_response(),
            ):
                run_probe(project, archive, host)

            failures = archive.select(kind="action", subject=SUBJECT_PROBE_FAILED, limit=10)
            self.assertEqual(len(failures), 1)
            # Required shipped behavior, not test-only: a silently-degraded
            # hook must flip the STANDING state too, so a later `hooks
            # status`/`capabilities` call (no new probe) also reads it.
            self.assertEqual(interception_state(archive, host), "UNAVAILABLE")

    def test_cmd_hooks_probe_exits_nonzero_on_a_failed_attempt_despite_prior_history(
        self,
    ) -> None:
        with isolated_project() as (project, archive):
            host = "claude"
            run_probe(project, archive, host)  # a real, valid, prior proof on record
            runtime = Runtime(anchor=archive.anchor, archive=archive)
            args = argparse.Namespace(hooks_command="probe", host=host)

            with mock.patch(
                "godmode_runtime.godmode_hookproof.subprocess.run",
                return_value=_no_denial_response(),
            ):
                result = cmd_hooks(args, runtime)

            self.assertNotEqual(result.exit_code, 0)
            self.assertNotEqual(result.payload["state"], "HARD")


class AutomaticSessionAnchorTests(unittest.TestCase):
    """Fix round 1, Critical-2: session-start writes a real freshness anchor.

    Reviewer's live repro: init, probe, status, capabilities over the
    shipped Claude Code hook lifecycle never wrote a `kind="session"`
    record, so `_session_anchor_sequence` was always 0 and every proof read
    as fresh forever. This drives the REAL `session-start` hook subprocess
    (not a direct function call) across two sessions and checks staleness
    actually occurs on the second.
    """

    def _session_start(self, project: Path, state: Path, host: str = "claude") -> None:
        environment = dict(os.environ)
        environment["GODMODE_STATE_HOME"] = str(state)
        environment["GODMODE_HOST"] = host
        done = subprocess.run(
            [sys.executable, str(HOOK), "session-start", "--project", str(project)],
            input=json.dumps({"hook_event_name": "SessionStart"}),
            capture_output=True, text=True, encoding="utf-8", timeout=60, env=environment,
        )
        self.assertEqual(done.returncode, 0, done.stderr)

    def _archive(self, project: Path, state: Path) -> Chronicle:
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            return Chronicle(resolve_anchor(project))

    def test_a_real_claude_session_lifecycle_writes_an_anchor_and_stales_a_prior_proof(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                Chronicle(resolve_anchor(project)).initialize()

            # Session 1: the automatic hook lifecycle an operator never
            # touches by hand - session-start, then a probe.
            self._session_start(project, state)
            archive = self._archive(project, state)
            anchors = archive.select(kind="action", subject=SUBJECT_ANCHOR, limit=10)
            self.assertEqual(len(anchors), 1)

            probe = subprocess.run(
                [sys.executable, str(GODMODE_CLI), "--project", str(project), "--json",
                 "hooks", "probe"],
                capture_output=True, text=True,
                env={**os.environ, "GODMODE_STATE_HOME": str(state), "GODMODE_HOST": "claude"})
            self.assertEqual(probe.returncode, 0, probe.stderr or probe.stdout)
            self.assertEqual(json.loads(probe.stdout)["state"], "HARD")
            self.assertEqual(interception_state(self._archive(project, state), "claude"), "HARD")

            # Session 2: a brand new Claude Code session opens. No new probe
            # runs - the proof is real, but it is now about a PRIOR
            # session's hook, not this one's.
            self._session_start(project, state)
            archive = self._archive(project, state)
            anchors = archive.select(kind="action", subject=SUBJECT_ANCHOR, limit=10)
            self.assertEqual(len(anchors), 2)
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

            status = subprocess.run(
                [sys.executable, str(GODMODE_CLI), "--project", str(project), "--json",
                 "hooks", "status"],
                capture_output=True, text=True,
                env={**os.environ, "GODMODE_STATE_HOME": str(state), "GODMODE_HOST": "claude"})
            self.assertEqual(json.loads(status.stdout)["verdict"], "UNAVAILABLE")


class SessionAnchorReconciliationTests(unittest.TestCase):
    """Fix round 1: the automatic anchor and `godmode session open` never fight."""

    def test_the_newer_of_either_anchor_kind_governs_freshness(self) -> None:
        with isolated_project() as (_project, archive):
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            self.assertEqual(interception_state(archive, "claude"), "HARD")

            record_session_anchor(archive, "claude")
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

            # The explicit CLI form, arriving after the automatic anchor,
            # must not resurrect the now-stale proof.
            open_session(archive, "explicit work session")
            self.assertEqual(interception_state(archive, "claude"), "UNAVAILABLE")

            # A fresh proof recorded after BOTH anchor kinds is HARD again,
            # regardless of which kind is newer.
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n2")
            self.assertEqual(interception_state(archive, "claude"), "HARD")


if __name__ == "__main__":
    unittest.main()
