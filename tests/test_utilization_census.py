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


class FourMoreFamiliesTests(unittest.TestCase):
    """The audit's worst offenders join the census where their demand is
    already recordable: criterion (work items tracked), plan (same),
    verdict (verified-grade claims staked), assumption (incidents opened)."""

    def test_tracked_work_without_criteria_or_plans_reads_dormant(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "feat-1", "a feature", "active")
            fams = utilization(archive)["families"]
            self.assertEqual(fams["criteria"]["verdict"], "dormant-with-demand")
            self.assertEqual(fams["planning"]["verdict"], "dormant-with-demand")

    def test_criterion_and_plan_records_satisfy_them(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "feat-1", "a feature", "active")
            archive.append("criterion", "feat-1",
                           {"task": "feat-1", "text": "all pins green"})
            archive.append("plan", "feat-1-plan",
                           {"state": "approved", "contract": {}})
            fams = utilization(archive)["families"]
            self.assertEqual(fams["criteria"]["verdict"], "satisfied")
            self.assertEqual(fams["planning"]["verdict"], "satisfied")

    def test_verified_claims_without_verdicts_read_dormant(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S-test", "the fix holds",
                         "verified", cites=["file:README.md"])
            fams = utilization(archive)["families"]
            self.assertEqual(fams["independent-check"]["verdict"],
                             "dormant-with-demand")

    def test_incidents_without_assumptions_read_dormant(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("incident", "export broke",
                           {"detail": "boom", "failure_class": None,
                            "turning_point": False})
            fams = utilization(archive)["families"]
            self.assertEqual(fams["assumptions"]["verdict"],
                             "dormant-with-demand")


class DemandMomentNudgeTests(unittest.TestCase):
    """Detection alone was the gap the operator named: the census read
    dormant-with-demand while nothing fired AT the moment of demand. The
    writers now nudge: a work item entering active without a criterion
    carries a finding; an incident recorded without a stated assumption
    carries an advisory. Findings inform, they never block."""

    def test_activating_an_item_without_a_criterion_is_named(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_item(archive, "feat-1", "a feature", "active")
            self.assertIn("criterion-missing", record["data"].get("findings", []))

    def test_a_preregistered_criterion_silences_it(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("criterion", "feat-1",
                           {"task": "feat-1", "text": "all pins green"})
            record = record_item(archive, "feat-1", "a feature", "active")
            self.assertNotIn("criterion-missing",
                             record["data"].get("findings", []))

    def test_an_incident_without_assumptions_carries_the_advisory(self) -> None:
        from godmode_runtime.godmode_mistakes import record_incident
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom")
            self.assertTrue(any("assumption" in a for a in
                                record["data"].get("advisories", [])))


class PreflightCensusTests(unittest.TestCase):
    """A push preflight that never mentions standing process debt is how
    eleven commits queue over a dormant census: the families now ride the
    preflight as judgment findings - a person decides, nothing blocks."""

    def test_dormant_families_appear_as_judgment_findings(self) -> None:
        import subprocess
        from godmode_runtime.godmode_status import record_item
        from godmode_runtime.godmode_preflight import push_preflight
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "feat-1", "a feature", "active")
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.invalid"],
                           cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "t"],
                           cwd=project, check=True)
            (project / "a.txt").write_text("x", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=project,
                           check=True)
            report = push_preflight(project, archive=archive)
            details = " ".join(f["detail"] for f in report["judgment"])
            self.assertIn("dormant-with-demand", details)


class TerminalWorkIsNotDemandTests(unittest.TestCase):
    """A criterion for work already verified and shipped is ritual, not
    rigor: criteria/planning demand counts OPEN items only, the same
    unresolved-only semantic evidence debt uses (operator clearing,
    2026-09-01)."""

    def test_terminal_items_stop_demanding(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "done-1", "old work", "verified",
                        evidence=["cmd:true"])
            fams = utilization(archive)["families"]
            self.assertEqual(fams["criteria"]["verdict"], "idle")
            self.assertEqual(fams["planning"]["verdict"], "idle")

    def test_open_items_still_demand(self) -> None:
        from godmode_runtime.godmode_status import record_item
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "open-1", "new work", "active")
            self.assertEqual(
                utilization(archive)["families"]["criteria"]["verdict"],
                "dormant-with-demand")


class EvidenceRichnessTests(unittest.TestCase):
    """Executor-grade signal beats self-declaration - the census now says
    which one a project's claims actually run on."""

    def test_buckets_split_by_citation_grade(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S", "the suite passes end to end",
                         "observed", cites=["cmd:python -m unittest"])
            record_claim(archive, project, "S", "the readme documents the flag",
                         "observed", cites=["file:README.md"])
            record_claim(archive, project, "S", "the parser is fine I think",
                         "observed", cites=[])
            richness = utilization(archive, project)["evidence_richness"]
            self.assertEqual(richness["executor"], 1)
            self.assertEqual(richness["cited"], 1)
            self.assertEqual(richness["bare"], 1)

    def test_all_bare_claims_draw_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            for index in range(5):
                record_claim(archive, project, "S",
                             f"unbacked statement number {index} here",
                             "observed", cites=[])
            richness = utilization(archive, project)["evidence_richness"]
            self.assertIn("self-declared", richness["advisory"])

    def test_a_healthy_mix_is_quiet(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            record_claim(archive, project, "S", "the suite passes end to end",
                         "observed", cites=["cmd:python -m unittest"])
            richness = utilization(archive, project)["evidence_richness"]
            self.assertIsNone(richness["advisory"])


class AtlasAndChecklistFamilyTests(unittest.TestCase):
    """S13 census next rows: the atlas verb leaves a record so its family
    can exist, and checklist demand is release-shaped (version records)."""

    def test_incidents_without_atlas_queries_read_dormant(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.append("incident", "the gate broke on posix",
                           {"failure_class": "environment-drift",
                            "turning_point": "reproduced on aliased TMP"})
            families = utilization(archive)["families"]
            self.assertEqual(families["atlas"]["verdict"], "dormant-with-demand")

    def test_an_atlas_query_satisfies_the_demand(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.append("incident", "the gate broke on posix",
                           {"failure_class": "environment-drift",
                            "turning_point": "reproduced"})
            archive.append("action", "atlas-query",
                           {"verb": "affected", "symbol_count": 1})
            families = utilization(archive)["families"]
            self.assertEqual(families["atlas"]["verdict"], "satisfied")

    def test_versions_without_checklist_rows_read_dormant(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.append("version", "0.9.9",
                           {"component": "bed", "value": "0.9.9"})
            families = utilization(archive)["families"]
            self.assertEqual(families["checklist"]["verdict"],
                             "dormant-with-demand")

    def test_a_checklist_row_satisfies_release_demand(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.append("version", "0.9.9",
                           {"component": "bed", "value": "0.9.9"})
            archive.append("checklist", "release-gates",
                           {"item": "docs lint", "status": "pass"})
            families = utilization(archive)["families"]
            self.assertEqual(families["checklist"]["verdict"], "satisfied")
