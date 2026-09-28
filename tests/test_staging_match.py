"""A staged approval matches its command with a redirect, a read filter or
a read beside it, and nothing else.

0.3.31 matched the staged text byte for byte, so `git push origin main >
push.log 2>&1` cost a second password. The normalised form is strict on
purpose: every row on the mismatch side names a way a looser rule would
have widened what one password buys.
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

from godmode_runtime.godmode_sentinel import CapabilityBroker, staging_core  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"
PUSH = "git push origin main"

MATCHES = [
    "git push origin main > push.log 2>&1",
    "git push origin main >> logs/push.txt",
    "git push origin main 2>&1 | tail -3",
    "git push origin main | grep -v remote",
    "git status && git push origin main",
    "git push origin main && git log --oneline -1",
    "git fetch -q && git push origin main; git status --short",
]
MISMATCHES = [
    "git push origin main --force",
    "git push origin main > /etc/motd",
    "git push origin main > ../outside.log",
    "git push origin main | sh",
    "git push origin main && rm -rf /",
    "cd ../other-repo && git push origin main",
    "git push origin main && git push --force origin main",
    "git push origin release",
]


class StagingCoreTests(unittest.TestCase):
    def test_the_core_of_a_matching_form_is_the_staged_command(self) -> None:
        for operation in MATCHES:
            with self.subTest(operation=operation):
                self.assertEqual(staging_core(operation, PLUGIN_ROOT), PUSH)

    def test_the_core_of_a_mismatching_form_is_not(self) -> None:
        for operation in MISMATCHES:
            with self.subTest(operation=operation):
                self.assertNotEqual(staging_core(operation, PLUGIN_ROOT), PUSH)


class StagedMatchTests(unittest.TestCase):
    def _broker(self, archive) -> CapabilityBroker:
        archive.initialize()
        broker = CapabilityBroker(archive)
        broker.configure(PASSWORD)
        return broker

    def test_a_matching_form_spends_the_staging_once(self) -> None:
        for operation in MATCHES:
            with self.subTest(operation=operation), \
                    isolated_project() as (_project, _state, _anchor, archive):
                broker = self._broker(archive)
                broker.stage(PUSH, PASSWORD)
                verdict = broker.consume_staged(operation)
                self.assertIsNotNone(verdict, operation)
                self.assertTrue(verdict["protected"])
                self.assertIsNone(broker.consume_staged(operation))

    def test_a_mismatching_form_leaves_the_staging_alone(self) -> None:
        for operation in MISMATCHES:
            with self.subTest(operation=operation), \
                    isolated_project() as (_project, _state, _anchor, archive):
                broker = self._broker(archive)
                broker.stage(PUSH, PASSWORD)
                self.assertIsNone(broker.consume_staged(operation), operation)
                self.assertIsNotNone(broker.consume_staged(PUSH))


if __name__ == "__main__":
    unittest.main()
