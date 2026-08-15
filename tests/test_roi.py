"""U-E1: ROI report - counts-only, no causal language.

The report folds `metric` records (C-79/U-T1), `verdict` records (U-V1), and
`action` records tagged with the closed `roi_event` vocabulary
(`godmode_roi.GATE_DENIED` etc.) into one counts-only shape. These tests
build that vocabulary directly with plain `archive.append()` calls - no
shipped writer emits gate/precedent/fence events yet (see the module
docstring), so the fixture stands in for one.
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

from godmode_runtime import godmode_roi as roi_module  # noqa: E402
from godmode_runtime.godmode_roi import (  # noqa: E402
    CAUSAL_DENYLIST,
    FENCE_FINDING,
    GATE_ASKED,
    GATE_DENIED,
    render_roi,
    roi_report,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _metric(archive, *, tokens_in: int, tokens_out: int) -> None:
    archive.append(
        "metric",
        "session measurement",
        {
            "measured": True,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "session": "S-fixture",
            "content_free": True,
        },
        evidence=[],
    )


def _metric_gap(archive) -> None:
    archive.append(
        "metric",
        "session measurement",
        {
            "measured": False,
            "reason": "transcript-file-not-found",
            "session": "S-gap",
            "content_free": True,
        },
        evidence=[],
    )


def _gate_event(archive, roi_event: str, *, claim: str = "") -> None:
    archive.append(
        "action",
        roi_event,
        {"roi_event": roi_event, "claim": claim},
        evidence=[],
    )


def _verdict(archive, disposition: str, *, claim: str = "roi-fixture claim") -> None:
    archive.append(
        "verdict",
        "claim:roi-fixture",
        {
            "claim": claim,
            "claimed_value": "42",
            "witness": {"kind": "seq", "ref": "1"},
            "checker": "cmd:true",
            "disposition": disposition,
            "run_state": "terminated",
            "acquitted_by": "independent",
        },
        evidence=[],
    )


def _seed_fixture(archive, *, prose: str = "") -> None:
    """2 measurement records, 3 refusals, 1 ask, 1 confirmed + 1 refuted
    verdict, 1 fence finding - plain appends, no production writer exists
    for the gate/precedent/fence events yet."""
    _metric(archive, tokens_in=100, tokens_out=50)
    _metric(archive, tokens_in=200, tokens_out=80)
    for _ in range(3):
        _gate_event(archive, GATE_DENIED)
    _gate_event(archive, GATE_ASKED)
    _verdict(archive, "confirmed")
    _verdict(archive, "refuted", claim=prose or "roi-fixture refuted claim")
    _gate_event(archive, FENCE_FINDING)


def _seed_session_without_measurement(archive) -> None:
    _metric_gap(archive)


class RoiCounts(unittest.TestCase):
    def test_counts_fold_from_fixture_records(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed_fixture(archive)
            r = roi_report(archive, sessions=None)
            self.assertEqual(
                r["tokens"],
                {"in": 300, "out": 130, "measured_sessions": 2, "unmeasured_sessions": 0},
            )
            self.assertEqual(r["gate"]["denied"], 3)
            self.assertEqual(r["verdicts"], {"confirmed": 1, "refuted": 1, "contested": 0})
            self.assertTrue(r["basis"])
            self.assertTrue(all(b.startswith("seq:") for b in r["basis"]))

    def test_unmeasured_sessions_stated_never_interpolated(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed_session_without_measurement(archive)
            r = roi_report(archive, sessions=None)
            self.assertEqual(r["tokens"]["measured_sessions"], 0)
            self.assertNotIn("in", r["tokens"])  # no token numbers invented


class NoCausalLanguage(unittest.TestCase):
    def test_rendered_report_never_claims_savings(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed_fixture(archive)
            text = render_roi(roi_report(archive, sessions=None))
            for word in CAUSAL_DENYLIST:  # ("saved", "prevented", "avoided", "earned", "roi of")
                self.assertNotIn(word, text.lower())

    def test_refuted_verdict_labeled_as_caught_not_prevented(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed_fixture(archive)
            self.assertIn(
                "rework-candidate-caught", render_roi(roi_report(archive, sessions=None))
            )


class ContentFree(unittest.TestCase):
    def test_sentinel_prose_never_reaches_report(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _seed_fixture(archive, prose="SENTINEL_SECRET_XYZ in a claim body")
            self.assertNotIn(
                "SENTINEL_SECRET_XYZ", render_roi(roi_report(archive, sessions=None))
            )


class ContestedDispositionAbsent(unittest.TestCase):
    def test_contested_counts_zero_without_a_writer(self) -> None:
        """The report counts what exists: an archive holding no contested
        verdicts reports zero, never crashes. ('contested' ships as a real
        disposition since the verdict-panels unit; this pins the zero case.)"""
        with isolated_project() as (project, _state, _anchor, archive):
            _verdict(archive, "confirmed")
            r = roi_report(archive, sessions=None)
            self.assertEqual(r["verdicts"]["contested"], 0)


class PlantVerification(unittest.TestCase):
    def test_denylist_check_catches_a_planted_causal_word(self) -> None:
        """Proves the mechanism NoCausalLanguage relies on is not vacuous: a
        render_roi that regressed to leak a causal word IS caught by the same
        `assertNotIn` the real test runs - not asserted by construction."""
        original_render = roi_module.render_roi

        def _leaky_render(report):
            return original_render(report) + " (tokens saved this session)"

        with isolated_project() as (project, _state, _anchor, archive):
            _seed_fixture(archive)
            report = roi_report(archive, sessions=None)
            with mock.patch.object(roi_module, "render_roi", _leaky_render):
                leaky_text = roi_module.render_roi(report)
            with self.assertRaises(AssertionError):
                self.assertNotIn("saved", leaky_text.lower())
            # Restored: the module's real render_roi is untouched outside the patch.
            self.assertNotIn("saved", original_render(report).lower())


if __name__ == "__main__":
    unittest.main()
