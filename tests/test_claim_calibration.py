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


class ForecastAdvisoryTests(unittest.TestCase):
    """S13-B: the advisory fires only from RESOLVED records, never from
    open predictions, and only once enough of them exist to mean anything."""

    def _resolve_n(self, archive, project, pairs):
        (project / "README.md").write_text("x", encoding="utf-8")
        for confidence, outcome in pairs:
            resolve_claim(archive, project, "S-test",
                          _scored_claim(archive, project, confidence)["sequence"],
                          outcome, cites=["file:README.md"])

    def test_no_advisory_below_the_sample_floor(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._resolve_n(archive, project, [(0.9, "failed")] * 2)
            self.assertEqual(calibration_summary(archive).get("advisory"), None)

    def test_advisory_names_the_records_it_derives_from(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._resolve_n(archive, project, [(0.9, "failed")] * 3)
            advisory = calibration_summary(archive)["advisory"]
            self.assertIn("seq:", advisory)
            self.assertIn("calibration", advisory)

    def test_well_calibrated_records_stay_silent(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._resolve_n(archive, project, [(0.9, "held")] * 4)
            self.assertEqual(calibration_summary(archive).get("advisory"), None)

    def test_open_predictions_never_trigger_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for _ in range(6):
                _scored_claim(archive, project, 0.9)
            self.assertEqual(calibration_summary(archive).get("advisory"), None)


class SupersededOutcomeTests(unittest.TestCase):
    """A claim that was true and later got improved upon is not a failure.

    The disposition vocabulary gains `superseded`: the claim HELD at its
    time (scores as held - the confidence was justified), and the state
    is recorded distinctly so a later reader never mistakes replacement
    for reversal. The fix-loop wire counts failed resolutions only;
    superseding a claim must never arm it.
    """

    def test_superseded_scores_as_held_and_keeps_its_name(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim, resolve_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record = record_claim(
                archive, project, "S", "the old ranking beat the baseline",
                "observed", cites=["file:README.md"], confidence=0.8)
            resolution = resolve_claim(
                archive, project, "S", record["sequence"], "superseded",
                cites=["file:README.md"])
            data = resolution["data"] if "data" in resolution else resolution
            self.assertEqual(data.get("outcome"), "superseded")
            self.assertAlmostEqual(data.get("score"), 1 - (0.8 - 1.0) ** 2)


class AttestationFingerprintTests(unittest.TestCase):
    """An attestation names the tree state it attested (obligation
    attestation-fingerprint-staleness, bounded form).

    Which FILES a check covered is not always knowable, so the fingerprint
    is the honest coarser thing: HEAD and the dirty count at attestation
    time. A later reader comparing against the current tree can tell "this
    green predates your edits" - the staleness signal the study's receipt
    pattern exists for - without the record ever claiming file coverage it
    cannot prove.
    """

    def test_record_step_carries_the_worktree_fingerprint(self) -> None:
        import subprocess
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_step
        with isolated_project() as (project, _s, _a, archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.invalid"],
                           cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "t"],
                           cwd=project, check=True)
            (project / "a.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=project,
                           check=True)
            record = record_step(archive, "S", "unit suite", "ran",
                                 result="green", project=project)
            fingerprint = record["data"]["worktree"]
            self.assertEqual(len(fingerprint["head"]), 12)
            self.assertEqual(fingerprint["dirty"], 0)

    def test_no_project_is_a_stated_gap_not_a_crash(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_step
        with isolated_project() as (_p, _s, _a, archive):
            record = record_step(archive, "S", "unit suite", "ran")
            self.assertNotIn("worktree", record["data"])


class AsymmetricScoreTests(unittest.TestCase):
    """Loss-averse calibration, ADDITIVE: overconfident failure costs more
    than underconfident holding saves (lambda 2.25 on the failure side).
    The symmetric score is untouched - history stays comparable - and the
    asymmetric reading rides beside it as its own field.
    """

    def test_failure_is_penalized_harder_than_symmetric(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim, resolve_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record = record_claim(archive, project, "S", "the risky bet holds",
                                  "observed", cites=["file:README.md"],
                                  confidence=0.9)
            resolution = resolve_claim(archive, project, "S",
                                       record["sequence"], "failed",
                                       cites=["file:README.md"])
            data = resolution.get("data", resolution)
            self.assertAlmostEqual(data["score"], 1 - 0.9 ** 2, places=4)
            self.assertAlmostEqual(data["asymmetric_score"],
                                   1 - 2.25 * (0.9 ** 2), places=4)

    def test_held_matches_the_symmetric_score(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim, resolve_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record = record_claim(archive, project, "S", "the safe bet holds",
                                  "observed", cites=["file:README.md"],
                                  confidence=0.7)
            resolution = resolve_claim(archive, project, "S",
                                       record["sequence"], "held",
                                       cites=["file:README.md"])
            data = resolution.get("data", resolution)
            self.assertAlmostEqual(data["asymmetric_score"], data["score"],
                                   places=6)


class NumericContradictionTests(unittest.TestCase):
    """S18: the ledger preserves fed errors faithfully - a wrong quantity
    in a checkpoint outlived the measurement that killed it, and nothing
    fired. The conservative pre-write advisory: a claim carrying a bare
    number, recorded over a recent claim on the same subject carrying a
    DIFFERENT number, names the disagreement at write time - flag, never
    block, because the new number is usually the correction."""

    def test_a_conflicting_quantity_draws_the_advisory(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S",
                         "the parser suite covers 39 scenario pairs today",
                         "observed", cites=["file:README.md"])
            second = record_claim(archive, project, "S",
                                  "the parser suite covers 31 scenario pairs today",
                                  "observed", cites=["file:README.md"])
            advisories = second.get("data", second).get("advisories", [])
            self.assertTrue(any("39" in a and "31" in a for a in advisories),
                            advisories)

    def test_matching_quantities_stay_silent(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S",
                         "the parser suite covers 39 scenario pairs today",
                         "observed", cites=["file:README.md"])
            second = record_claim(archive, project, "S",
                                  "the parser suite covers 39 scenario pairs today",
                                  "observed", cites=["file:README.md"])
            advisories = second.get("data", second).get("advisories", [])
            self.assertFalse(any("disagree" in a for a in advisories))

    def test_different_subjects_never_compare(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S",
                         "the lexer benchmark holds 39 fixtures",
                         "observed", cites=["file:README.md"])
            second = record_claim(archive, project, "S",
                                  "the deploy window spans 31 minutes",
                                  "observed", cites=["file:README.md"])
            advisories = second.get("data", second).get("advisories", [])
            self.assertFalse(any("disagree" in a for a in advisories))


class UnbackedCommandCiteTests(unittest.TestCase):
    """Field report 2026-09-02: an observed-grade claim citing a command that
    was never attested recorded clean - the grade silently read as checked."""

    def test_observed_claim_with_unattested_cmd_is_named(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_claim(
                archive, project, "S", "the suite is green across all modules",
                "observed", cites=["cmd:python -m unittest discover"])
            advisories = record.get("data", record).get("advisories", [])
            self.assertTrue(any("no attestation behind" in a
                                for a in advisories), advisories)
            self.assertEqual(record.get("data", record).get("grade"),
                             "observed")

    def test_attested_cmd_cite_stays_clean(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_attest import record_claim, run_check
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            outcome = run_check(archive, "S", project, "truthy",
                                ["python", "-c", "print('ok')"])
            record = record_claim(
                archive, project, "S", "the probe printed ok",
                "observed", cites=[outcome["citation"]])
            advisories = record.get("data", record).get("advisories", [])
            self.assertFalse(any("no attestation" in a for a in advisories),
                             advisories)


class SweepDepthTests(unittest.TestCase):
    """Operator challenge 2026-09-03: sweep verdicts were recorded from
    README reads with nothing naming the depth. The verdict class now
    demands either a cited source read or a declared reading depth."""

    def _claim(self, archive, project, text, cites):
        from godmode_runtime.godmode_attest import record_claim
        record = record_claim(archive, project, "S", text, "observed",
                              cites=cites)
        return record.get("data", record).get("advisories", [])

    def test_verdict_without_source_read_is_named(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._claim(
                archive, project,
                "the upstream repo is swept and filed nil-build with two corroborations",
                ["file:README.md"])
            self.assertTrue(any("reading depth" in a for a in advisories),
                            advisories)

    def test_cited_source_file_is_clean(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._claim(
                archive, project,
                "the upstream repo is swept and filed nil-build after a code read",
                ["url:upstream/blob/main/hooks/session-start.sh",
                 "file:README.md"])
            self.assertFalse(any("reading depth" in a for a in advisories),
                             advisories)

    def test_declared_depth_is_clean(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._claim(
                archive, project,
                "the upstream repo is swept and filed nil-build, README-level: "
                "it is out of our lane entirely",
                ["file:README.md"])
            self.assertFalse(any("reading depth" in a for a in advisories),
                             advisories)


class FalsifierAdvisoryTests(unittest.TestCase):
    """A theory nothing could kill is a story, not a finding - a
    hypothesis names its falsifier or the gap is named."""

    def _record(self, archive, project, **kw):
        from godmode_runtime.godmode_attest import record_claim
        record = record_claim(archive, project, "S",
                              kw.pop("text"), kw.pop("grade"), **kw)
        return record.get("data", record).get("advisories", [])

    def test_bare_hypothesis_is_named(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._record(
                archive, project,
                text="the cache is probably dropping the second write",
                grade="hypothesis")
            self.assertTrue(any("falsifier" in a for a in advisories),
                            advisories)

    def test_refuted_by_is_clean(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._record(
                archive, project,
                text="the cache is probably dropping the second write",
                grade="hypothesis",
                refuted_by="run the write twice and read the store back")
            self.assertFalse(any("falsifier" in a for a in advisories),
                             advisories)

    def test_downgraded_hypothesis_is_named(self) -> None:
        from test_godmode_runtime import isolated_project
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            advisories = self._record(
                archive, project,
                text="the parser is verified to drop trailing commas",
                grade="verified",
                cites=["cmd:python parse_check.py"])
            self.assertTrue(any("falsifier" in a for a in advisories),
                            advisories)
