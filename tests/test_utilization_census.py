"""Demand-vs-use census: dormancy with demand is the alarm.

Absolute usage tracking is wrong - a project with no databases should
never touch `db`. The honest question pairs what the record DEMANDED
(reversals, repeated incidents' subjects, third strikes) with what
FIRED (incidents opened, differentials recorded, lessons written,
verdicts run). Dormant machinery with standing demand is named;
dormant machinery with no demand is health; a fresh archive reads
honest-empty. Advisory always - the census informs the doctor, it
never flips health.
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

from godmode_runtime.godmode_attest import record_claim, resolve_claim  # noqa: E402
from godmode_runtime.godmode_metrics import utilization  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _reversal(archive, project, text):
    (project / "README.md").write_text("x", encoding="utf-8")
    claim = record_claim(archive, project, "S-test", text, "observed",
                        confidence=0.8)
    resolve_claim(archive, project, "S-test", claim["sequence"], "failed",
                  cites=["file:README.md"])


class UtilizationCensusTests(unittest.TestCase):
    def test_a_fresh_archive_reads_idle(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            census = utilization(archive)
            self.assertTrue(all(f["verdict"] == "idle"
                                for f in census["families"].values()))

    def test_reversals_without_an_investigation_read_dormant(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _reversal(archive, project, "the matrix jobs pass on the runner")
            _reversal(archive, project, "the matrix jobs pass on the runner")
            family = utilization(archive)["families"]["investigation"]
            self.assertEqual(family["verdict"], "dormant-with-demand")
            self.assertGreaterEqual(family["demand"], 1)
            self.assertEqual(family["fired"], 0)

    def test_an_opened_incident_satisfies_the_demand(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _reversal(archive, project, "the matrix jobs pass on the runner")
            _reversal(archive, project, "the matrix jobs pass on the runner")
            archive.append("incident", "runner loop opened",
                           {"detail": "investigating", "failure_class": None,
                            "turning_point": False})
            family = utilization(archive)["families"]["investigation"]
            self.assertEqual(family["verdict"], "satisfied")

    def test_incidents_without_lessons_read_dormant_learning(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("incident", "export broke",
                           {"detail": "boom", "failure_class": None,
                            "turning_point": False})
            family = utilization(archive)["families"]["learning"]
            self.assertEqual(family["verdict"], "dormant-with-demand")

    def test_a_lesson_after_the_incident_satisfies_learning(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("incident", "export broke",
                           {"detail": "boom", "failure_class": None,
                            "turning_point": False})
            archive.append("lesson", "export-rule",
                           {"value": "bound the export", "status": "active",
                            "generalized_guard": "always bound exports"})
            family = utilization(archive)["families"]["learning"]
            self.assertEqual(family["verdict"], "satisfied")


if __name__ == "__main__":
    unittest.main()


class DbFamilyTests(unittest.TestCase):
    """The db family joins the census the way the operator's own audit
    demonstrated: demand is detectable (database files exist in the tree),
    so dormancy is measured, never assumed."""

    def test_database_files_without_records_read_dormant(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "app.sqlite3").write_bytes(b"SQLite format 3\x00" + b"\x00" * 90)
            family = utilization(archive, project)["families"]["db"]
            self.assertEqual(family["verdict"], "dormant-with-demand")

    def test_a_database_record_satisfies_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "app.sqlite3").write_bytes(b"SQLite format 3\x00" + b"\x00" * 90)
            archive.append("database", "app.sqlite3",
                           {"engine": "sqlite", "status": "inventoried"})
            family = utilization(archive, project)["families"]["db"]
            self.assertEqual(family["verdict"], "satisfied")

    def test_no_database_files_reads_idle(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            family = utilization(archive, project)["families"]["db"]
            self.assertEqual(family["verdict"], "idle")

    def test_without_a_project_the_family_is_absent(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertNotIn("db", utilization(archive)["families"])
