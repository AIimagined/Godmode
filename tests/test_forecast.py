"""B6-B: what would this cost, and what did today's policy do to yesterday?

Two questions over the same corpus. The archive holds every refusal the
gate ever produced - operation, tool, category and the tier it carried at
the time - which makes both answerable from evidence rather than from a
heuristic someone tuned by feel.

* **Forecast.** Before running something, say what it would be classified
  as *and* whether this project has met its shape before. A tier alone is
  a rule; a tier plus "this category was refused 44 times here" is a
  reason.
* **Replay.** Re-classify every operation the archive already holds under
  *today's* rules and compare against the tier recorded then. That is the
  only way to see what a policy change did to work already done.

The direction of drift is the point. A rule that got stricter is expected
- the ratchet only tightens. A rule that got *looser* means something that
would have been stopped once would now pass, which is the regression the
ratchet exists to prevent and must be reported separately rather than
averaged into a count of differences.
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

from godmode_runtime.godmode_forecast import (  # noqa: E402
    TIER_ORDER,
    forecast,
    replay,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _refusal(archive, operation: str, tier: str, category: str) -> None:
    archive.append("refusal", operation[:120], {
        "operation": operation, "tier": tier,
        "category": category, "tool": "Bash",
    })


class ForecastTests(unittest.TestCase):
    def test_a_dangerous_operation_forecasts_a_high_tier(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = forecast(archive, "git push --force origin main",
                              project_root=project)
            self.assertTrue(result["protected"])
            self.assertEqual(result["tier"], "R5")

    def test_precedent_counts_prior_refusals_of_the_same_category(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _refusal(archive, "git push --force origin main", "R5",
                     "git-history-or-remote")
            _refusal(archive, "git reset --hard HEAD~3", "R5",
                     "git-history-or-remote")
            _refusal(archive, "rm -rf build", "R4", "filesystem-mutation")
            result = forecast(archive, "git push --force origin other",
                              project_root=project)
            self.assertEqual(result["precedent"]["same_category"], 2)

    def test_a_harmless_operation_carries_no_alarm(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = forecast(archive, "git status", project_root=project)
            self.assertFalse(result["protected"])
            self.assertEqual(result["precedent"]["same_category"], 0)


class ReplayTests(unittest.TestCase):
    def test_an_unchanged_policy_reports_no_drift(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # Recorded with exactly what today's classifier answers, so any
            # drift reported here would be the check's own noise.
            result = forecast(archive, "git push --force origin main",
                              project_root=project)
            _refusal(archive, "git push --force origin main",
                     result["tier"], result["category"])
            report = replay(archive, project_root=project)
            self.assertEqual(report["drifted"], [])
            self.assertEqual(report["total"], 1)

    def test_a_loosened_rule_is_reported_as_relaxed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # Recorded as harmless once; today's classifier calls it R5. The
            # archive is the "then" side, so this reads as a tightening.
            _refusal(archive, "git push --force origin main", "R0",
                     "git-history-or-remote")
            report = replay(archive, project_root=project)
            self.assertEqual(len(report["tightened"]), 1)
            self.assertEqual(report["relaxed"], [])

    def test_a_tier_that_dropped_is_reported_as_relaxed(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # Recorded as maximal once; today's classifier finds nothing
            # protected, so a command once stopped would now pass.
            _refusal(archive, "git status", "R5", "git-history-or-remote")
            report = replay(archive, project_root=project)
            self.assertEqual(len(report["relaxed"]), 1)
            self.assertEqual(report["relaxed"][0]["then"]["tier"], "R5")

    def test_a_probe_sentinel_is_synthetic_not_a_relaxation(self) -> None:
        # `godmode hooks probe` records refusals whose "operation" is a
        # sentinel token, not a command. The plain classifier cannot rate a
        # token, so replaying one looks like a rule that went soft. Nine of
        # these sat in this project's own archive and were the entire
        # apparent relaxation. Counted apart, never as drift.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _refusal(archive, "godmode-probe:453e176392f44721", "R5",
                     "unrecognized-tool")
            report = replay(archive, project_root=project)
            self.assertEqual(report["relaxed"], [])
            self.assertEqual(len(report["synthetic"]), 1)

    def test_tiers_order_from_harmless_to_irreversible(self) -> None:
        self.assertLess(TIER_ORDER["R0"], TIER_ORDER["R5"])


if __name__ == "__main__":
    unittest.main()
