"""NS-13c + I-8: PDCA, OODA and the research read order are named SOPs.

Each step names the verbs that perform it; `sop --name <n>` writes the
standing-procedure record once, at first use; a PDCA phase's cycle time is
the count of records between its attestation and the next phase's, so a
Check that never follows a Do (fixes with no retest) is visible in
`metrics` and in `trends`.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_attest import open_session, record_step  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_stages import (  # noqa: E402
    SOP_STEPS, SOPS, named_sop_attest, pdca_cycle,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _run(project, *argv):
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(["--project", str(project), *argv])
    return code, json.loads(out.getvalue())


class RegistryTests(unittest.TestCase):
    def test_the_registry_names_four_sops(self) -> None:
        self.assertEqual(set(SOPS), {"troubleshoot", "pdca", "ooda", "research"})
        self.assertIs(SOPS["troubleshoot"], SOP_STEPS)

    def test_every_named_step_carries_its_verbs(self) -> None:
        for name in ("pdca", "ooda", "research"):
            for step in SOPS[name]:
                self.assertTrue(step["id"] and step["text"], (name, step))
                self.assertTrue(step["verbs"], (name, step))

    def test_pdca_and_ooda_phases_in_order(self) -> None:
        self.assertEqual([s["id"] for s in SOPS["pdca"]], ["plan", "do", "check", "act"])
        self.assertEqual([s["id"] for s in SOPS["ooda"]], ["observe", "orient", "decide", "act"])
        self.assertEqual([s["id"] for s in SOPS["research"]],
                         ["license", "tree", "files", "cite", "verdicts"])


class SopVerbTests(unittest.TestCase):
    def test_first_use_writes_one_standing_record_per_sop(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "sop")
            _run(project, "sop", "--name", "pdca", "--session", session)
            _run(project, "sop", "--name", "ooda", "--session", session)
            _run(project, "sop", "--name", "pdca", "--session", session)
            standing = [r for r in archive.read_events()
                        if r["kind"] == "decision" and r["subject"].startswith("sop:")]
        self.assertEqual(sorted(r["subject"] for r in standing), ["sop:ooda", "sop:pdca"])
        pdca = next(r for r in standing if r["subject"] == "sop:pdca")
        self.assertEqual([s["id"] for s in pdca["data"]["steps"]], ["plan", "do", "check", "act"])

    def test_status_and_attest_by_name(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "sop")
            code, status = _run(project, "sop", "--name", "ooda", "--session", session)
            self.assertEqual(code, 0, status)
            self.assertEqual(status["next"], "observe")
            self.assertTrue(status["next_verbs"])
            code, attested = _run(project, "sop", "--name", "ooda", "--attest", "observe",
                                  "--session", session, "--result", "brief read")
            self.assertEqual(code, 0, attested)
            self.assertEqual(attested["record"]["subject"], "sop:ooda:observe")
            _code, status = _run(project, "sop", "--name", "ooda", "--session", session)
        self.assertEqual(status["next"], "orient")

    def test_an_unknown_step_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "sop")
            with self.assertRaises(ArchiveError):
                named_sop_attest(archive, session, "pdca", "T1")

    def test_the_bare_verb_still_reports_the_troubleshooting_sop(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "sop")
            _code, status = _run(project, "sop", "--session", session)
        self.assertEqual(status["next"], "T0")


class ResearchMinimumTests(unittest.TestCase):
    """I-8: adopt/extend needs at least two implementing files cited path#lines."""

    def test_adopt_without_two_implementing_files_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "research")
            named_sop_attest(archive, session, "research", "files",
                             evidence=["file:src/engine.py#L10-L40"])
            with self.assertRaises(ArchiveError) as caught:
                named_sop_attest(archive, session, "research", "verdicts",
                                 result="adopt: the engine design")
            self.assertIn("2", str(caught.exception))

    def test_adopt_with_two_implementing_files_is_attested(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "research")
            named_sop_attest(archive, session, "research", "files",
                             evidence=["file:src/engine.py#L10-L40", "file:src/store.py#L1-L20"])
            record = named_sop_attest(archive, session, "research", "verdicts",
                                      result="extend: the engine design")
        self.assertEqual(record["subject"], "sop:research:verdicts")

    def test_files_cited_across_two_attestations_both_count(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "research")
            named_sop_attest(archive, session, "research", "files",
                             evidence=["file:src/engine.py#L10-L40"])
            named_sop_attest(archive, session, "research", "files",
                             evidence=["file:src/store.py#L1-L20"])
            record = named_sop_attest(archive, session, "research", "verdicts",
                                      result="adopt: the engine design")
        self.assertEqual(record["subject"], "sop:research:verdicts")

    def test_a_park_verdict_needs_no_implementing_files(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "research")
            record = named_sop_attest(archive, session, "research", "verdicts",
                                      result="park: README-level read only")
        self.assertEqual(record["subject"], "sop:research:verdicts")


class PdcaCycleTests(unittest.TestCase):
    def test_cycle_time_is_records_between_phase_attestations(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "pdca")
            named_sop_attest(archive, session, "pdca", "plan")
            for n in range(3):
                archive.append("decision", f"note {n}", {"status": "active"})
            named_sop_attest(archive, session, "pdca", "do")
            archive.append("decision", "one more", {"status": "active"})
            named_sop_attest(archive, session, "pdca", "check")
            cycle = pdca_cycle(archive.read_events())
        phases = {row["phase"]: row for row in cycle["phases"]}
        self.assertEqual(phases["plan"]["records"], 3)
        self.assertEqual(phases["do"]["records"], 1)
        self.assertEqual(phases["check"]["state"], "open")
        self.assertIsNone(cycle["stalled"])

    def test_fixes_without_a_retest_read_as_a_stalled_check(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "pdca")
            named_sop_attest(archive, session, "pdca", "plan")
            named_sop_attest(archive, session, "pdca", "do")
            archive.append("change", "fix the parser", {"files": ["src/p.py"]})
            stalled = pdca_cycle(archive.read_events())
            self.assertEqual(stalled["stalled"], "check")
            # A check that ran after the fix un-stalls it.
            record_step(archive, session, "check:unit", "ran", result="exit 0",
                        evidence=["cmd:python -m unittest"])
            self.assertIsNone(pdca_cycle(archive.read_events())["stalled"])

    def test_metrics_and_trends_carry_the_row(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "pdca")
            named_sop_attest(archive, session, "pdca", "plan")
            named_sop_attest(archive, session, "pdca", "do")
            archive.append("change", "fix the parser", {"files": ["src/p.py"]})
            _code, metrics = _run(project, "metrics")
            _code, trends = _run(project, "trends")
        self.assertEqual(metrics["pdca_cycle"]["stalled"], "check")
        self.assertEqual(trends["pdca"]["stalled"], "check")
        self.assertIn("pdca", trends["report"])
        self.assertIn("stalled", trends["report"])


if __name__ == "__main__":
    unittest.main()
