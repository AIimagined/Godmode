"""Every advisory charter rule owns a mechanical check or a stated reason.

`godmode assess` reported checkable_share 0.625 on this repo (3 of 8 rules
ADVISORY) - inspecting them showed all three are sentence-fragment
artifacts: GODMODE.md's descriptive prose wraps mid-sentence, and the
line-based directive scanner catches half-sentences containing words like
"require"/"never"/"before" that are not actionable rules at all. Writing a
new detection shape for them would be false enforcement (manufacturing a
verification method for prose that names no real directive) - the module's
own docstring warns against exactly this. The honest fix is `assess`
distinguishing "nobody has looked" from "reviewed, and here is why no check
applies", via `charter --review-advisory RULE_ID --reason "..."`.
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

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_assess import assess  # noqa: E402
from godmode_runtime.godmode_charter import compile_charter  # noqa: E402


class AdvisoryReviewTests(unittest.TestCase):
    def test_an_unreviewed_advisory_rule_is_unexplained(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            report = assess(project, budget=100_000, archive=archive)
        self.assertEqual(len(report["charter"]["advisory_unexplained"]), 1)

    def test_no_archive_leaves_every_advisory_rule_unexplained(self) -> None:
        # Backward compatible: archive is optional, and its absence must
        # not be misread as "reviewed" - that would silently hide the gap.
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            report = assess(project, budget=100_000)
        self.assertEqual(len(report["charter"]["advisory_unexplained"]), 1)

    def test_a_reviewed_rule_is_no_longer_unexplained(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            charter = compile_charter(project)
            rule_id = charter["compiled"][0]["id"]
            archive.append("decision", f"charter-advisory-reviewed:{rule_id}",
                           {"reason": "subjective aesthetic judgement; no mechanical "
                                     "check can decide 'feels premium'"}, evidence=[])
            report = assess(project, budget=100_000, archive=archive)
        self.assertEqual(report["charter"]["advisory_unexplained"], [])

    def test_a_review_with_no_reason_is_ignored(self) -> None:
        # An empty reason is not a reason; a rule "reviewed" with nothing
        # said is still unexplained, or the gate is satisfied by silence.
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Feel\n- The interface must feel premium.\n", encoding="utf-8")
            charter = compile_charter(project)
            rule_id = charter["compiled"][0]["id"]
            archive.append("decision", f"charter-advisory-reviewed:{rule_id}",
                           {"reason": "   "}, evidence=[])
            report = assess(project, budget=100_000, archive=archive)
        self.assertEqual(len(report["charter"]["advisory_unexplained"]), 1)

class PlantCoverageTests(unittest.TestCase):
    """A HARD rule with no plant on record has never been seen to fail.

    Matches plant_and_observe's real shape: an attestation with subject
    `guard:<name>`, status "ran" when the green-red-green sequence proved
    out, and `data.rule_ids` naming which HARD rules it covers. Archive-wide
    (not session-scoped, unlike gate()'s attested_rule_ids) - this is a
    lifetime structural fact about the guard mechanism, not a per-session
    freshness requirement.
    """

    def test_a_hard_rule_with_no_plant_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8")
            report = assess(project, budget=100_000, archive=archive)
            charter = compile_charter(project)
            hard_ids = {r["id"] for r in charter["compiled"] if r["enforcement"] == "HARD"}
            self.assertTrue(hard_ids)
            self.assertEqual(set(report["charter"]["hard_unplanted"]), hard_ids)

    def test_a_proven_plant_clears_the_rule(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8")
            charter = compile_charter(project)
            rule_id = charter["compiled"][0]["id"]
            archive.append(
                "attestation", "guard:ask-before-commit",
                {"session": "S-x", "status": "ran", "rule_ids": [rule_id],
                 "result": "observed failing: green(0) -> red(1) -> green(0)"},
                evidence=["cmd:pytest", "file:tests/test_ask.py"])
            report = assess(project, budget=100_000, archive=archive)
        self.assertNotIn(rule_id, report["charter"]["hard_unplanted"])

    def test_a_blocked_plant_does_not_clear_the_rule(self) -> None:
        # status="blocked" means the sequence did NOT prove out (never went
        # red, or didn't return to green) - it must not count as a plant.
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8")
            charter = compile_charter(project)
            rule_id = charter["compiled"][0]["id"]
            archive.append(
                "attestation", "guard:ask-before-commit",
                {"session": "S-x", "status": "blocked", "rule_ids": [rule_id],
                 "result": "not observed failing: baseline=0 planted=0 restored=0",
                 "reason": "guard did not fail against a planted violation"},
                evidence=["cmd:pytest", "file:tests/test_ask.py"])
            report = assess(project, budget=100_000, archive=archive)
        self.assertIn(rule_id, report["charter"]["hard_unplanted"])

    def test_no_archive_names_every_hard_rule(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "GODMODE.md").write_text(
                "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8")
            report = assess(project, budget=100_000)
            charter = compile_charter(project)
            hard_ids = {r["id"] for r in charter["compiled"] if r["enforcement"] == "HARD"}
            self.assertEqual(set(report["charter"]["hard_unplanted"]), hard_ids)


class AdvisoryReviewRepoTests(unittest.TestCase):
    def test_this_repos_own_advisory_rules_are_now_all_reviewed(self) -> None:
        # Closing the loop, not just building the mechanism: this repo's
        # own 3 advisory rules (found live via `godmode charter --full`)
        # must actually carry review decisions, or the checkability work
        # is infrastructure nobody used on the one project it was built for.
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        anchor = resolve_anchor(PLUGIN_ROOT)
        archive = Chronicle(anchor)
        report = assess(PLUGIN_ROOT, budget=100_000, archive=archive)
        self.assertEqual(
            report["charter"]["advisory_unexplained"], [],
            "this repo's own advisory charter rules are not fully reviewed")


if __name__ == "__main__":
    unittest.main()
