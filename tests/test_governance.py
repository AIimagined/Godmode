"""Sprint 8: governance derived from what actually happened here.

The pivot's thesis is that godmode should stop shipping generic frames and
start proposing this project's rules from its own record. Every input
already exists - refusals with categories, recurring obligations, repeated
asks - and the promotion target already ships, since the charter compiles
and enforces rules. The pivot adds a synthesizer, not a subsystem.

The plan's three guardrails are not preferences, so they are what these
tests pin hardest:

1. **Propose, never install.** A candidate lives in a review surface. It
   never reaches the active charter without a person promoting it, and the
   synthesizer has no path that writes one.
2. **Tighten-only.** A synthesized rule may add an obligation, never relax
   one. Loosening stays a manual, chronicled act.
3. **Provenance and expiry.** Every candidate carries the records that
   support it, how many, and over what window - and says when its own
   evidence has gone stale rather than silently standing on it.

The fourth property is the one the brainstorm agenda worried about:
approval fatigue is evidence of tolerance, not of correctness. Frequency
alone must not mint a rule, so a candidate states its evidence and lets a
person judge it rather than presenting a count as a verdict.
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

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_governance import (  # noqa: E402
    MIN_OBSERVATIONS,
    candidates,
    governance_report,
    promote,
    promoted_rules,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _refusals(archive, operation: str, category: str, tier: str,
              times: int = 1) -> None:
    for index in range(times):
        archive.append("refusal", f"{operation} #{index}", {
            "operation": f"{operation} {index}", "tier": tier,
            "category": category, "tool": "Bash",
        })


class SynthesisTests(unittest.TestCase):
    def test_a_repeated_category_becomes_a_candidate(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "git push --force", "git-history-or-remote",
                      "R5", times=MIN_OBSERVATIONS["protected-category"])
            found = candidates(archive)
            self.assertTrue(
                any(c["category"] == "git-history-or-remote" for c in found))

    def test_thin_evidence_does_not_mint_a_rule(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "git push --force", "git-history-or-remote",
                      "R5", times=1)
            self.assertEqual(candidates(archive), [])

    def test_every_candidate_carries_its_provenance(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            candidate = candidates(archive)[0]
            self.assertTrue(candidate["citations"])
            self.assertGreaterEqual(
                candidate["observations"], MIN_OBSERVATIONS["protected-category"])
            self.assertIn("first_seen", candidate)
            self.assertIn("last_seen", candidate)

    def test_a_candidate_id_is_stable_across_reads(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            self.assertEqual(candidates(archive)[0]["id"],
                             candidates(archive)[0]["id"])


class GuardrailTests(unittest.TestCase):
    def test_synthesis_never_writes_to_the_archive(self) -> None:
        # Propose, never install: reading candidates must not itself be a
        # write, or the review surface becomes the enforcement surface.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            before = len(archive.read_events(verify=False))
            candidates(archive)
            governance_report(archive)
            self.assertEqual(len(archive.read_events(verify=False)), before)

    def test_a_candidate_only_ever_adds_an_obligation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            for candidate in candidates(archive):
                self.assertEqual(candidate["direction"], "tighten")

    def test_promotion_is_explicit_and_recorded(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            candidate = candidates(archive)[0]
            promote(archive, candidate["id"], reason="reviewed and agreed")
            self.assertIn(candidate["id"], promoted_rules(archive))

    def test_promoting_an_unknown_candidate_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                promote(archive, "nonexistent-candidate", reason="no")

    def test_a_promoted_candidate_stops_being_proposed(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusals(archive, "rm -rf", "filesystem-mutation", "R4",
                      times=MIN_OBSERVATIONS["protected-category"])
            candidate = candidates(archive)[0]
            promote(archive, candidate["id"], reason="agreed")
            self.assertNotIn(candidate["id"],
                             [c["id"] for c in candidates(archive)])


class ReportTests(unittest.TestCase):
    def test_the_report_states_that_nothing_was_installed(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            report = governance_report(archive)
            self.assertFalse(report["installed"])

    def test_an_empty_archive_proposes_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertEqual(governance_report(archive)["candidates"], [])


if __name__ == "__main__":
    unittest.main()
