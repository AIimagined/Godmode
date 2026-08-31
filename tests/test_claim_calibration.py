"""Calibration ledger: scored claims, resolutions, and the doctor summary.

A claim may declare how sure it is (`confidence`, 0..1). A later
resolution closes the loop with an outcome (`held` / `failed`) and its
own evidence, and the pair yields a calibration score: 1 - (confidence -
outcome)^2, where held is 1.0 and failed is 0.0. Perfectly-placed
confidence scores 1.0; full confidence on a claim that failed scores 0.

The ledger is append-only in both directions: a resolution names exactly
one claim, a claim resolves at most once, and a resolution is never
itself resolvable. `calibration_summary` reads the whole ledger for the
doctor: mean score, per-bucket error rates, and the standing debt of
scored claims never resolved. All honest-empty before any data exists.
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

from godmode_runtime.godmode_attest import (  # noqa: E402
    calibration_summary,
    record_claim,
    resolve_claim,
)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _scored_claim(archive, project, confidence, text="the fix holds"):
    return record_claim(
        archive, project, "S-test", text, "observed", confidence=confidence,
    )


class ConfidenceFieldTests(unittest.TestCase):
    def test_out_of_range_confidence_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for bad in (-0.1, 1.1, 7):
                with self.assertRaises(ArchiveError):
                    _scored_claim(archive, project, bad)

    def test_confidence_is_stored_and_defaults_to_none(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            scored = _scored_claim(archive, project, 0.8)
            self.assertEqual(scored["data"]["confidence"], 0.8)
            plain = record_claim(archive, project, "S-test", "plain", "observed")
            # Present-but-None, so a reader never guesses schema version.
            self.assertIsNone(plain["data"]["confidence"])

    def test_boundary_confidences_are_accepted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(_scored_claim(archive, project, 0.0)["data"]["confidence"], 0.0)
            self.assertEqual(_scored_claim(archive, project, 1.0)["data"]["confidence"], 1.0)


class ResolutionTests(unittest.TestCase):
    def test_resolving_a_missing_sequence_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                resolve_claim(archive, project, "S-test", 999, "held",
                              cites=["file:README.md"])

    def test_resolution_requires_evidence(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            claim = _scored_claim(archive, project, 0.9)
            with self.assertRaises(ArchiveError):
                resolve_claim(archive, project, "S-test", claim["sequence"],
                              "held", cites=[])

    def test_unknown_outcome_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            claim = _scored_claim(archive, project, 0.9)
            with self.assertRaises(ArchiveError):
                resolve_claim(archive, project, "S-test", claim["sequence"],
                              "maybe", cites=["file:README.md"])

    def test_score_math_held_and_failed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            held = resolve_claim(
                archive, project, "S-test",
                _scored_claim(archive, project, 0.9)["sequence"],
                "held", cites=["file:README.md"])
            self.assertAlmostEqual(held["data"]["score"], 0.99)
            failed = resolve_claim(
                archive, project, "S-test",
                _scored_claim(archive, project, 0.9)["sequence"],
                "failed", cites=["file:README.md"])
            self.assertAlmostEqual(failed["data"]["score"], 0.19)

    def test_a_claim_resolves_at_most_once(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            claim = _scored_claim(archive, project, 0.5)
            resolve_claim(archive, project, "S-test", claim["sequence"], "held",
                          cites=["file:README.md"])
            with self.assertRaises(ArchiveError):
                resolve_claim(archive, project, "S-test", claim["sequence"],
                              "failed", cites=["file:README.md"])

    def test_a_resolution_is_not_itself_resolvable(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            claim = _scored_claim(archive, project, 0.5)
            resolution = resolve_claim(archive, project, "S-test",
                                       claim["sequence"], "held",
                                       cites=["file:README.md"])
            with self.assertRaises(ArchiveError):
                resolve_claim(archive, project, "S-test",
                              resolution["sequence"], "held",
                              cites=["file:README.md"])

    def test_an_unscored_claim_resolves_with_no_score(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            claim = record_claim(archive, project, "S-test", "plain", "observed")
            resolution = resolve_claim(archive, project, "S-test",
                                       claim["sequence"], "held",
                                       cites=["file:README.md"])
            self.assertEqual(resolution["data"]["outcome"], "held")
            self.assertIsNone(resolution["data"]["score"])


class SummaryTests(unittest.TestCase):
    def test_empty_ledger_reads_honestly_empty(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            summary = calibration_summary(archive)
            self.assertEqual(summary["scored_resolved"], 0)
            self.assertEqual(summary["unresolved_scored"], 0)
            self.assertIn("no scored claims", summary["note"])

    def test_summary_counts_mean_and_debt(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            resolve_claim(archive, project, "S-test",
                          _scored_claim(archive, project, 0.9)["sequence"],
                          "held", cites=["file:README.md"])
            resolve_claim(archive, project, "S-test",
                          _scored_claim(archive, project, 0.9)["sequence"],
                          "failed", cites=["file:README.md"])
            debt = _scored_claim(archive, project, 0.7)  # never resolved
            summary = calibration_summary(archive)
            self.assertEqual(summary["scored_resolved"], 2)
            self.assertAlmostEqual(summary["mean_score"], (0.99 + 0.19) / 2)
            self.assertEqual(summary["unresolved_scored"], 1)
            self.assertEqual(summary["oldest_unresolved_seq"], debt["sequence"])

    def test_buckets_report_error_rate_per_confidence_band(self) -> None:
        # The tier map becomes auditable: each band reports how often its
        # claims failed, so a threshold is a measurement, not an aesthetic.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            for confidence, outcome in ((0.95, "held"), (0.9, "failed"),
                                        (0.3, "failed")):
                resolve_claim(archive, project, "S-test",
                              _scored_claim(archive, project, confidence)["sequence"],
                              outcome, cites=["file:README.md"])
            summary = calibration_summary(archive)
            bands = {band["band"]: band for band in summary["bands"]}
            high = bands["high"]      # confidence >= 0.8
            self.assertEqual(high["resolved"], 2)
            self.assertAlmostEqual(high["error_rate"], 0.5)
            low = bands["low"]        # confidence < 0.5
            self.assertEqual(low["resolved"], 1)
            self.assertAlmostEqual(low["error_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
