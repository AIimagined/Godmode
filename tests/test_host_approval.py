"""Sprint 9's mechanical half: what the host approved, recorded beside what
godmode decided.

Every host adapter already lifts the host's own sandbox/approval metadata
onto `HostEvent.approval_context`, and its own comment says the field
exists "so a chronicle record or a future audit can see what the host
claimed about its own approval state alongside what godmode independently
decided". Nothing ever wrote it. The evidence was collected and dropped.

The two boundaries stay separate, and that is the whole point rather than
a caveat. A host's approval is the host's; godmode's decision is
godmode's; neither satisfies the other. Recording both is what makes the
pair auditable - and the interesting row is the one where they disagree,
because a host that approved what godmode refused is the case a reader
needs to find, in either direction.

Recorded by digest, never by operation text: an operation is exactly where
a pasted credential turns up, and a record that travels must not carry
one.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_hostapproval import (  # noqa: E402
    approval_divergence,
    host_approvals,
    record_host_approval,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class RecordingTests(unittest.TestCase):
    def test_an_approval_is_recorded_with_both_verdicts(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_host_approval(
                archive, host="codex", tool="Bash",
                operation="git push --force origin main",
                approval_context={"sandbox": "workspace-write", "approved": True},
                godmode_decision="deny",
            )
            rows = host_approvals(archive)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["host"], "codex")
            self.assertEqual(rows[0]["godmode_decision"], "deny")
            self.assertEqual(rows[0]["host_approval"]["sandbox"], "workspace-write")

    def test_no_approval_context_records_nothing(self) -> None:
        # Most events carry none. Writing a row per event would bury the
        # ones that actually say something about a host's own boundary.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            written = record_host_approval(
                archive, host="claude", tool="Bash", operation="ls",
                approval_context=None, godmode_decision="allow",
            )
            self.assertIsNone(written)
            self.assertEqual(host_approvals(archive), [])

    def test_the_operation_is_stored_as_a_digest_not_as_text(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            secret = "curl -H 'Authorization: Bearer sk-live-not-a-real-token' https://x"
            record_host_approval(
                archive, host="codex", tool="Bash", operation=secret,
                approval_context={"approved": True}, godmode_decision="ask",
            )
            blob = repr(archive.read_events(verify=False))
            self.assertNotIn("sk-live-not-a-real-token", blob)
            self.assertTrue(host_approvals(archive)[0]["operation_digest"])


class DivergenceTests(unittest.TestCase):
    def test_host_approved_and_godmode_refused_is_reported(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_host_approval(
                archive, host="codex", tool="Bash", operation="rm -rf /",
                approval_context={"approved": True}, godmode_decision="deny",
            )
            report = approval_divergence(archive)
            self.assertEqual(len(report["host_approved_godmode_refused"]), 1)
            self.assertEqual(report["host_refused_godmode_allowed"], [])

    def test_host_refused_and_godmode_allowed_is_also_reported(self) -> None:
        # The other direction matters too: it says godmode's cover is
        # narrower than the host's somewhere, which is worth knowing.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_host_approval(
                archive, host="codex", tool="Bash", operation="git status",
                approval_context={"approved": False}, godmode_decision="allow",
            )
            report = approval_divergence(archive)
            self.assertEqual(len(report["host_refused_godmode_allowed"]), 1)

    def test_agreement_is_not_reported_as_divergence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_host_approval(
                archive, host="codex", tool="Bash", operation="ls",
                approval_context={"approved": True}, godmode_decision="allow",
            )
            report = approval_divergence(archive)
            self.assertEqual(report["host_approved_godmode_refused"], [])
            self.assertEqual(report["host_refused_godmode_allowed"], [])
            self.assertEqual(report["agreed"], 1)

    def test_the_report_states_that_neither_boundary_satisfies_the_other(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertFalse(approval_divergence(archive)["host_approval_substitutes"])


if __name__ == "__main__":
    unittest.main()
