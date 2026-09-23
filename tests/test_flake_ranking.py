"""Retries are recorded and ranked; a frequent flake without a lesson is a finding."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_preflight  # noqa: E402
from godmode_runtime.godmode_trends import trends_report  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class FlakeRankingTests(unittest.TestCase):
    def test_ranked_and_finding(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for _ in range(3):
                archive.append("action", "flaky-retry", {"test_id": "tests.test_x.T.test_a", "outcome": "passed-isolated", "operation": "flake:tests.test_x.T.test_a"})
            archive.append("action", "flaky-retry", {"test_id": "tests.test_y.T.test_b", "outcome": "passed-isolated", "operation": "flake:tests.test_y.T.test_b"})
            rows = trends_report(archive, sessions=5)["flakes"]
            self.assertEqual(rows[0]["test_id"], "tests.test_x.T.test_a")
            self.assertEqual(rows[0]["retries"], 3)
            findings = godmode_preflight.flake_findings(archive)
            self.assertEqual([f["check"] for f in findings], ["flake-without-lesson"])

    def test_lesson_clears_the_finding(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for _ in range(3):
                archive.append("action", "flaky-retry", {"test_id": "tests.test_x.T.test_a", "outcome": "passed-isolated", "operation": "flake:tests.test_x.T.test_a"})
            archive.append("lesson", "tests.test_x.T.test_a flakes under batch load", {"status": "active", "value": "load signature", "generalized_guard": "run isolated"})
            self.assertEqual(godmode_preflight.flake_findings(archive), [])

    # Final review S4: `flakes()`'s lesson lookup used to route through
    # `archive.select(kind="lesson", limit=500)`, which clamps to the
    # newest 500 lesson records regardless of what is asked for. A lesson
    # naming a flake written more than 500 lessons ago used to read as
    # absent, and `flake_findings` would raise a false `flake-without-lesson`
    # an operator cannot fix by adding a lesson that is already there.
    def test_lesson_past_500_records_still_clears_the_finding(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("lesson", "tests.test_x.T.test_a flakes under batch load",
                            {"status": "active", "value": "load signature",
                             "generalized_guard": "run isolated"})
            for i in range(520):
                archive.append("lesson", f"unrelated lesson {i}",
                                {"status": "active", "value": f"filler {i}",
                                 "generalized_guard": "n/a"})
            for _ in range(3):
                archive.append("action", "flaky-retry", {
                    "test_id": "tests.test_x.T.test_a", "outcome": "passed-isolated",
                    "operation": "flake:tests.test_x.T.test_a"})
            self.assertEqual(godmode_preflight.flake_findings(archive), [])


if __name__ == "__main__":
    unittest.main()
