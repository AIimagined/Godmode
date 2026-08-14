"""Metrics measure whether the product works, not whether its tests pass.

The distinction matters most where a metric could flatter: an empty archive
must report insufficient data rather than a perfect score, because a zero
denominator is the easiest way to look healthy while measuring nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_metrics import (  # noqa: E402
    METRIC_ORDER,
    metrics,
    render_markdown,
)


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


class EmptyArchiveTests(unittest.TestCase):
    def test_nothing_measured_reports_insufficient_data_not_success(self) -> None:
        with isolated_project() as (project, archive):
            report = metrics(archive, project)
            self.assertEqual(report["verdict"], "insufficient-data")
            self.assertEqual(report["summary"]["measured"], 0)
            for name in METRIC_ORDER:
                entry = report["metrics"][name]
                self.assertIsNone(entry["value"], name)
                self.assertEqual(entry["confidence"], "insufficient-data", name)
                self.assertIsNone(entry["meets_target"], name)

    def test_all_twelve_metrics_are_present_and_ordered(self) -> None:
        with isolated_project() as (project, archive):
            report = metrics(archive, project)
            self.assertEqual(len(METRIC_ORDER), 12)
            self.assertEqual(list(report["metrics"]), list(METRIC_ORDER))


class MeasuredTests(unittest.TestCase):
    def test_resume_accuracy_counts_a_session_that_followed_its_next_action(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            archive.append("checkpoint", "staged the rotation fix",
                           {"status": "green", "next": "run the replay test"})
            session = open_session(archive, "next-session")
            record_step(archive, session, "run the replay test", "ran", result="passed")
            entry = metrics(archive, project)["metrics"]["resume_accuracy"]
            self.assertEqual(entry["confidence"], "measured")
            self.assertEqual(entry["value"], 1.0)
            self.assertTrue(entry["meets_target"])

    def test_a_drifting_session_lowers_resume_accuracy(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            archive.append("checkpoint", "staged the rotation fix",
                           {"status": "green", "next": "run the replay test"})
            session = open_session(archive, "next-session")
            record_step(archive, session, "refactor the billing module", "ran", result="done")
            entry = metrics(archive, project)["metrics"]["resume_accuracy"]
            self.assertEqual(entry["value"], 0.0)
            self.assertFalse(entry["meets_target"])

    def test_a_downgraded_root_cause_claim_lowers_rca_precision(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_claim, record_step

        with isolated_project() as (project, archive):
            session = open_session(archive, "rca")
            (project / "real.py").write_text("x = 1\n", encoding="utf-8")
            # A root cause now needs the differential that confirmed it, so the
            # claim that should hold cites the comparison that was run. The
            # attestation is what makes a `cmd:` citation resolve.
            record_step(archive, session, "differential", "ran",
                        result="compared", evidence=["cmd:diff old new"])
            record_claim(archive, project, session,
                         "root cause is the rotation reuse", "verified",
                         cites=["file:real.py", "cmd:diff old new"])
            record_claim(archive, project, session,
                         "root cause is the cache", "verified",
                         cites=["file:ghost.py"])
            entry = metrics(archive, project)["metrics"]["rca_precision"]
            self.assertEqual(entry["confidence"], "measured")
            self.assertEqual(entry["value"], 0.5)
            self.assertFalse(entry["meets_target"])

    def test_a_reopened_verified_item_raises_the_false_complete_rate(self) -> None:
        from godmode_runtime.godmode_status import record_item

        with isolated_project() as (project, archive):
            record_item(archive, "S1", "first", "verified", evidence=["file:a.py"])
            record_item(archive, "S1", "first", "active", proof="regression observed in CI")
            record_item(archive, "S2", "second", "verified", evidence=["file:b.py"])
            entry = metrics(archive, project)["metrics"]["false_complete_rate"]
            self.assertEqual(entry["confidence"], "measured")
            self.assertEqual(entry["value"], 0.5)
            self.assertFalse(entry["meets_target"])

    def test_evidence_density_averages_citations_per_claim(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_claim

        with isolated_project() as (project, archive):
            session = open_session(archive, "density")
            (project / "a.py").write_text("x = 1\n", encoding="utf-8")
            record_claim(archive, project, session, "a holds", "observed",
                         cites=["file:a.py"])
            record_claim(archive, project, session, "b holds", "observed")
            entry = metrics(archive, project)["metrics"]["evidence_density"]
            self.assertEqual(entry["value"], 0.5)


class TokenReductionBasisTests(unittest.TestCase):
    """token_reduction's basis: a real measured total when C-79's session-log
    metric is on record, the size-heuristic estimate only when it isn't -
    and the report always says which one was used (U-T1 follow-up)."""

    def test_basis_is_estimated_when_no_measured_metric_record_exists(self) -> None:
        with isolated_project() as (project, archive):
            archive.append("checkpoint", "one", {"status": "green", "next": "x"})
            entry = metrics(archive, project)["metrics"]["token_reduction"]
        self.assertIn("estimated", entry["basis"])

    def test_basis_is_measured_and_uses_real_tokens_when_a_measured_metric_exists(self) -> None:
        with isolated_project() as (project, archive):
            archive.append("checkpoint", "one", {"status": "green", "next": "x"})
            archive.append("metric", "session measurement", {
                "measured": True, "turns": 3, "tool_calls": {"Bash": 2},
                "commands": 2, "test_runs": 0, "tokens_in": 9000,
                "tokens_out": 500, "content_free": True, "session": "S-1",
            })
            entry = metrics(archive, project)["metrics"]["token_reduction"]
        self.assertIn("measured", entry["basis"])
        self.assertIn("9000", entry["basis"])

    def test_a_gap_metric_record_does_not_count_as_a_measured_basis(self) -> None:
        """`measured: False` is a stated gap, not a zero - it must not be
        read as "the session spent zero tokens" and silently win over the
        estimate."""
        with isolated_project() as (project, archive):
            archive.append("checkpoint", "one", {"status": "green", "next": "x"})
            archive.append("metric", "session measurement", {
                "measured": False, "reason": "transcript-file-not-found",
                "session": None, "content_free": True,
            })
            entry = metrics(archive, project)["metrics"]["token_reduction"]
        self.assertIn("estimated", entry["basis"])

    def test_several_measured_metric_records_sum_their_tokens(self) -> None:
        with isolated_project() as (project, archive):
            archive.append("checkpoint", "one", {"status": "green", "next": "x"})
            for tokens_in in (1000, 2500):
                archive.append("metric", "session measurement", {
                    "measured": True, "turns": 1, "tool_calls": {},
                    "commands": 0, "test_runs": 0, "tokens_in": tokens_in,
                    "tokens_out": 0, "content_free": True, "session": "S-1",
                })
            entry = metrics(archive, project)["metrics"]["token_reduction"]
        self.assertIn("3500", entry["basis"])


class RenderTests(unittest.TestCase):
    def test_markdown_names_every_metric_and_its_basis(self) -> None:
        with isolated_project() as (project, archive):
            rendered = render_markdown(metrics(archive, project))
            self.assertIn("PRODUCT METRICS", rendered)
            for name in METRIC_ORDER:
                self.assertIn(name, rendered)

    def test_report_is_deterministic(self) -> None:
        with isolated_project() as (project, archive):
            archive.append("checkpoint", "one", {"status": "green", "next": "do a thing"})
            first = metrics(archive, project)
            second = metrics(archive, project)
            self.assertEqual(first["metrics"], second["metrics"])


if __name__ == "__main__":
    unittest.main()
