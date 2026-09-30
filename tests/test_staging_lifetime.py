"""A staged approval outlives a suite run and dies with the commit.

One release cost nine password rounds because every approval expired in 300
seconds while a suite or CI ran. The clock was never what made a staging
safe: it is bound to the exact operation, the repository, the worktree,
HEAD and the branch, and it is spent once. This module pins the three
properties that replace the short clock.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime import godmode_sentinel  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"
PUSH = "git push origin main"


def _broker(archive) -> CapabilityBroker:
    archive.initialize()
    broker = CapabilityBroker(archive)
    broker.configure(PASSWORD)
    return broker


class StagingLifetimeTests(unittest.TestCase):
    def test_a_staging_survives_a_forty_minute_wait(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            broker = _broker(archive)
            start = 1_800_000_000
            with mock.patch.object(godmode_sentinel.time, "time", return_value=start):
                broker.stage(PUSH, PASSWORD)
            with mock.patch.object(godmode_sentinel.time, "time", return_value=start + 40 * 60):
                self.assertIsNotNone(broker.consume_staged(PUSH))

    def test_a_staging_dies_after_twelve_hours(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            broker = _broker(archive)
            start = 1_800_000_000
            with mock.patch.object(godmode_sentinel.time, "time", return_value=start):
                broker.stage(PUSH, PASSWORD)
            with mock.patch.object(godmode_sentinel.time, "time",
                                   return_value=start + 12 * 3600 + 1):
                self.assertIsNone(broker.consume_staged(PUSH))

    def test_a_new_commit_invalidates_the_staging(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            broker = _broker(archive)
            before = dict(broker._mint_context(), head="a" * 40)
            after = dict(before, head="b" * 40)
            with mock.patch.object(broker, "_mint_context", return_value=before):
                broker.stage(PUSH, PASSWORD)
            with mock.patch.object(broker, "_mint_context", return_value=after):
                self.assertIsNone(broker.consume_staged(PUSH))
            # Spent on the failed attempt: not retried against the old HEAD either.
            with mock.patch.object(broker, "_mint_context", return_value=before):
                self.assertIsNone(broker.consume_staged(PUSH))

    def test_a_staging_is_spent_once(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            broker = _broker(archive)
            broker.stage(PUSH, PASSWORD)
            self.assertIsNotNone(broker.consume_staged(PUSH))
            self.assertIsNone(broker.consume_staged(PUSH))


if __name__ == "__main__":
    unittest.main()
