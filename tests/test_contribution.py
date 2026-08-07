"""What Godmode did this session — counted from records, never inflated.

The central test is the honesty one: a refusal is a refusal, and the summary
must never describe it as a disaster averted. The counterfactual is unknowable,
and claiming it would be exactly the unfalsifiable assertion the runtime
downgrades everywhere else.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
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
from godmode_runtime.godmode_contribution import (  # noqa: E402
    contribution,
    render_line,
    summary_enabled,
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


class SilenceTests(unittest.TestCase):
    def test_a_session_where_nothing_fired_says_nothing(self) -> None:
        from godmode_runtime.godmode_attest import open_session

        with isolated_project() as (project, archive):
            session = open_session(archive, "quiet")
            report = contribution(archive, project, session)
            self.assertFalse(report["reportable"])
            self.assertIsNone(render_line(report))

    def test_bounding_alone_is_reportable(self) -> None:
        """Token reduction is measured, so it counts even with no refusals."""
        from godmode_runtime.godmode_attest import open_session

        with isolated_project() as (project, archive):
            session = open_session(archive, "bounded")
            for index in range(30):
                archive.append("decision", f"decision-{index}",
                               {"status": "active", "prose": "x" * 400})
            report = contribution(archive, project, session)
            self.assertTrue(report["reportable"])
            self.assertGreater(report["context"]["reduction"], 0)


class CountingTests(unittest.TestCase):
    def test_refusals_and_downgrades_are_counted_with_their_records(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_claim, record_step

        with isolated_project() as (project, archive):
            session = open_session(archive, "busy")
            record_step(archive, session, "check:suite", "blocked",
                        result="exit 1", reason="check failed")
            record_claim(archive, project, session, "everything works", "verified")
            report = contribution(archive, project, session)

            self.assertEqual(report["activity"]["checks_blocked"]["count"], 1)
            self.assertEqual(report["activity"]["claims_downgraded"]["count"], 1)
            # Every count carries the records that produced it, so the number is
            # checkable rather than trusted.
            for entry in report["activity"].values():
                if entry["count"]:
                    self.assertTrue(entry["records"], entry)
                    self.assertTrue(all(r.startswith("seq:") for r in entry["records"]))

    def test_skipped_steps_and_secret_catches_are_counted(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            session = open_session(archive, "skips")
            record_step(archive, session, "read the sources", "skipped", reason="in a hurry")
            archive.append("incident", "secret-blocked-before-write",
                           {"status": "blocked", "value": "credential shape refused"})
            report = contribution(archive, project, session)
            self.assertEqual(report["activity"]["steps_skipped"]["count"], 1)
            self.assertEqual(report["activity"]["secrets_caught"]["count"], 1)

    def test_counts_are_scoped_to_the_session(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            first = open_session(archive, "one")
            record_step(archive, first, "check:a", "blocked", result="exit 1", reason="failed")
            second = open_session(archive, "two")
            report = contribution(archive, project, second)
            self.assertEqual(report["activity"]["checks_blocked"]["count"], 0)


class HonestyTests(unittest.TestCase):
    def test_the_summary_never_claims_a_disaster_was_averted(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            session = open_session(archive, "honest")
            record_step(archive, session, "check:suite", "blocked",
                        result="exit 1", reason="check failed")
            report = contribution(archive, project, session)
            line = render_line(report)
            # Everything except the caveat, which exists precisely to say the
            # counterfactual is unmeasurable and therefore names it.
            without_caveat = dict(report)
            caveat = without_caveat.pop("caveat")
            blob = json.dumps(without_caveat).lower() + " " + (
                (line or "").lower().replace(caveat.lower(), ""))
            for overclaim in ("prevented", "averted", "saved you", "errors stopped",
                              "would have", "disaster", "bugs caught"):
                self.assertNotIn(overclaim, blob, f"summary overclaims: {overclaim}")
            self.assertIn("not disasters averted", caveat.lower())
            # And the caveat is never dropped from the rendered line.
            self.assertIn("not disasters averted", (line or "").lower())

    def test_token_reduction_is_labelled_measured(self) -> None:
        from godmode_runtime.godmode_attest import open_session

        with isolated_project() as (project, archive):
            session = open_session(archive, "measured")
            for index in range(30):
                archive.append("decision", f"d-{index}", {"status": "active", "prose": "y" * 400})
            report = contribution(archive, project, session)
            self.assertEqual(report["context"]["basis"], "measured")


class OptOutTests(unittest.TestCase):
    def test_a_project_can_turn_the_summary_off(self) -> None:
        with isolated_project() as (project, _archive):
            self.assertTrue(summary_enabled(project))
            (project / ".godmode-report.json").write_text(
                json.dumps({"session_summary": False}), encoding="utf-8")
            self.assertFalse(summary_enabled(project))

    def test_a_malformed_opt_out_file_leaves_the_summary_on(self) -> None:
        with isolated_project() as (project, _archive):
            (project / ".godmode-report.json").write_text("null", encoding="utf-8")
            self.assertTrue(summary_enabled(project))

    def test_a_disabled_summary_produces_no_line(self) -> None:
        from godmode_runtime.godmode_attest import open_session, record_step

        with isolated_project() as (project, archive):
            (project / ".godmode-report.json").write_text(
                json.dumps({"session_summary": False}), encoding="utf-8")
            session = open_session(archive, "off")
            record_step(archive, session, "check:a", "blocked", result="exit 1", reason="failed")
            report = contribution(archive, project, session)
            self.assertFalse(report["reportable"])
            self.assertEqual(report["disabled_by"], ".godmode-report.json")


if __name__ == "__main__":
    unittest.main()
