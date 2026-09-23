"""A host with no live proof must cite what it replicates, or what it still
has to read.

The old finding knew two states: live proof or nothing. A host whose
hook path is replicated from an implementation read at code level, and
pinned by a test, is not on paper - it is proven by replication and
awaits a live confirmation.
"""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime import godmode_reach  # noqa: E402


class FakeArchive:
    def read_events(self):
        return []


class ReachReferenceTests(unittest.TestCase):
    def test_blocking_without_reference(self) -> None:
        with unittest.mock.patch.object(godmode_reach, "unverifiable_hosts", return_value=["cursor"]), \
             unittest.mock.patch.object(godmode_reach, "reach_metadata", return_value={"cursor": {}}):
            finding = godmode_reach.reach_finding(FakeArchive())
        self.assertEqual(finding["severity"], "blocking")
        self.assertIn("cursor", finding["detail"])

    def test_advisory_with_reference_and_test(self) -> None:
        meta = {"cursor": {"reference": "ledger:207",
                            "replication_test": "tests.test_launcher_root_fallback.LauncherTests.test_posix_root_without_variable",
                            "next_probe": "2026-10-01"}}
        with unittest.mock.patch.object(godmode_reach, "unverifiable_hosts", return_value=["cursor"]), \
             unittest.mock.patch.object(godmode_reach, "reach_metadata", return_value=meta):
            finding = godmode_reach.reach_finding(FakeArchive())
        self.assertEqual(finding["severity"], "advisory")

    def test_no_unverifiable_no_finding(self) -> None:
        with unittest.mock.patch.object(godmode_reach, "unverifiable_hosts", return_value=[]):
            self.assertIsNone(godmode_reach.reach_finding(FakeArchive()))


if __name__ == "__main__":
    unittest.main()
