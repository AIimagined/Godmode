"""Two rules absorbed 2026-09-11 from a multi-agent workspace's
incident-derived review checklist.

A negative over a window is a negative over that window only: "no
exploitation in 48h" was really three hours of retained logs. An absence
claim whose text or cited search names a window carries an advisory that
asks for the store's actual extent.

Deleting a branch auto-closes every open pull request based on it and
the merge UI does not say so; the branch-deletion preview names the
check to run first, without any network call from the classifier.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_attest import absence_window_advisory, record_claim  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class WindowedAbsenceTests(unittest.TestCase):
    def test_a_window_in_the_claim_or_its_search_is_named(self) -> None:
        self.assertIn("last 500", absence_window_advisory(
            "the local database holds no error rows (last 500, any age)", []))
        self.assertIn("--since", absence_window_advisory(
            "no exploitation is present", ["cmd:grep -c token access.log --since=48h"]))
        self.assertIsNone(absence_window_advisory("no network dependency exists", ["cmd:godmode sbom --gate"]))

    def test_the_recorded_claim_carries_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_claim(archive, project, "s", "no error rows in the last 7 days", "observed")
        self.assertTrue(any("window" in a for a in record["data"].get("advisories", [])), record["data"])


class BranchDeletionTests(unittest.TestCase):
    def test_the_preview_names_the_pull_requests_a_deletion_closes(self) -> None:
        verdict = classify_action("git branch -D feature/threading")
        self.assertEqual(verdict["category"], "git-branch-mutation")
        self.assertTrue(any("gh pr list --base feature/threading" in i for i in verdict["impact"]), verdict)


if __name__ == "__main__":
    unittest.main()
