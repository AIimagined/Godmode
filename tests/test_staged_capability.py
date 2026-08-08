"""A refusal an operator can answer, without disabling the guard.

The gate refused and named a remedy that did not exist: no host tool call
carries a field a capability could travel in, so the broker was unreachable from
the hook and the only available response was to switch the plugin off. That
happened six times in one session, which is the honest measurement of what a
total refusal costs.

The broker was never the missing part. Its token binds to an exact operation,
is password-issued, expires, and burns on use. What was missing is a place the
hook can read it from.

Staging puts the token in the archive's own state directory, which sits under
the git metadata directory rather than in the working tree — so a cloned
repository cannot ship one, which is the disarming this gate exists to notice.
Every other property is inherited unchanged: an operator with the password
authorises one exact command, once, for a short window.
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

from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"
PUSH = "git push origin main"


class StagingTests(unittest.TestCase):
    def test_a_staged_capability_lets_the_hook_permit_that_operation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            verdict = broker.consume_staged(PUSH)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict["category"], "git-history-or-remote")

    def test_without_staging_the_hook_finds_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            self.assertIsNone(broker.consume_staged(PUSH))

    def test_staging_requires_the_password(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with self.assertRaises(AuthorizationError):
                broker.stage(PUSH, "not the password")


class BindingTests(unittest.TestCase):
    """Every property the token already had, kept."""

    def test_a_staged_capability_permits_only_the_exact_operation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            self.assertIsNone(broker.consume_staged("git push --force origin main"))
            self.assertIsNone(broker.consume_staged("rm -rf build"))
            # The one it was issued for still works.
            self.assertIsNotNone(broker.consume_staged(PUSH))

    def test_a_staged_capability_is_spent_once(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            self.assertIsNotNone(broker.consume_staged(PUSH))
            self.assertIsNone(broker.consume_staged(PUSH),
                              "a spent capability was accepted a second time")

    def test_an_expired_capability_is_not_accepted(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD, ttl_seconds=10)
            data = broker._load()
            for entry in data["staged"]:
                entry["expires_at"] = 0
            broker._store(data)
            self.assertIsNone(broker.consume_staged(PUSH))

    def test_staging_a_read_only_operation_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with self.assertRaises(AuthorizationError):
                broker.stage("ls", PASSWORD)


class LocationTests(unittest.TestCase):
    def test_staged_state_is_not_in_the_working_tree(self) -> None:
        """A repository that could carry a grant could carry one for anything."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            try:
                broker.path.relative_to(Path(project))
            except ValueError:
                return  # outside the project entirely: correct
            self.assertIn(".git", broker.path.parts,
                          "a clone would carry the operator's authorization")


class RecordTests(unittest.TestCase):
    def test_consuming_a_staged_capability_is_recorded(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            broker.consume_staged(PUSH)
            kinds = [r["subject"] for r in archive.select(kind="action", limit=50)]
        self.assertIn("capability-consumed", kinds)


if __name__ == "__main__":
    unittest.main()
